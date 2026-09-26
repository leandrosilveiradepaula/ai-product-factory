from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from .execution_worker import DirectExecutionItem
from .supabase_server import resolve_supabase_server_config


class SupabaseCodexRunQueue:
    """Optimistically claims one queued Codex run without requiring a new database RPC."""

    def __init__(self, *, url: str | None = None, secret_key: str | None = None, service_role_key: str | None = None) -> None:
        cfg=resolve_supabase_server_config(url=url,secret_key=secret_key,service_role_key=service_role_key)
        self.url=cfg.url
        self.headers=cfg.headers

    def _request(self, method: str, path: str, payload=None, *, return_rows: bool = True):
        headers={**self.headers,"Content-Type":"application/json"}
        if method in {"PATCH","POST"}:
            headers["Prefer"]="return=representation" if return_rows else "return=minimal"
        data=None if payload is None else json.dumps(payload).encode()
        req=urllib.request.Request(f"{self.url}/rest/v1/{path}",data=data,headers=headers,method=method)
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane request failed: {method} {path} ({exc.code})") from exc
        return [] if not raw else json.loads(raw)

    def _get(self,path:str):
        return self._request("GET",path)

    def claim_next(self,worker_id:str)->DirectExecutionItem|None:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        candidates=self._get("factory_runs?select=id,task_id,metadata,started_at,attempt_count&status=eq.queued&execution_route=eq.codex&order=created_at.asc&limit=10")
        for run in candidates:
            run_id=str(run["id"])
            task_id=str(run["task_id"])
            tasks=self._get(f"factory_tasks?select=id,project_id,title,description,status&id=eq.{quote(task_id)}&status=eq.queued_execution&limit=1")
            if not tasks:
                continue
            task=tasks[0]
            project_id=str(task["project_id"])
            projects=self._get(f"factory_projects?select=project_key,repository&id=eq.{quote(project_id)}&is_active=eq.true&limit=1")
            if not projects or not projects[0].get("repository"):
                continue
            project=projects[0]
            metadata=dict(run.get("metadata") or {})
            if bool(metadata.get("human_gate_required",False)):
                continue

            now=datetime.now(timezone.utc)
            claimed_meta={**metadata,"execution_worker_id":worker_id,"execution_claimed_at":now.isoformat(),"codex_claim":True}
            claimed=self._request(
                "PATCH",
                f"factory_runs?id=eq.{quote(run_id)}&status=eq.queued&execution_route=eq.codex",
                {
                    "status":"implementing",
                    "started_at":run.get("started_at") or now.isoformat(),
                    "lease_owner":worker_id,
                    "lease_expires_at":(now+timedelta(minutes=30)).isoformat(),
                    "attempt_count":int(run.get("attempt_count") or 0)+1,
                    "metadata":claimed_meta,
                },
            )
            if not claimed:
                continue

            task_rows=self._request(
                "PATCH",
                f"factory_tasks?id=eq.{quote(task_id)}&status=eq.queued_execution",
                {"status":"implementing","updated_at":now.isoformat()},
            )
            if not task_rows:
                self._request(
                    "PATCH",
                    f"factory_runs?id=eq.{quote(run_id)}&status=eq.implementing&lease_owner=eq.{quote(worker_id)}",
                    {"status":"queued","lease_owner":None,"lease_expires_at":None,"metadata":metadata},
                )
                continue

            self._request(
                "POST",
                "factory_audit_events",
                {
                    "project_id":project_id,
                    "task_id":task_id,
                    "run_id":run_id,
                    "actor_type":"system",
                    "actor_ref":worker_id,
                    "event_type":"execution.codex.claimed",
                    "payload":{"repository":project["repository"]},
                },
                return_rows=False,
            )
            return DirectExecutionItem(
                run_id,task_id,str(project["project_key"]),str(project["repository"]),None,
                str(task["title"]),str(task.get("description") or ""),f"factory/task-{task_id}",False,
            )
        return None
