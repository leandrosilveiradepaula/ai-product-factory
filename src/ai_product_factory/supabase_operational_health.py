from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

from .operational_alerts import OperationalHealth
from .cost_observability import requires_cost_estimate
from .supabase_server import resolve_supabase_server_config


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

    def read(self, *, budget: Decimal | None = None, now: datetime | None = None) -> OperationalHealth:
        now=now or datetime.now(timezone.utc)
        runs=self._get("factory_runs?select=status,attempt_count,last_error,lease_expires_at&order=created_at.desc&limit=200")
        usage=self._get("factory_tool_usage?select=tool_family,estimated_cost&order=created_at.desc&limit=1000")
        expired=0
        dead=0
        failed=0
        for row in runs:
            status=str(row.get("status") or "")
            lease=_parse_time(row.get("lease_expires_at"))
            if lease is not None and lease < now and status in {"running","implementing","preparing_codex_manual"}:
                expired+=1
            if status == "failed":
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
                known+=Decimal(str(value))
        return OperationalHealth(expired_leases=expired,dead_letter_runs=dead,failed_runs=failed,unknown_cost_events=unknown,known_cost=known,budget=budget)
