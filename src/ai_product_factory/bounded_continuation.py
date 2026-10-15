"""Bounded deterministic continuation within an already authorized scheduler wake.

This module does not claim work, authorize costs, merge PRs, or call models.
A caller passes its existing readiness-gated, durable one-item worker.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ContinuationBlocked(RuntimeError):
    """Refuse unbounded execution or unstable durable work identity."""


_WAITING = frozenset({
    "awaiting_release", "wait_ci", "ci_triggered",
    "blocked", "release_policy_blocked",
})


def drain_deterministic_lane(
    once: Callable[[], dict[str, Any]],
    *,
    max_items: int = 1,
    identity: str = "run_id",
) -> dict[str, Any]:
    """Drain up to four items; stop on waits, empty queue or repeated identity.

    The underlying worker must remain responsible for authorization, durable
    atomic claims, GitHub SHA checks and transitions. A no-op is not retried.
    """
    if type(max_items) is not int or not 1 <= max_items <= 4:
        raise ValueError("deterministic continuation bound must be 1..4")
    if identity not in {"run_id", "job_id", "change_set_id"}:
        raise ValueError("unsupported durable lane identity")
    done: list[dict[str, str]] = []
    seen: set[str] = set()
    reason = "capacity"
    for _ in range(max_items):
        item = once()
        if not isinstance(item, dict) or type(item.get("claimed")) is not bool:
            raise ContinuationBlocked("deterministic worker returned invalid claim evidence")
        if item.get("error"):
            raise ContinuationBlocked("deterministic lane worker reported an error")
        state = item.get("status")
        if not isinstance(state, str) or not state.strip():
            raise ContinuationBlocked("deterministic worker lacks status evidence")
        if not item["claimed"]:
            reason = state
            break
        ref = item.get(identity)
        if not isinstance(ref, str) or not ref.strip():
            raise ContinuationBlocked("claimed work item has no durable identity")
        if ref in seen:
            raise ContinuationBlocked("deterministic worker repeated durable identity")
        seen.add(ref)
        done.append({"id": ref, "status": state})
        if state in _WAITING:
            reason = state
            break
    return {
        "claimed": bool(done),
        "status": "processed" if done else reason,
        "processed": len(done),
        "stop_reason": reason,
        "items": done,
    }
