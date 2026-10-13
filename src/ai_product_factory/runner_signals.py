"""Fail-closed, side-effect-free GitHub Actions output adapters.

Signals originate from durable runtime JSON. Never infer a newly materialized
Change Set from a product-stage job's success/skip state alone.
"""
from __future__ import annotations

from typing import Any


def product_run_completed(payload: Any) -> bool:
    """Only a successfully completed claimed product run merits a post-stage probe."""
    return isinstance(payload, dict) and payload.get("claimed") is True and payload.get("status") == "completed"


def dispatch_queue_ready(payload: Any) -> bool:
    """A fresh Control Plane probe, never an old product-work flag, wakes dispatch."""
    return isinstance(payload, dict) and payload.get("dispatch_work") is True
