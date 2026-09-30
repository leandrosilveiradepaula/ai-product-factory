from __future__ import annotations

import json
import urllib.error
import urllib.request

from .supabase_server import resolve_supabase_server_config


class SupabaseScheduleProbe:
    """Read-only scheduler probe used to avoid starting idle GitHub-hosted runners."""

    def __init__(self, *, url: str | None = None, secret_key: str | None = None, service_role_key: str | None = None) -> None:
        cfg = resolve_supabase_server_config(url=url, secret_key=secret_key, service_role_key=service_role_key)
        self.url = cfg.url
        self.headers = cfg.headers

    def _get(self, path: str) -> list[dict]:
        req = urllib.request.Request(f"{self.url}/rest/v1/{path}", headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane read failed: {path} ({exc.code})") from exc
        return [] if not raw else json.loads(raw)

    def probe(self) -> dict:
        runs = self._get(
            "factory_runs?select=id,task_id,status,execution_route"
            "&status=in.(created,queued,ci_pending,preview_ready,awaiting_release,awaiting_codex_manual)"
            "&order=created_at.asc&limit=200"
        )
        tasks = self._get(
            "factory_tasks?select=id,status"
            "&status=in.(queued,queued_execution)&limit=200"
        )
        task_status = {str(row["id"]): str(row.get("status") or "") for row in tasks}

        product_work = any(
            str(run.get("status")) in {"created", "queued"}
            and task_status.get(str(run.get("task_id"))) == "queued"
            for run in runs
        )
        codex_manual_work = any(
            str(run.get("status")) == "awaiting_codex_manual"
            or (
                str(run.get("status")) == "queued"
                and str(run.get("execution_route") or "") == "codex"
                and task_status.get(str(run.get("task_id"))) == "queued_execution"
            )
            for run in runs
        )

        dispatch_work = bool(self._get(
            "factory_change_set_work_units?select=id&status=eq.pending&limit=1"
        ))
        integration_work = bool(self._get(
            "factory_change_sets?select=id&status=in.(building,integrating)&limit=1"
        ))
        lanes = self._get(
            "factory_specialist_lane_jobs?select=role&status=eq.queued&limit=20"
        )
        specialist_roles = sorted({
            str(row.get("role") or "")
            for row in lanes
            if str(row.get("role") or "") in {"security", "qa", "operations"}
        })

        out = {
            "product_work": product_work,
            "dispatch_work": dispatch_work,
            "integration_work": integration_work,
            "ci_work": any(str(run.get("status")) == "ci_pending" for run in runs),
            "specialist_work": bool(specialist_roles),
            "specialist_roles": specialist_roles,
            "preview_work": any(str(run.get("status")) == "preview_ready" for run in runs),
            "release_work": any(str(run.get("status")) == "awaiting_release" for run in runs),
            "codex_manual_work": codex_manual_work,
        }
        out["work_detected"] = any(
            bool(out[key])
            for key in (
                "product_work",
                "dispatch_work",
                "integration_work",
                "ci_work",
                "specialist_work",
                "preview_work",
                "release_work",
                "codex_manual_work",
            )
        )
        return out
