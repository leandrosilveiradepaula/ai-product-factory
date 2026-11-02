"""Bounded, exact-SHA governance evidence for a proposed human decision.

The model proposes a question; it never authorizes a scope or creates a
human decision. A quoted statement must be present in the source snapshot
which the worker already read at its immutable commit.
"""
from __future__ import annotations

import re
from typing import Any


def validated_material_decision(
    proposed: Any, *,
    source: dict,
    snapshot: dict[str, str],
    blocked_reason: str,
) -> dict | None:
    if proposed is None:
        return None
    if not isinstance(proposed, dict) or set(proposed) != {
        "decision_kind", "question", "why_needed", "governance_path", "governance_quote",
    }:
        raise PermissionError("structured governance decision evidence is invalid")
    if proposed.get("decision_kind") != "material_requirement_change":
        raise PermissionError("unsupported governance decision kind")
    binding = source.get("journey_binding")
    if not isinstance(binding, dict) or binding.get("binding_version") != 2:
        raise PermissionError("material decision requires bound Journey V2")
    if not isinstance(blocked_reason, str) or not blocked_reason.strip():
        raise PermissionError("material decision requires a real blocked implementation")
    for key, lo, hi in (
        ("question", 20, 400), ("why_needed", 25, 750),
        ("governance_quote", 35, 480),
    ):
        value = proposed.get(key)
        if not isinstance(value, str) or value != value.strip() or not lo <= len(value) <= hi:
            raise PermissionError("governance decision text invalid: " + key)
    path = proposed.get("governance_path")
    if path not in ("AGENTS.md", "docs/codex/CURRENT_TASK.md"):
        raise PermissionError("governance decision path not authorized")
    contents = snapshot.get(path)
    quote = proposed["governance_quote"]
    if not isinstance(contents, str) or quote not in contents:
        raise PermissionError("governance quotation not found at pinned source")
    if not re.search(
        r"decis[aã]o humana|autoriza[cç][aã]o (?:humana|expl[ií]cita)|human decision|human approval",
        quote, re.IGNORECASE,
    ):
        raise PermissionError("governance quotation does not reserve a human decision")
    if any(ord(char) < 32 and char not in "\n\t" for char in quote):
        raise PermissionError("governance quotation contains control characters")
    if len(blocked_reason) > 1000:
        raise PermissionError("governance blocked reason exceeds bounded receipt")
    return {
        "decision_kind": "material_requirement_change",
        "question": proposed["question"],
        "why_needed": proposed["why_needed"],
        "governance_path": path,
        "governance_quote": quote,
        "reason": blocked_reason,
    }
