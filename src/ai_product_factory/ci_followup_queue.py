from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote

from .supabase_server import resolve_supabase_server_config


@dataclass(frozen=True)
class CIFollowupItem:
    run_id: str
    project_key: str
    repository: str
    issue_number: int
    branch: str
    pr_number: int
    candidate_commit: str
    human_gate_required: bool
    change_set_id: str | None = None


class SupabaseCIFollowupQueue:
    """Read-only selector for one ci_pending run.

    The GitHub Actions workflow serializes runs through a global concurrency
    group, so this selector intentionally does not introduce another lease.
    """

    def __init__(self, *, url: str | None = None, secret_key: str | None = None, service_role_key: str | None = None) -> None:
        cfg=resolve_supabase_server_config(url=url,secret_key=secret_key,service_role_key=service_role_key)
        self.url=cfg.url
        self.headers=cfg.headers

    def _get(self, path: str) -> list[dict]:
        req=urllib.request.Request(f"{self.url}/rest/v1/{path}",headers=self.headers,method="GET")
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane read failed: {path} ({exc.code})") from exc
        return [] if not raw else json.loads(raw)

    def has_ci_dispatch_receipt(
        self, *, run_id: str, pr_number: int, candidate_commit: str,
        branch: str, workflow: str,
    ) -> bool:
        """Deduplicate exact-SHA GitHub Actions dispatches across scheduler wakes.

        A successful dispatch is durably recorded in factory_tool_usage.
        Missing GitHub checks after dispatch should not cause repeated hourly
        workflow_dispatch attempts or unrelated paid work.
        """
        if (not isinstance(run_id,str) or not run_id.strip()
            or not isinstance(pr_number,int) or isinstance(pr_number,bool)
            or pr_number < 1 or not re.fullmatch(r"[0-9a-f]{40}",candidate_commit)
            or not isinstance(branch,str) or not branch.strip()
            or branch in ("main","master") or branch.startswith("/")
            or ".." in branch or "//" in branch or "\\" in branch
            or any(ch.isspace() or ord(ch)<32 or ord(ch)==127 for ch in branch)
            or workflow != "validate.yml"):
            raise ValueError("invalid exact CI dispatch receipt identity")
        rows = self._get(
            "factory_tool_usage?select=metadata"
            "&run_id=eq." + quote(run_id,safe="")
            + "&operation=eq.dispatch_ci&order=created_at.desc&limit=11"
        )
        if not isinstance(rows,list) or len(rows)>10:
            raise RuntimeError("CI dispatch receipt history exceeds safe boundary")
        matched=False
        for row in rows:
            if not isinstance(row,dict) or not isinstance(row.get("metadata"),dict):
                raise RuntimeError("malformed durable CI dispatch receipt")
            data=row["metadata"]
            if data.get("head_sha") != candidate_commit:
                continue
            if (data.get("pr") != pr_number or data.get("ref") != branch
                or data.get("workflow") != workflow):
                raise RuntimeError("same-SHA CI dispatch identity drift")
            matched=True
        return matched

    def next_pending(self, *, exclude_run_ids: tuple[str, ...] = (), allow_unreconciled_receipt: bool = False) -> CIFollowupItem | None:
        # Read-only bounded FIFO lookahead. A pending external CI/human gate
        # must not mask later candidates already eligible for follow-up.
        if (not isinstance(exclude_run_ids, tuple) or len(exclude_run_ids) > 8
            or any(not isinstance(v, str) or not v.strip() for v in exclude_run_ids)):
            raise ValueError("invalid bounded follow-up exclusion set")
        limit = 12 if exclude_run_ids else 1
        runs=self._get("factory_runs?select=id,task_id,branch_name,candidate_commit,metadata&status=eq.ci_pending&order=created_at.asc&limit="+str(limit))
        if not isinstance(runs, list) or any(not isinstance(row, dict) for row in runs):
            raise RuntimeError("invalid follow-up queue response")
        skipped = set(exclude_run_ids)
        run = next((row for row in runs if str(row.get("id") or "") not in skipped), None)
        if run is None:
            return None
        run_id=str(run["id"])
        task_id=str(run["task_id"])
        candidate=str(run.get("candidate_commit") or "")
        branch=str(run.get("branch_name") or "")
        metadata=run.get("metadata") or {}
        issue_data=metadata.get("github_issue") or {}
        issue_number=int(issue_data.get("number") or 0)
        human_gate=bool(metadata.get("human_gate_required",False))
        if not candidate or not branch or issue_number < 1:
            raise RuntimeError("ci_pending run is missing candidate, branch, or GitHub issue binding")

        tasks=self._get(f"factory_tasks?select=project_id&id=eq.{quote(task_id)}&limit=1")
        if not tasks:
            raise RuntimeError("ci_pending run task was not found")
        project_id=str(tasks[0]["project_id"])
        projects=self._get(f"factory_projects?select=project_key,repository&id=eq.{quote(project_id)}&limit=1")
        if not projects or not projects[0].get("repository"):
            raise RuntimeError("ci_pending run project repository is not configured")

        usage=self._get(f"factory_tool_usage?select=metadata&run_id=eq.{quote(run_id)}&operation=eq.create_pr&order=created_at.desc&limit=1")
        if usage:
            pr_meta=usage[0].get("metadata") or {}
            pr_number=int(pr_meta.get("pr") or 0)
            head_sha=str(pr_meta.get("head_sha") or "")
            if pr_number < 1:
                raise RuntimeError("durable PR evidence is missing PR number")
            if head_sha != candidate and not allow_unreconciled_receipt:
                # An immutable create_pr receipt may legitimately predate a
                # separately audited, atomic candidate reconciliation.
                reconciliations=self._get(
                    f"factory_tool_usage?select=metadata&run_id=eq.{quote(run_id)}"
                    "&operation=eq.reconcile_pr_candidate&order=created_at.desc&limit=1"
                )
                receipt=(reconciliations[0].get("metadata") or {}) if reconciliations else {}
                if (receipt.get("previous_commit") != head_sha
                    or receipt.get("candidate_commit") != candidate
                    or receipt.get("pr_number") != str(pr_number)
                    or receipt.get("change_set_id") != metadata.get("change_set_id")):
                    raise RuntimeError("durable PR evidence does not match run candidate commit")
        elif str(metadata.get("source") or "")=="operator_reconciled_dogfood":
            pr_number=int(metadata.get("pr_number") or 0)
            if pr_number < 1:
                raise RuntimeError("operator-reconciled dogfood run is missing PR number")
        else:
            raise RuntimeError("ci_pending run has no durable create_pr evidence")

        project=projects[0]
        change_set_id = metadata.get("change_set_id") if metadata.get("source") == "change-set" else None
        if change_set_id is not None and (not isinstance(change_set_id, str) or not change_set_id.strip()):
            raise RuntimeError("invalid durable change-set identity")
        return CIFollowupItem(
            run_id=run_id,
            project_key=str(project["project_key"]),
            repository=str(project["repository"]),
            issue_number=issue_number,
            branch=branch,
            pr_number=pr_number,
            candidate_commit=candidate,
            human_gate_required=human_gate,
            change_set_id=change_set_id,
        )
