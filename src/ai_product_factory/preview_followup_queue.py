from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote

from .supabase_server import resolve_supabase_server_config


@dataclass(frozen=True)
class PreviewFollowupItem:
    run_id: str
    project_id: str
    project_key: str
    repository: str
    manifest: dict
    issue_number: int
    branch: str
    pr_number: int
    candidate_commit: str
    risk: dict


class SupabasePreviewFollowupQueue:
    """Read-only selector for one run that has green CI + quality gate evidence."""

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

    def next_pending(self) -> PreviewFollowupItem | None:
        runs=self._get("factory_runs?select=id,task_id,branch_name,candidate_commit,metadata&status=eq.preview_ready&order=created_at.asc&limit=1")
        if not runs:
            return None
        run=runs[0]
        run_id=str(run["id"])
        task_id=str(run["task_id"])
        candidate=str(run.get("candidate_commit") or "")
        branch=str(run.get("branch_name") or "")
        issue_data=(run.get("metadata") or {}).get("github_issue") or {}
        issue_number=int(issue_data.get("number") or 0)
        if not candidate or not branch or issue_number < 1:
            raise RuntimeError("preview_ready run is missing candidate, branch, or GitHub issue binding")

        tasks=self._get(f"factory_tasks?select=project_id,risk&id=eq.{quote(task_id)}&limit=1")
        if not tasks:
            raise RuntimeError("preview_ready run task was not found")
        project_id=str(tasks[0]["project_id"])
        projects=self._get(f"factory_projects?select=project_key,repository,manifest&id=eq.{quote(project_id)}&limit=1")
        if not projects or not projects[0].get("repository"):
            raise RuntimeError("preview_ready run project repository is not configured")

        usage=self._get(f"factory_tool_usage?select=metadata&run_id=eq.{quote(run_id)}&operation=eq.create_pr&order=created_at.desc&limit=1")
        if not usage:
            raise RuntimeError("preview_ready run has no durable PR evidence")
        pr_meta=usage[0].get("metadata") or {}
        pr_number=int(pr_meta.get("pr") or 0)
        head_sha=str(pr_meta.get("head_sha") or "")
        if pr_number < 1 or head_sha != candidate:
            raise RuntimeError("durable PR evidence does not match preview candidate")

        gate=self._get(f"factory_evaluations?select=status,baseline_ref,result&run_id=eq.{quote(run_id)}&eval_type=eq.quality_gate&status=eq.success&order=created_at.desc&limit=1")
        if not gate:
            raise RuntimeError("preview_ready run has no successful quality gate evidence")
        gate_row=gate[0]
        if str(gate_row.get("baseline_ref") or "") != candidate or (gate_row.get("result") or {}).get("passed") is not True:
            raise RuntimeError("quality gate evidence does not match preview candidate")

        project=projects[0]
        return PreviewFollowupItem(
            run_id=run_id,project_id=project_id,project_key=str(project["project_key"]),repository=str(project["repository"]),
            manifest=project.get("manifest") or {},issue_number=issue_number,branch=branch,pr_number=pr_number,candidate_commit=candidate,
            risk=tasks[0].get("risk") or {},
        )
