"""Regression tests for the Factory-generated read-only journey CLI.

The parser must understand *real* JourneyReport values, and the read-only
mode must never start a new run or invent completed release stages.
"""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from unittest.mock import patch

from ai_product_factory.autonomy_journey import (
    STAGES, JourneyReport, JourneyStage, no_start_report,
)
from scripts.audit_autonomy_journey import _classify, main


def make_report(
    status: str, verified: int, blockers: tuple[str, ...] = ()
) -> JourneyReport:
    if verified < 0 or verified > len(STAGES):
        raise ValueError("verified stage count out of bounds")
    return JourneyReport(
        project_key="ai-product-factory",
        root_run_id="945c0da5-f36f-46da-a454-072037a988a5",
        status=status,
        highest_verified=STAGES[verified - 1] if verified else None,
        stages=tuple(
            JourneyStage(
                name,
                "verified" if index < verified else "not_reached",
                "durable_scoped_evidence" if index < verified else None,
            )
            for index, name in enumerate(STAGES)
        ),
        candidate_sha=None,
        pr_number=None,
        blockers=blockers,
    )


class RealJourneyClassificationTests(unittest.TestCase):
    def test_real_in_progress_uses_verified_prefix_not_unknown_future(self):
        result, reasons = _classify(make_report("in_progress", 4))
        self.assertEqual(result, "in_progress")
        self.assertEqual(reasons, [{"code": "stage_not_yet_verified", "stage": "routing"}])

    def test_real_waiting_human_merge_is_awaiting_not_insufficient(self):
        required = STAGES.index("awaiting_release") + 1
        result, reasons = _classify(make_report("awaiting_human_merge", required))
        self.assertEqual(result, "awaiting")
        self.assertEqual(reasons, [{"code": "pending_gate", "stage": "human_release_observed"}])

    def test_fully_observed_release_is_eligible_only_with_all_stages(self):
        result, reasons = _classify(make_report("observed_complete", len(STAGES)))
        self.assertEqual(result, "eligible")
        self.assertEqual(reasons, [{"code": "all_required_stages_verified"}])
        invalid, _ = _classify(make_report("observed_complete", len(STAGES)-1))
        self.assertEqual(invalid, "insufficient_evidence")

    def test_no_start_and_blocked_statuses_are_not_success(self):
        result, reasons = _classify(no_start_report("ai-product-factory"))
        self.assertEqual(result, "not_started")
        self.assertEqual(reasons[0]["code"], "explicit_project_start_not_observed")
        result, reasons = _classify(
            make_report("blocked", 5, ("descendant_run_failed_or_blocked",))
        )
        self.assertEqual(result, "blocked")
        self.assertEqual(reasons[0]["code"], "verified_blocker")

    def test_unknown_or_contradictory_evidence_fails_closed(self):
        baseline = make_report("in_progress", 4)
        variants = (
            replace(baseline, status="completed"),
            replace(baseline, blockers=("candidate_sha_drift",)),
            replace(baseline, highest_verified="implementation"),
            replace(baseline, stages=baseline.stages[:-1]),
            replace(baseline, stages=baseline.stages[:-1] + (baseline.stages[0],)),
            replace(baseline, stages=baseline.stages[:4] + (
                JourneyStage("routing", "verified"),
            ) + baseline.stages[5:]),
            replace(baseline, stages=baseline.stages[:6] + (
                JourneyStage("review", "verified"),
            ) + baseline.stages[7:]),
            replace(make_report("awaiting_human_merge", 4), blockers=()),
            make_report("awaiting_human_merge", len(STAGES)),
            make_report("in_progress", len(STAGES)),
        )
        for value in variants:
            with self.subTest(case=repr(value)[0:70]):
                state, reasons = _classify(value)
                self.assertEqual(state, "insufficient_evidence")
                self.assertTrue(reasons)

    def test_cli_required_stage_does_not_require_full_release(self):
        report = make_report("in_progress", STAGES.index("planning") + 1)
        with patch("scripts.audit_autonomy_journey.SupabaseJourneyReader") as reader:
            reader.return_value.read.return_value = report
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main([
                    "--project-key", "ai-product-factory",
                    "--since-utc", "2026-10-20T00:00:00Z",
                    "--require-at-least", "planning",
                ])
        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["requirement_met"])
        self.assertEqual(payload["classification"], "in_progress")
        self.assertEqual(payload["paid_calls"], 0)
        self.assertEqual(payload["writes"], 0)
        reader.return_value.read.assert_called_once()

    def test_cli_future_unverified_stage_never_passes(self):
        report = make_report("in_progress", STAGES.index("planning") + 1)
        with patch("scripts.audit_autonomy_journey.SupabaseJourneyReader") as reader:
            reader.return_value.read.return_value = report
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main([
                    "--project-key", "ai-product-factory",
                    "--since-utc", "2026-10-20T00:00:00Z",
                    "--require-at-least", "github_ci",
                ])
        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertFalse(payload["requirement_met"])
        self.assertEqual(payload["classification"], "in_progress")

    def test_cli_default_none_requires_manual_start_evidence(self):
        with patch("scripts.audit_autonomy_journey.SupabaseJourneyReader") as reader:
            reader.return_value.read.return_value = no_start_report("ai-product-factory")
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main([
                    "--project-key", "ai-product-factory",
                    "--since-utc", "2026-10-20T00:00:00Z",
                ])
        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["classification"], "not_started")
        self.assertFalse(payload["requirement_met"])

    def test_cli_waiting_human_gate_can_verify_earlier_stages(self):
        report = make_report("awaiting_human_merge", STAGES.index("awaiting_release") + 1)
        with patch("scripts.audit_autonomy_journey.SupabaseJourneyReader") as reader:
            reader.return_value.read.return_value = report
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main([
                    "--project-key", "ai-product-factory",
                    "--since-utc", "2026-10-20T00:00:00Z",
                    "--require-at-least", "awaiting_release",
                ])
        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["classification"], "awaiting")
        self.assertTrue(payload["requirement_met"])


if __name__ == "__main__":
    unittest.main()
