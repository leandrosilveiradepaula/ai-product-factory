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

    def next_pending(self) -> CIFollowupItem | None:
        runs=self._get("factory_runs?select=id,task_id,branch_name,candidate_commit,metadata&status=eq.ci_pending&order=created_at.asc&limit=1")
        if not runs:
            return None
        run=runs[0]
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
        if not usage:
            raise RuntimeError("ci_pending run has no durable create_pr evidence")
        pr_meta=usage[0].get("metadata") or {}
        pr_number=int(pr_meta.get("pr") or 0)
        head_sha=str(pr_meta.get("head_sha") or "")
        if pr_number < 1 or head_sha != candidate:
            raise RuntimeError("durable PR evidence does not match run candidate commit")

        project=projects[0]
        return CIFollowupItem(
            run_id=run_id,
            project_key=str(project["project_key"]),
            repository=str(project["repository"]),
            issue_number=issue_number,
            branch=branch,
            pr_number=pr_number,
            candidate_commit=candidate,
            human_gate_required=human_gate,
        )
