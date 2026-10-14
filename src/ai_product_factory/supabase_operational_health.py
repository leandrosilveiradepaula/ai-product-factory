from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from .operational_alerts import OperationalHealth
from .cost_observability import requires_cost_estimate
from .preview_eligibility import is_delivery_preview_run
from .supabase_server import resolve_supabase_server_config

USAGE_PAGE_SIZE = 1000
MAX_USAGE_PAGES = 20


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class SupabaseOperationalHealthReader:
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

    def _all_usage(self) -> list[dict]:
        """Read the cost inventory completely or reject a partial budget total.

        Order by timestamp and ID to make page boundaries deterministic. IDs
        also expose offset shifts/duplicate rows if the inventory is changing.
        This is observability only; actual paid execution uses its own ledger.
        """
        seen: set[str] = set()
        usage: list[dict] = []
        for page in range(MAX_USAGE_PAGES):
            offset = page * USAGE_PAGE_SIZE
            batch = self._get(
                "factory_tool_usage?select=id,tool_family,estimated_cost"
                "&order=created_at.desc,id.desc"
                f"&limit={USAGE_PAGE_SIZE}&offset={offset}"
            )
            if not isinstance(batch, list) or len(batch) > USAGE_PAGE_SIZE:
                raise RuntimeError("cost usage inventory is not a bounded array")
            for row in batch:
                if not isinstance(row, dict):
                    raise RuntimeError("cost usage inventory includes malformed row")
                identity = row.get("id")
                if not isinstance(identity, str) or not identity.strip() or identity in seen:
                    raise RuntimeError("cost usage inventory has invalid or duplicate ID")
                if not isinstance(row.get("tool_family"), str) or not row["tool_family"].strip():
                    raise RuntimeError("cost usage inventory has invalid tool family")
                seen.add(identity)
                usage.append(row)
            if len(batch) < USAGE_PAGE_SIZE:
                return usage
        raise RuntimeError("cost usage inventory exceeded verified pagination boundary")

    def read(self, *, budget: Decimal | None = None, now: datetime | None = None) -> OperationalHealth:
        now=now or datetime.now(timezone.utc)
        runs=self._get("factory_runs?select=id,task_id,status,attempt_count,last_error,lease_expires_at,created_at&order=created_at.desc&limit=200")
        task_ids=sorted({str(row.get("task_id") or "") for row in runs if row.get("task_id") and row.get("status")=="failed"})
        task_status_by_id={}
        if task_ids:
            encoded=",".join(task_ids)
            tasks=self._get(f"factory_tasks?select=id,status&id=in.({encoded})")
            if not isinstance(tasks, list) or any(not isinstance(row, dict) for row in tasks):
                raise RuntimeError("failed task health lookup is malformed")
            task_status_by_id={str(row.get("id")):str(row.get("status") or "") for row in tasks}
            if set(task_status_by_id) != set(task_ids) or len(tasks) != len(task_ids):
                raise RuntimeError("failed task health lookup is incomplete")
        # Delivery eligibility must match the Preview queue. Historical manual
        # audits stay visible in the Control Plane, but are not delivery work.
        preview_runs=self._get(
            "factory_runs?select=id,created_at,metadata"
            "&status=eq.preview_ready&order=created_at.asc&limit=201"
        )
        if not isinstance(preview_runs,list) or len(preview_runs)>200:
            raise RuntimeError("preview health scan exceeded its verified 200-run boundary")
        stale_preview=0
        for row in preview_runs:
            if not isinstance(row,dict):
                raise RuntimeError("malformed preview health row")
            if not is_delivery_preview_run(row):
                continue
            created=_parse_time(row.get("created_at"))
            if created is None or created.tzinfo is None:
                raise RuntimeError("delivery preview run has no valid creation time")
            if now-created >= timedelta(hours=24):
                stale_preview+=1
        usage=self._all_usage()
        expired=0
        dead=0
        failed=0
        for row in runs:
            status=str(row.get("status") or "")
            lease=_parse_time(row.get("lease_expires_at"))
            if lease is not None and lease < now and status in {"running","implementing","preparing_codex_manual"}:
                expired+=1
            if status == "failed" and task_status_by_id.get(str(row.get("task_id") or ""))=="failed":
                failed+=1
                if "maximum attempts" in str(row.get("last_error") or "").lower():
                    dead+=1
        known=Decimal("0")
        unknown=0
        for row in usage:
            value=row.get("estimated_cost")
            if value is None:
                if requires_cost_estimate(row.get("tool_family")):
                    unknown+=1
            else:
                try:
                    cost = Decimal(str(value))
                except (ValueError, ArithmeticError) as exc:
                    raise RuntimeError("cost usage inventory contains invalid amount") from exc
                if not cost.is_finite() or cost < 0:
                    raise RuntimeError("cost usage inventory contains invalid amount")
                known += cost
        return OperationalHealth(expired_leases=expired,dead_letter_runs=dead,failed_runs=failed,unknown_cost_events=unknown,known_cost=known,budget=budget,stale_preview_runs=stale_preview)
