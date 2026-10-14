"""Read-only scheduler liveness using durable schedule_probe.observed events.

This observer can detect missing wakeups or long gaps only when an alert
evaluation actually runs. It never claims guaranteed background delivery.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import json
import urllib.error
import urllib.request

from .operational_alerts import OperationalAlert
from .supabase_server import resolve_supabase_server_config

MAX_GAP = timedelta(hours=2)


@dataclass(frozen=True)
class SchedulerLiveness:
    latest: datetime | None
    previous: datetime | None
    checked_at: datetime
    gap: timedelta | None
    age: timedelta | None


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("scheduler heartbeat has no valid timestamp")
    try:
        out = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("scheduler heartbeat has malformed timestamp") from exc
    if out.tzinfo is None or out.utcoffset() is None:
        raise RuntimeError("scheduler heartbeat has no timezone")
    return out.astimezone(timezone.utc)


class SupabaseSchedulerLivenessReader:
    def __init__(self, *, url: str | None = None,
                 secret_key: str | None = None,
                 service_role_key: str | None = None) -> None:
        cfg = resolve_supabase_server_config(
            url=url, secret_key=secret_key, service_role_key=service_role_key
        )
        self.url, self.headers = cfg.url, cfg.headers

    def read(self, *, now: datetime | None = None) -> SchedulerLiveness:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("scheduler check requires timezone-aware now")
        now = now.astimezone(timezone.utc)
        path = (
            "factory_audit_events?select=created_at"
            "&event_type=eq.schedule_probe.observed"
            "&order=created_at.desc&limit=2"
        )
        request = urllib.request.Request(
            f"{self.url}/rest/v1/{path}", headers=self.headers, method="GET"
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError("scheduler heartbeat read unavailable") from exc
        try:
            rows = [] if not raw else json.loads(raw)
        except ValueError as exc:
            raise RuntimeError("scheduler heartbeat response is invalid JSON") from exc
        if not isinstance(rows, list) or len(rows) > 2:
            raise RuntimeError("scheduler heartbeat response is not bounded")
        if any(not isinstance(row, dict) for row in rows):
            raise RuntimeError("scheduler heartbeat response contains malformed rows")
        stamps = [_timestamp(row.get("created_at")) for row in rows]
        if any(stamp > now + timedelta(minutes=2) for stamp in stamps):
            raise RuntimeError("scheduler heartbeat is in the future")
        if len(stamps) == 2 and stamps[1] > stamps[0]:
            raise RuntimeError("scheduler heartbeat is not sorted newest first")
        latest = stamps[0] if stamps else None
        previous = stamps[1] if len(stamps) == 2 else None
        return SchedulerLiveness(
            latest=latest, previous=previous, checked_at=now,
            gap=latest-previous if previous is not None else None,
            age=max(now-latest, timedelta(0)) if latest is not None else None
        )


def evaluate_scheduler_liveness(state: SchedulerLiveness) -> tuple[OperationalAlert, ...]:
    if state.latest is None:
        return (OperationalAlert(
            "scheduler_gap", "warning",
            "No durable scheduler probe has been observed; verify GitHub Actions schedule"
        ),)
    if state.age is not None and state.age >= MAX_GAP:
        minutes = int(state.age.total_seconds()//60)
        return (OperationalAlert(
            "scheduler_gap", "warning",
            f"Last durable scheduler probe is {minutes} minutes old (expected best-effort twice hourly)"
        ),)
    if state.gap is not None and state.gap >= MAX_GAP:
        minutes = int(state.gap.total_seconds()//60)
        return (OperationalAlert(
            "scheduler_gap", "warning",
            f"Recent scheduler probes were {minutes} minutes apart (best-effort cadence gap)"
        ),)
    return ()
