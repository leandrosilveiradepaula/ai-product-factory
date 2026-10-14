"""Read-only GitHub Actions completion evidence for the native Factory scheduler.

A persisted native heartbeat proves the scheduled job started its work probe,
not that its entire workflow succeeded. This independent health observation
does not start, retry, dispatch, or merge any workflow.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .operational_alerts import OperationalAlert

WORKFLOW_PATH = ".github/workflows/autonomous-runner.yml"
PAGE_SIZE = 30
MAX_AGE = timedelta(hours=2)


@dataclass(frozen=True)
class NativeScheduleRun:
    run_id: int
    created_at: datetime
    conclusion: str


@dataclass(frozen=True)
class NativeScheduleHealth:
    completed: tuple[NativeScheduleRun, ...]
    checked_at: datetime


def _time(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("native scheduler run has invalid timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("native scheduler run has malformed timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise RuntimeError("native scheduler run has no timezone")
    return result.astimezone(timezone.utc)


class GithubNativeScheduledRunReader:
    """Use the existing read-only Actions API from the same repository client."""

    def __init__(self, github: Any):
        self.github = github

    def read(self, *, now: datetime | None = None) -> NativeScheduleHealth:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("native scheduler check requires timezone-aware now")
        now = now.astimezone(timezone.utc)
        data = self.github._call(
            "GET",
            f"/repos/{self.github.repository}/actions/runs",
            query={"event": "schedule", "per_page": str(PAGE_SIZE)},
        )
        if not isinstance(data, dict):
            raise RuntimeError("native scheduler run inventory is not an object")
        rows = data.get("workflow_runs")
        if not isinstance(rows, list) or len(rows) > PAGE_SIZE:
            raise RuntimeError("native scheduler run inventory is incomplete or malformed")
        completed: list[NativeScheduleRun] = []
        seen: set[int] = set()
        previous_time: datetime | None = None
        for row in rows:
            if not isinstance(row, dict):
                raise RuntimeError("native scheduler run inventory contains malformed row")
            if row.get("path") != WORKFLOW_PATH:
                continue
            if (row.get("event") != "schedule"
                    or row.get("head_branch") != "main"
                    or (row.get("repository") or {}).get("full_name") != self.github.repository):
                raise RuntimeError("native scheduler run has untrusted origin")
            run_id = row.get("id")
            if type(run_id) is not int or run_id <= 0 or run_id in seen:
                raise RuntimeError("native scheduler run has invalid or duplicate ID")
            seen.add(run_id)
            created_at = _time(row.get("created_at"))
            if created_at > now + timedelta(minutes=5):
                raise RuntimeError("native scheduler run is in the future")
            if previous_time is not None and created_at > previous_time:
                raise RuntimeError("native scheduler runs are not sorted newest first")
            previous_time = created_at
            status = row.get("status")
            if status == "completed":
                conclusion = row.get("conclusion")
                if not isinstance(conclusion, str) or not conclusion:
                    raise RuntimeError("completed native scheduler run has no conclusion")
                completed.append(NativeScheduleRun(run_id, created_at, conclusion))
            elif status not in ("queued", "in_progress", "requested", "waiting", "pending"):
                raise RuntimeError("native scheduler run has unknown status")
        # Exclude in-progress schedules: a run cannot yet certify its own success.
        # We intentionally keep failures among the last two completed runs.
        return NativeScheduleHealth(tuple(completed[:2]), now)


def evaluate_native_scheduler_health(state: NativeScheduleHealth) -> tuple[OperationalAlert, ...]:
    finished = state.completed
    if len(finished) < 2:
        return (OperationalAlert(
            "scheduler_pipeline", "warning",
            "Fewer than two completed native Factory scheduler workflows are available",
        ),)
    latest, previous = finished
    age = state.checked_at - latest.created_at
    gap = latest.created_at - previous.created_at
    if age >= MAX_AGE or gap <= timedelta(0) or gap >= MAX_AGE:
        return (OperationalAlert(
            "scheduler_pipeline", "warning",
            "Native Factory scheduler workflow completions are stale or too far apart",
        ),)
    if latest.conclusion != "success" or previous.conclusion != "success":
        return (OperationalAlert(
            "scheduler_pipeline", "warning",
            f"Native Factory scheduler run #{latest.run_id} concluded {latest.conclusion}; "
            f"previous run #{previous.run_id} concluded {previous.conclusion}. "
            "Two timely completed successes are required",
        ),)
    return ()
