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


_STAGE_VERIFIED = "verified"
_STAGE_NOT_REACHED = "not_reached"


def _status(value: Any) -> str:
    """Return only an enum-like status, never arbitrary evidence payloads."""
    return value.strip().lower() if isinstance(value, str) else ""


def _reason(code: str, stage: str | None = None) -> dict[str, str]:
    result = {"code": code}
    if stage is not None:
        result["stage"] = stage
    return result


def _classify(report: Any) -> tuple[str, list[dict[str, str]]]:
    """Classify the ACTUAL read-only JourneyReport contract, fail-closed.

    Journey stages have verified/not_reached status, in a verified prefix.
    The report status may be in_progress, awaiting_human_merge,
    observed_complete, blocked or not_started. No later-stage assertion is
    a substitute for a missing earlier stage.
    """
    report_status = _status(getattr(report, "status", None))
    stages = getattr(report, "stages", None)
    if not isinstance(stages, (tuple, list)) or len(stages) != len(STAGES):
        return "insufficient_evidence", [_reason("missing_stage_evidence")]

    names = tuple(getattr(item, "name", None) for item in stages)
    if names != STAGES:
        return "insufficient_evidence", [_reason("contradictory_stage_evidence")]

    verified_prefix = 0
    future_seen = False
    for item in stages:
        current = _status(getattr(item, "status", None))
        if current not in {_STAGE_VERIFIED, _STAGE_NOT_REACHED}:
            return "insufficient_evidence", [
                _reason("unrecognized_stage_status", item.name)
            ]
        if current == _STAGE_NOT_REACHED:
            future_seen = True
        else:
            if future_seen:
                return "insufficient_evidence", [
                    _reason("contradictory_stage_evidence", item.name)
                ]
            verified_prefix += 1

    highest = STAGES[verified_prefix - 1] if verified_prefix else None
    if getattr(report, "highest_verified", None) != highest:
        return "insufficient_evidence", [_reason("contradictory_current_evidence")]

    blockers = getattr(report, "blockers", None)
    if (not isinstance(blockers, (tuple, list))
            or any(not isinstance(code, str) or not 1 <= len(code) <= 160
                   for code in blockers)):
        return "insufficient_evidence", [_reason("unverifiable_live_evidence")]

    if report_status == "not_started":
        if (verified_prefix or "explicit_project_start_not_observed"
                not in blockers):
            return "insufficient_evidence", [
                _reason("contradictory_current_evidence")
            ]
        return "not_started", [_reason("explicit_project_start_not_observed")]

    if report_status == "blocked":
        if not blockers:
            return "insufficient_evidence", [
                _reason("contradictory_current_evidence")
            ]
        return "blocked", [_reason("verified_blocker")]

    if blockers or verified_prefix == 0:
        return "insufficient_evidence", [
            _reason("contradictory_current_evidence")
        ]

    if report_status == "observed_complete":
        if verified_prefix != len(STAGES):
            return "insufficient_evidence", [
                _reason("contradictory_current_evidence")
            ]
        return "eligible", [_reason("all_required_stages_verified")]

    if report_status == "awaiting_human_merge":
        if verified_prefix != STAGES.index("awaiting_release") + 1:
            return "insufficient_evidence", [
                _reason("contradictory_current_evidence")
            ]
        return "awaiting", [_reason("pending_gate", "human_release_observed")]

    if report_status == "in_progress":
        if verified_prefix >= STAGES.index("awaiting_release") + 1:
            return "insufficient_evidence", [
                _reason("contradictory_current_evidence")
            ]
        return "in_progress", [
            _reason("stage_not_yet_verified", STAGES[verified_prefix])
        ]

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
        required_stage = (
            "manual_start" if args.require_at_least == "none"
            else args.require_at_least
        )
        required_stage_verified = any(
            item.name == required_stage and item.status == "verified"
            for item in report.stages
        )
        result["requirement_met"] = (
            classification in {"in_progress", "awaiting", "eligible"}
            and required_stage_verified
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
