#!/usr/bin/env python3
"""Audit a fresh, operator-started Factory run without writing or spending."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any

from ai_product_factory.autonomy_journey import STAGES
from ai_product_factory.autonomy_journey_reader import SupabaseJourneyReader


_VERIFIED = {"verified"}
_BLOCKED = {"blocked", "failed", "error", "rejected", "denied"}
_AWAITING = {"awaiting", "pending", "waiting", "running", "in_progress"}
_COMPLETE_REPORTS = {"verified", "eligible", "completed"}


def _status(value: Any) -> str:
    """Return only a normalized enum-like status, never arbitrary evidence."""
    return value.strip().lower() if isinstance(value, str) else ""


def _reason(code: str, stage: str | None = None) -> dict[str, str]:
    result = {"code": code}
    if stage is not None:
        result["stage"] = stage
    return result


def _classify(report: Any) -> tuple[str, list[dict[str, str]]]:
    """Classify only facts exposed by the exact-run read-only reader.

    Eligibility fails closed: every expected stage and the report-level status
    must be currently verified.  Unknown, missing, duplicate, or contradictory
    facts are insufficient evidence rather than implicit progress.
    """
    report_status = _status(getattr(report, "status", None))
    stages = getattr(report, "stages", None)
    if not isinstance(stages, (list, tuple)):
        return "insufficient_evidence", [_reason("missing_stage_evidence")]

    observed: dict[str, str] = {}
    duplicate_names: set[str] = set()
    invalid_entries = False
    for item in stages:
        name = getattr(item, "name", None)
        if not isinstance(name, str) or name not in STAGES:
            invalid_entries = True
            continue
        if name in observed:
            duplicate_names.add(name)
            continue
        observed[name] = _status(getattr(item, "status", None))

    reasons: list[dict[str, str]] = []
    if invalid_entries:
        reasons.append(_reason("unrecognized_stage_evidence"))
    for name in sorted(duplicate_names):
        reasons.append(_reason("contradictory_stage_evidence", name))
    for name in STAGES:
        if name not in observed:
            reasons.append(_reason("missing_stage_evidence", name))

    blocked_stages = [name for name in STAGES if observed.get(name) in _BLOCKED]
    pending_stages = [name for name in STAGES if observed.get(name) in _AWAITING]
    unknown_stages = [
        name for name in STAGES
        if name in observed
        and observed[name] not in _VERIFIED | _BLOCKED | _AWAITING
    ]

    all_verified = (
        not reasons
        and len(observed) == len(STAGES)
        and all(observed.get(name) in _VERIFIED for name in STAGES)
    )
    report_blocks = report_status in _BLOCKED
    report_awaits = report_status in _AWAITING

    contradictory = (
        (report_blocks and all_verified)
        or (report_awaits and all_verified)
        or (report_status in _COMPLETE_REPORTS and (blocked_stages or pending_stages))
        or (blocked_stages and pending_stages)
    )
    if contradictory:
        reasons.append(_reason("contradictory_current_evidence"))

    # A reader-reported block is a verifiable operational fact, even if other
    # stage facts are incomplete.  Contradictions remain visible in reasons.
    if report_blocks or blocked_stages:
        if report_blocks:
            reasons.append(_reason("verified_blocker"))
        for name in blocked_stages:
            reasons.append(_reason("verified_blocker", name))
        return "blocked", reasons

    if reasons or unknown_stages or not report_status:
        for name in unknown_stages:
            reasons.append(_reason("unrecognized_stage_status", name))
        if not report_status:
            reasons.append(_reason("missing_current_run_status"))
        return "insufficient_evidence", reasons

    if report_awaits or pending_stages:
        if report_status not in _AWAITING | _COMPLETE_REPORTS:
            return "insufficient_evidence", [_reason("unrecognized_current_run_status")]
        return "awaiting", [_reason("pending_gate", name) for name in pending_stages] or [
            _reason("pending_gate")
        ]

    if all_verified and report_status in _COMPLETE_REPORTS:
        return "eligible", [_reason("all_required_stages_verified")]

    return "insufficient_evidence", [_reason("unrecognized_current_run_status")]


def _error_result(args: argparse.Namespace, exc: Exception) -> dict[str, Any]:
    """Emit a redacted, fixed-shape failure without downstream exception text."""
    return {
        "project_key": args.project_key,
        "status": "blocked",
        "classification": "insufficient_evidence",
        "reasons": [{"code": "unverifiable_live_evidence"}],
        "required_stage": args.require_at_least,
        "requirement_met": False,
        "blocker": "unverifiable_live_evidence",
        "error_type": type(exc).__name__,
        "product_ready": False,
        "paid_calls": 0,
        "writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only exact-run Factory journey evidence")
    parser.add_argument("--project-key", required=True)
    parser.add_argument(
        "--since-utc", required=True,
        help="Reject every Start before this UTC instant",
    )
    parser.add_argument("--run-id", help="Optional specific UUID from the explicit human Start")
    parser.add_argument("--require-at-least", choices=("none",) + STAGES, default="none")
    args = parser.parse_args(argv)
    try:
        since = datetime.fromisoformat(args.since_utc.replace("Z", "+00:00"))
        report = SupabaseJourneyReader().read(
            project_key=args.project_key, since=since, run_id=args.run_id,
        )
        result = report.as_json()
        classification, reasons = _classify(report)
        result["classification"] = classification
        result["reasons"] = reasons
        result["required_stage"] = args.require_at_least
        required_stage_verified = args.require_at_least == "none" or any(
            item.name == args.require_at_least and item.status == "verified"
            for item in report.stages
        )
        result["requirement_met"] = (
            classification in {"awaiting", "eligible"} and required_stage_verified
        )
        # This command has no mutation or model path regardless of reader data.
        result["paid_calls"] = 0
        result["writes"] = 0
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0 if result["requirement_met"] else 2
    except Exception as exc:
        # Do not print arbitrary downstream HTTP bodies, headers, prompts,
        # service credentials, user metadata or audit payloads.
        print(json.dumps(_error_result(args, exc), sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
