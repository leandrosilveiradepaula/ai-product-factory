from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime,timedelta,timezone

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

    def _get_optional(self, path: str) -> list[dict]:
        try:
            return self._get(path)
        except RuntimeError as exc:
            if "(404)" in str(exc):
                return []
            raise

    def _post(self, path: str, payload: dict) -> None:
        headers = {
            **self.headers,
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        req = urllib.request.Request(
            f"{self.url}/rest/v1/{path}",
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30):
            pass

    def _portfolio_dispatch_candidates(self) -> list[dict]:
        """Read-only RPC; fail closed if portfolio eligibility cannot be verified."""
        headers = {**self.headers, "Content-Type": "application/json"}
        req = urllib.request.Request(
            f"{self.url}/rest/v1/rpc/factory_portfolio_candidates",
            data=json.dumps({"p_limit": 20}).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                value = json.loads(response.read().decode())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise RuntimeError("portfolio eligibility read failed") from exc
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise RuntimeError("invalid portfolio eligibility response")
        return value

    def _record_telemetry(self, *, work_detected: bool, work_classes: list[str], queue_diagnostics: dict | None = None) -> bool:
        try:
            self._post(
                "factory_audit_events",
                {
                    "actor_type": "system",
                    "actor_ref": "schedule-probe",
                    "event_type": "schedule_probe.observed",
                    "payload": {
                        "work_detected": work_detected,
                        "work_classes": work_classes,
                        "queue_diagnostics": queue_diagnostics or {},
                    },
                },
            )
        except Exception:
            return False
        return True

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

        pending_change_set_work = bool(self._get(
            "factory_change_set_work_units?select=id&status=eq.pending&limit=1"
        ))
        # Portfolio RPC enforces project pause, worker limits and incident priority.
        # Never infer eligibility from orphan queued tasks alone.
        portfolio_candidates = self._portfolio_dispatch_candidates()
        dispatch_work = pending_change_set_work or bool(portfolio_candidates)
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

        github_access_work = bool(self._get_optional(
            "factory_project_github_access?select=project_id"
            "&status=in.(unverified,stale)&limit=1"
        ))

        preview_runs=[run for run in runs if str(run.get("status"))=="preview_ready"]
        blocked_preview_runs=set()
        if preview_runs:
            cutoff=(datetime.now(timezone.utc)-timedelta(hours=24)).isoformat().replace("+00:00","Z")
            blocked_preview_runs={
                str(row.get("run_id") or "")
                for row in self._get_optional(
                    "factory_deployments?select=run_id"
                    "&environment=eq.preview&status=eq.blocked_quota"
                    f"&created_at=gte.{cutoff}&limit=200"
                )
            }

        queued_ids = {str(t["id"]) for t in tasks if t.get("status") == "queued"}
        product_ids = {str(run.get("task_id")) for run in runs if str(run.get("status")) in {"created", "queued"} and str(run.get("task_id")) in queued_ids}
        out = {
            "queue_diagnostics": {
                "queued_tasks": len(queued_ids),
                "queued_execution_tasks": sum(t.get("status") == "queued_execution" for t in tasks),
                "eligible_product_tasks": len(product_ids),
                "queued_without_product_run": len(queued_ids - product_ids),
                "preview_ready_runs": len(preview_runs),
                "preview_quota_blocked_runs": sum(str(run.get("id") or "") in blocked_preview_runs for run in preview_runs),
            },
            "github_access_work": github_access_work,
            "product_work": product_work,
            "dispatch_work": dispatch_work,
            "integration_work": integration_work,
            "ci_work": any(str(run.get("status")) == "ci_pending" for run in runs),
            "specialist_work": bool(specialist_roles),
            "specialist_roles": specialist_roles,
            "specialist_security_work": "security" in specialist_roles,
            "specialist_qa_work": "qa" in specialist_roles,
            "specialist_operations_work": "operations" in specialist_roles,
            "preview_work": any(str(run.get("id") or "") not in blocked_preview_runs for run in preview_runs),
            "release_work": any(str(run.get("status")) == "awaiting_release" for run in runs),
            "codex_manual_work": codex_manual_work,
        }
        out["work_detected"] = any(
            bool(out[key])
            for key in (
                "github_access_work",
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
        work_classes = [
            work_class
            for work_class, key in (
                ("github_access", "github_access_work"),
                ("product", "product_work"),
                ("dispatch", "dispatch_work"),
                ("integration", "integration_work"),
                ("ci", "ci_work"),
                ("specialist_security", "specialist_security_work"),
                ("specialist_qa", "specialist_qa_work"),
                ("specialist_operations", "specialist_operations_work"),
                ("preview", "preview_work"),
                ("release", "release_work"),
                ("codex_manual", "codex_manual_work"),
            )
            if out[key]
        ]
        out["telemetry_recorded"] = self._record_telemetry(
            work_detected=out["work_detected"],
            work_classes=work_classes,
            queue_diagnostics=out["queue_diagnostics"],
        )
        return out
