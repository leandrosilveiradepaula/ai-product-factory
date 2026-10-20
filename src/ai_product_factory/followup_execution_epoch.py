"""Bind deterministic followups to their original routed worker generation.

An old routed CI/Preview/Specialist run without an epoch must not be
silently trusted merely because an operator later resumes the project.
"""
from __future__ import annotations


def run_followup_epoch(run: dict) -> tuple[int | None, bool]:
    if not isinstance(run, dict):
        raise RuntimeError("followup run must be an object")
    route = run.get("execution_route")
    if route is not None and not isinstance(route, str):
        raise RuntimeError("invalid execution route")
    metadata = run.get("metadata")
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise RuntimeError("invalid execution metadata")
    raw = metadata.get("execution_generation")
    required = route in {"direct", "codex"} or raw is not None
    if raw is None:
        return None, required
    if type(raw) is not int or raw < 1:
        raise RuntimeError("invalid durable execution generation")
    return raw, required
