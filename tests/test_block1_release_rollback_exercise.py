"""Offline release/rollback safety exercise for Block 1.

This does not revert a repository or change production. It verifies the
deterministic release policy for a broad matrix and rejects unauthorized
production transitions before any network/DB side effect.
"""
from pathlib import Path
import unittest

from ai_product_factory.release_policy import ReleaseEnvironment, evaluate_release
from ai_product_factory.models import RiskProfile


class Block1ReleaseRollbackExercise(unittest.TestCase):
    def test_production_is_never_autonomous_even_for_default_risk(self):
        decision = evaluate_release(ReleaseEnvironment.PROD, RiskProfile())
        self.assertFalse(decision.may_release_autonomously)
        self.assertTrue(decision.human_gate_required)
        self.assertTrue(decision.reasons)

    def test_nonproduction_does_not_bypass_risk_gates(self):
        for environment in (ReleaseEnvironment.DEV, ReleaseEnvironment.PREVIEW):
            decision = evaluate_release(environment, RiskProfile())
            self.assertTrue(decision.may_release_autonomously)
            self.assertFalse(decision.human_gate_required)

    def test_invalid_release_environment_is_not_treated_as_preview(self):
        # ReleaseEnvironment is a strict enum at external boundaries; callers
        # must parse it before calling evaluate_release.
        for value in ("production", "PROD", "", "preview-production"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ReleaseEnvironment(value)

    def test_documented_rollback_requires_separate_human_merge(self):
        body = (Path(__file__).resolve().parents[1] /
                "docs/RELEASE_AUTONOMY.md").read_text(encoding="utf-8")
        for contract in ("reversão", "CI", "SHA", "humano", "RLS", "rollback"):
            with self.subTest(contract=contract):
                self.assertIn(contract, body)
        self.assertIn("nunca faz auto-merge", body)
        self.assertIn("Não executar", body)


if __name__ == "__main__":
    unittest.main()
