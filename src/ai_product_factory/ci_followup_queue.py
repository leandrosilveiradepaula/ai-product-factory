from __future__ import annotations

import json
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

    def next_pending(self, *, exclude_run_ids: tuple[str, ...] = ()) -> CIFollowupItem | None:
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
            if pr_number < 1 or head_sha != candidate:
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
