from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote

from .supabase_server import resolve_supabase_server_config


@dataclass(frozen=True)
class ReleaseFollowupItem:
    run_id: str
    project_id: str
    project_key: str
    repository: str
    issue_number: int | None
    branch: str
    pr_number: int
    candidate_commit: str
    risk: dict
    merge_sha: str | None = None
    release_source: str = "delivery"


class SupabaseReleaseFollowupQueue:
    """Read-only selector for one run waiting on a human PR merge."""

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

    def next_pending(self) -> ReleaseFollowupItem | None:
        runs=self._get("factory_runs?select=id,task_id,branch_name,candidate_commit,metadata&status=eq.awaiting_release&order=created_at.asc&limit=1")
        if not runs:
            return None
        run=runs[0]
        run_id=str(run["id"])
        task_id=str(run["task_id"])
        candidate=str(run.get("candidate_commit") or "")
        branch=str(run.get("branch_name") or "")
        issue_data=(run.get("metadata") or {}).get("github_issue") or {}
        issue_number=int(issue_data.get("number") or 0) or None
        if not candidate or not branch:
            raise RuntimeError("awaiting_release run is missing candidate or branch")

        tasks=self._get(f"factory_tasks?select=project_id,risk&id=eq.{quote(task_id)}&limit=1")
        if not tasks:
            raise RuntimeError("awaiting_release run task was not found")
        project_id=str(tasks[0]["project_id"])
        projects=self._get(f"factory_projects?select=project_key,repository&id=eq.{quote(project_id)}&limit=1")
        if not projects or not projects[0].get("repository"):
            raise RuntimeError("awaiting_release run project repository is not configured")

        reports=self._get(
            f"factory_release_reports?select=status,candidate_commit,report&run_id=eq.{quote(run_id)}&order=created_at.desc&limit=1"
        )
        if reports and str(reports[0].get("status") or "")=="released":
            report=reports[0]
            report_candidate=str(report.get("candidate_commit") or "")
            payload=report.get("report") or {}
            pr_number=int(payload.get("pr_number") or 0)
            merge_sha=str(payload.get("merge_sha") or "")
            if report_candidate!=candidate or pr_number<1 or not merge_sha:
                raise RuntimeError("released report does not match run candidate or lacks merge evidence")
            project=projects[0]
            return ReleaseFollowupItem(
                run_id=run_id,project_id=project_id,project_key=str(project["project_key"]),repository=str(project["repository"]),
                issue_number=issue_number,branch=branch,pr_number=pr_number,candidate_commit=candidate,
                risk=tasks[0].get("risk") or {},merge_sha=merge_sha,release_source="console_report",
            )

        if issue_number is None:
            raise RuntimeError("awaiting_release run without a released report requires GitHub issue binding")

        usage=self._get(f"factory_tool_usage?select=metadata,operation&run_id=eq.{quote(run_id)}&operation=in.(verified_preview_awaiting_human_merge,preview_not_required_awaiting_human_merge)&order=created_at.desc&limit=1")
        if not usage:
            raise RuntimeError("awaiting_release run has no durable release-readiness evidence")
        meta=usage[0].get("metadata") or {}
        pr_number=int(meta.get("pr") or 0)
        head_sha=str(meta.get("head_sha") or "")
        if pr_number < 1 or head_sha != candidate:
            raise RuntimeError("release-readiness evidence does not match run candidate commit")

        project=projects[0]
        return ReleaseFollowupItem(
            run_id=run_id,project_id=project_id,project_key=str(project["project_key"]),repository=str(project["repository"]),
            issue_number=issue_number,branch=branch,pr_number=pr_number,candidate_commit=candidate,
            risk=tasks[0].get("risk") or {},
        )
