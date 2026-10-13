from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime,timedelta,timezone

from .supabase_server import resolve_supabase_server_config
from .preview_eligibility import is_delivery_preview_run, is_quota_blocked_candidate


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

    def _status_partitioned_rows(self, table: str, columns: str, statuses: tuple[str, ...]) -> tuple[list[dict], tuple[str, ...]]:
        """Prevent a flood of old entries in one status hiding another queue.

        All partitions are read-only; a repeated ID can occur if a run changes
        status between calls. In that case the latest observed row wins.
        """
        rows: dict[str, dict] = {}
        capped: list[str] = []
        for status in statuses:
            base = f"{table}?select={columns}&status=eq.{status}"
            oldest = self._get(
                base + "&order=created_at.asc&limit=200"
                if table == "factory_runs" else base + "&limit=200"
            )
            snapshots = [oldest]
            if isinstance(oldest, list) and len(oldest) == 200:
                capped.append(status)
                # Always retain old FIFO candidates. Include newest runs too,
                # so historic Preview/queued runs cannot crowd out fresh work.
                if table == "factory_runs":
                    snapshots.append(self._get(base + "&order=created_at.desc&limit=200"))
            for items in snapshots:
                if not isinstance(items, list) or any(
                    not isinstance(row, dict)
                    or str(row.get("status") or "") != status
                    or not isinstance(row.get("id"), str) or not row["id"]
                    for row in items
                ):
                    raise RuntimeError("invalid status-partitioned Control Plane snapshot")
                for item in items:
                    rows[item["id"]] = item
        return list(rows.values()), tuple(capped)

    def _linked_task_statuses(self, runs: list[dict], task_status: dict[str,str]) -> tuple[dict[str,str],int,int]:
        """Resolve run/task joins missed by an independently bounded task scan.

        Only exact alphanumeric/UUID task IDs returned from Control Plane are
        used in PostgREST filters; malformed IDs fail closed before URL usage.
        """
        linked = {
            str(run.get("task_id"))
            for run in runs
            if str(run.get("status") or "") in {"created", "queued"}
            and run.get("task_id") is not None
        }
        missing = sorted(linked - set(task_status))
        for task_id in missing:
            if re.fullmatch(r"[A-Za-z0-9_-]{1,64}",task_id) is None:
                raise RuntimeError("invalid linked task identifier")
        resolved = dict(task_status)
        # Bound lookups even if a legacy backlog is very large; expose that
        # truncation in durable diagnostic telemetry instead of claiming full coverage.
        bounded = missing[:400]
        for offset in range(0,len(bounded),40):
            batch=bounded[offset:offset+40]
            data=self._get(
                "factory_tasks?select=id,status,project_id&id=in.("
                + ",".join(batch) + ")&status=in.(queued,queued_execution)&limit=40"
            )
            if not isinstance(data,list) or any(
                not isinstance(t,dict)
                or t.get("id") not in batch
                or t.get("status") not in {"queued","queued_execution"}
                for t in data
            ):
                raise RuntimeError("invalid linked-task Control Plane response")
            for t in data:
                resolved[str(t["id"])]=str(t["status"])
        return resolved,len(bounded),max(0,len(missing)-len(bounded))

    def probe(self) -> dict:
        runs, capped_run_statuses = self._status_partitioned_rows(
            "factory_runs",
            "id,task_id,status,execution_route,created_at,branch_name,candidate_commit,metadata",
            ("created", "queued", "ci_pending", "preview_ready", "awaiting_release", "awaiting_codex_manual"),
        )
        tasks, capped_task_statuses = self._status_partitioned_rows(
            "factory_tasks", "id,status,project_id", ("queued", "queued_execution"),
        )
        task_status = {str(row["id"]): str(row.get("status") or "") for row in tasks}
        task_status,linked_task_lookups,linked_task_lookup_truncated = self._linked_task_statuses(runs,task_status)

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
        # Existing routed runs also need the dispatch matrix to wake executors.
        # Never use orphan tasks alone to infer executable work.
        assigned_execution_work = any(
            str(run.get("status")) == "queued"
            and str(run.get("execution_route") or "") in {"direct", "codex"}
            and task_status.get(str(run.get("task_id"))) == "queued_execution"
            for run in runs
        )
        # Both predicates must agree: a raw pending unit is only a hint and must
        # survive portfolio pause/incident/capacity rules before waking dispatch.
        # Already routed queued execution continues independently.
        dispatch_work = (pending_change_set_work and bool(portfolio_candidates)) or assigned_execution_work
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
        deliverable_previews=[run for run in preview_runs if is_delivery_preview_run(run)]
        blocked_preview_runs=set()
        if deliverable_previews:
            cutoff=(datetime.now(timezone.utc)-timedelta(hours=24)).isoformat().replace("+00:00","Z")
            blocks=self._get_optional(
                "factory_deployments?select=run_id,metadata"
                "&environment=eq.preview&status=eq.blocked_quota"
                f"&created_at=gte.{cutoff}&order=created_at.desc&limit=200"
            )
            blocked_preview_runs={
                str(run.get("id") or "") for run in deliverable_previews
                if is_quota_blocked_candidate(run,blocks)
            }

        queued_ids = {str(t["id"]) for t in tasks if t.get("status") == "queued"}
        product_ids = {str(run.get("task_id")) for run in runs if str(run.get("status")) in {"created", "queued"} and str(run.get("task_id")) in queued_ids}
        portfolio_eligible_projects = {str(row.get("project_id")) for row in portfolio_candidates if row.get("project_id")}
        eligible_queued_without_run = sum(str(t.get("project_id") or "") in portfolio_eligible_projects for t in tasks if str(t.get("id")) in queued_ids - product_ids)
        execution_task_ids = {str(t["id"]) for t in tasks if t.get("status") == "queued_execution"}
        execution_run_ids = {str(run.get("task_id")) for run in runs if str(run.get("status")) in {"created", "queued"} and str(run.get("task_id")) in execution_task_ids}
        stale_preview_runs = 0
        now = datetime.now(timezone.utc)
        for run in preview_runs:
            created_at = run.get("created_at")
            if not isinstance(created_at, str):
                continue
            try:
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if created.tzinfo is None:
                    continue
                if now - created >= timedelta(hours=24):
                    stale_preview_runs += 1
            except ValueError:
                continue
        out = {
            "queue_diagnostics": {
                "run_status_partitions_at_limit": list(capped_run_statuses),
                "task_status_partitions_at_limit": list(capped_task_statuses),
                "linked_task_lookups": linked_task_lookups,
                "linked_task_lookup_truncated": linked_task_lookup_truncated,
                "queued_tasks": len(queued_ids),
                "queued_execution_tasks": len(execution_task_ids),
                "queued_execution_without_queued_run": len(execution_task_ids - execution_run_ids),
                "eligible_product_tasks": len(product_ids),
                "pending_work_unit_hint": pending_change_set_work,
                "portfolio_dispatch_candidate_count": len(portfolio_candidates),
                "queued_without_product_run": len(queued_ids - product_ids),
                "queued_without_product_run_but_portfolio_eligible": eligible_queued_without_run,
                "queued_without_product_run_and_not_portfolio_eligible": len(queued_ids - product_ids) - eligible_queued_without_run,
                "preview_ready_runs": len(preview_runs),
                "preview_manual_audit_only_runs": len(preview_runs)-len(deliverable_previews),
                "preview_ready_older_than_24h": stale_preview_runs,
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
            "preview_work": any(str(run.get("id") or "") not in blocked_preview_runs for run in deliverable_previews),
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
