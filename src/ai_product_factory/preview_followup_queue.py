from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from .preview_eligibility import is_delivery_preview_run, is_quota_blocked_candidate

from .supabase_server import resolve_supabase_server_config
from .followup_execution_epoch import run_followup_epoch
from .followup_active_project_query import active_project_followup_query
from .candidate_pr_receipt import validate_create_pr_candidate


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
    execution_generation: int | None = None
    require_execution_generation: bool = False


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

    def next_pending(self, *, exclude_run_ids: tuple[str, ...] = ()) -> PreviewFollowupItem | None:
        # A paused or quota-blocked candidate must not starve active delivery.
        if (not isinstance(exclude_run_ids, tuple) or len(exclude_run_ids)>12
            or any(not isinstance(x,str) or not x.strip() for x in exclude_run_ids)):
            raise ValueError("invalid bounded Preview exclusion set")
        ignored=set(exclude_run_ids)
        runs=self._get(
            active_project_followup_query(status="preview_ready",limit=50)
        )
        if not runs:
            return None
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=24)).isoformat().replace("+00:00","Z")
        run=None
        for row in runs:
            if not isinstance(row,dict) or not isinstance(row.get("id"),str):
                raise RuntimeError("invalid Preview candidate identity")
            if row["id"] in ignored or not is_delivery_preview_run(row):
                continue
            blocks=self._get(
                "factory_deployments?select=run_id,metadata"
                "&environment=eq.preview&status=eq.blocked_quota"
                f"&run_id=eq.{quote(str(row['id']))}&created_at=gte.{cutoff}"
                "&order=created_at.desc&limit=20"
            )
            if is_quota_blocked_candidate(row,blocks):
                continue
            run=row
            break
        if run is None:
            return None
        execution_generation, require_execution_generation = run_followup_epoch(run)
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
        validate_create_pr_candidate(
            read=self._get,run_id=run_id,pr_number=pr_number,
            original_head=head_sha,candidate_commit=candidate,
            run_metadata=run.get("metadata") or {},
        )

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
            execution_generation=execution_generation,
            require_execution_generation=require_execution_generation,
        )
