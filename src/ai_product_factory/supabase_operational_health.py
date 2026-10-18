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
MAX_USAGE_BIGINT = (1 << 63) - 1
RUN_PAGE_SIZE = 200
MAX_RUN_PAGES = 20
FAILED_TASK_BATCH = 100
# Includes historical and active phases. Unknown strings fail closed rather than
# being silently dropped from all health counters.
KNOWN_RUN_STATUSES = frozenset({
    "created", "queued", "pending", "running", "implementing",
    "preparing_codex_manual", "awaiting_codex_manual", "awaiting_release",
    "awaiting_gate", "awaiting_human", "awaiting_ci", "ci_pending",
    "review_ready", "specialist_review_pending", "repair_pending",
    "preview_ready", "completed", "integrated", "merged",
    "failed", "cancelled", "blocked", "planning", "routing",
})


def _usage_identity(value: object) -> str:
    """Canonical PostgreSQL bigint primary key as JSON number or decimal text.

    Reject booleans (subclasses of int), floats, malformed values and values
    outside the signed bigint range. Canonicalize before deduplicating.
    """
    if isinstance(value, bool):
        raise RuntimeError("cost usage inventory has invalid ID")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.isascii() and value.isdecimal():
        parsed = int(value)
    else:
        raise RuntimeError("cost usage inventory has invalid ID")
    if not 0 < parsed <= MAX_USAGE_BIGINT:
        raise RuntimeError("cost usage inventory has invalid ID")
    return str(parsed)



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
                identity = _usage_identity(row.get("id"))
                if identity in seen:
                    raise RuntimeError("cost usage inventory has invalid or duplicate ID")
                if not isinstance(row.get("tool_family"), str) or not row["tool_family"].strip():
                    raise RuntimeError("cost usage inventory has invalid tool family")
                seen.add(identity)
                usage.append(row)
            if len(batch) < USAGE_PAGE_SIZE:
                return usage
        raise RuntimeError("cost usage inventory exceeded verified pagination boundary")

    def _all_runs(self) -> list[dict]:
        """Enumerate the run ledger fully or refuse a partial health report.

        Stable created_at/id ordering plus identity validation detects overlap.
        Offset pagination remains subject to concurrent insertions; a duplicate
        or out-of-order page must fail closed, not suppress old incidents.
        """
        seen: set[str] = set()
        runs: list[dict] = []
        last_time: datetime | None = None
        last_id: str | None = None
        for page in range(MAX_RUN_PAGES):
            batch=self._get(
                "factory_runs?select=id,task_id,status,attempt_count,last_error,lease_expires_at,created_at"
                "&order=created_at.desc,id.desc"
                f"&limit={RUN_PAGE_SIZE}&offset={page*RUN_PAGE_SIZE}"
            )
            if not isinstance(batch,list) or len(batch)>RUN_PAGE_SIZE:
                raise RuntimeError("run health inventory is not a bounded array")
            for row in batch:
                if not isinstance(row,dict):
                    raise RuntimeError("run health inventory contains malformed row")
                identity=row.get("id")
                if not isinstance(identity,str) or not identity.strip() or identity in seen:
                    raise RuntimeError("run health inventory has invalid or duplicate ID")
                if row.get("status") not in KNOWN_RUN_STATUSES:
                    raise RuntimeError("run health inventory contains unknown status")
                created=row.get("created_at")
                if created is not None:
                    try:
                        when=_parse_time(created)
                    except (ValueError,TypeError,AttributeError) as exc:
                        raise RuntimeError("run health inventory has invalid creation time") from exc
                    if when is None or when.tzinfo is None or when.utcoffset() is None:
                        raise RuntimeError("run health inventory has invalid creation time")
                    if last_time is not None and (
                        when>last_time or (when==last_time and last_id is not None and identity>last_id)
                    ):
                        raise RuntimeError("run health inventory is not sorted by timestamp and ID")
                    last_time=when
                    last_id=identity
                seen.add(identity)
                runs.append(row)
            if len(batch)<RUN_PAGE_SIZE:
                return runs
        raise RuntimeError("run health inventory exceeded verified pagination boundary")

    def read(self, *, budget: Decimal | None = None, now: datetime | None = None) -> OperationalHealth:
        now=now or datetime.now(timezone.utc)
        runs=self._all_runs()
        task_ids=sorted({str(row.get("task_id") or "") for row in runs if row.get("task_id") and row.get("status")=="failed"})
        task_status_by_id={}
        for start in range(0,len(task_ids),FAILED_TASK_BATCH):
            batch_ids=task_ids[start:start+FAILED_TASK_BATCH]
            encoded=",".join(batch_ids)
            tasks=self._get(f"factory_tasks?select=id,status&id=in.({encoded})")
            if not isinstance(tasks,list) or any(not isinstance(row,dict) for row in tasks):
                raise RuntimeError("failed task health lookup is malformed")
            statuses={str(row.get("id")):row.get("status") for row in tasks}
            if (set(statuses)!=set(batch_ids) or len(tasks)!=len(batch_ids)
                    or any(not isinstance(status,str) or not status.strip() for status in statuses.values())):
                raise RuntimeError("failed task health lookup is incomplete")
            task_status_by_id.update(statuses)
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
