"""Schedule work probing and durable, sanitized probe observations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


_AUDIT_EVENT_TYPE = "schedule_probe.observed"


def _normalized_work_classes(probe_flags: Mapping[str, bool]) -> list[str]:
    """Return the stable work classes represented by positive probe flags.

    The probe flags are the source of truth for both routing and telemetry.  Do
    not use work-item data here: an audit observation is intentionally only a
    summary of the probe outcome.
    """

    return sorted(
        {
            flag.strip().lower().replace("_", "-")
            for flag, detected in probe_flags.items()
            if detected and flag.strip()
        }
    )


def persist_schedule_probe_observation(
    audit_events: Any,
    *,
    probe_flags: Mapping[str, bool],
) -> None:
    """Persist the sanitized result of a successfully completed schedule probe.

    ``audit_events`` is the existing ``factory_audit_events`` table handle
    (for example, ``supabase.table("factory_audit_events")``).  Deliberately
    omit ``created_at`` so the ledger's database default remains the durable
    observation timestamp.
    """

    work_classes = _normalized_work_classes(probe_flags)
    payload = {
        "work_detected": bool(work_classes),
        "work_classes": work_classes,
    }

    audit_events.insert(
        {
            "event_type": _AUDIT_EVENT_TYPE,
            "payload": payload,
        }
    ).execute()


def record_successful_probe(
    audit_events: Any,
    probe_flags: Mapping[str, bool],
) -> tuple[bool, Sequence[str]]:
    """Record and return the existing probe summary used by schedule routing.

    Schedule-probe callers should invoke this only after their existing probe
    has completed successfully.  Returning the same summary keeps Codex
    routing independent of persistence while ensuring the audit event is
    durable before a successful observation is reported.
    """

    work_classes = _normalized_work_classes(probe_flags)
    persist_schedule_probe_observation(audit_events, probe_flags=probe_flags)
    return bool(work_classes), work_classes
