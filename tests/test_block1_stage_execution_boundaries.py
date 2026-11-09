"""B2: actual Product Stage output contract must refuse simulated completion.

This is an executed unit contract on the real runtime validator. It does NOT
claim every production entrypoint or live authorization has been certified.
"""
from __future__ import annotations

import unittest

from ai_product_factory.product_stage_output_contract import (
    ProductStageOutputBlocked, assert_executed_product_stage_output,
)


class SimulationCannotBecomeCompletedStage(unittest.TestCase):
    def test_noop_demo_and_other_unexecuted_modes_never_pass(self):
        modes = (
            "noop", "no_op", "no-op", "NOOP", " No Op ", "demo",
            "mock", "fixture", "deferred", "dry_run", "dry-run",
            "placeholder", "simulated", "simulation", "requires_model",
            "not_executed", "not-executed", "skipped",
        )
        for field in (
            "mode", "execution_mode", "status", "execution_status",
            "result_status", "stage_status",
        ):
            for mode in modes:
                with self.subTest(field=field, mode=mode):
                    with self.assertRaisesRegex(ProductStageOutputBlocked,
                                                "^product_stage_output_not_executed$"):
                        assert_executed_product_stage_output({field: mode})

    def test_boolean_like_non_execution_guards_refuse_success(self):
        for key in (
            "requires_model", "deferred", "placeholder", "mock",
            "fixture", "simulated", "dry_run", "noop", "no_op", "demo",
        ):
            for value in (True, "true", "yes", "1"):
                with self.subTest(key=key, value=value):
                    with self.assertRaises(ProductStageOutputBlocked):
                        assert_executed_product_stage_output({
                            "mode": "executed", key: value,
                        })

    def test_negative_words_in_product_content_do_not_cause_false_denial(self):
        payload = {
            "mode": "executed",
            "status": "completed",
            "summary": "Avoid demo/no-op releases; test fixture behavior",
            "acceptance_criteria": [
                "Reject demo/noop when execution mode indicates a simulation"
            ],
        }
        self.assertIsNone(assert_executed_product_stage_output(payload))

    def test_false_markers_are_not_promoted_to_negative_execution(self):
        for key in ("demo", "noop", "no_op", "mock", "fixture"):
            with self.subTest(key=key):
                self.assertIsNone(assert_executed_product_stage_output({
                    key: False, "mode": "executed", "status": "completed",
                }))


if __name__ == "__main__":
    unittest.main()
