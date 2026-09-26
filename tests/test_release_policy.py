import unittest

from ai_product_factory.models import RiskProfile
from ai_product_factory.release_policy import ReleaseEnvironment, evaluate_release


class ReleasePolicyTests(unittest.TestCase):
    def test_dev_low_risk_is_autonomous(self):
        decision = evaluate_release(ReleaseEnvironment.DEV)
        self.assertTrue(decision.may_release_autonomously)
        self.assertFalse(decision.human_gate_required)

    def test_preview_low_risk_is_autonomous(self):
        decision = evaluate_release(ReleaseEnvironment.PREVIEW)
        self.assertTrue(decision.may_release_autonomously)

    def test_production_always_requires_human(self):
        decision = evaluate_release(ReleaseEnvironment.PROD)
        self.assertFalse(decision.may_release_autonomously)
        self.assertTrue(decision.human_gate_required)
        self.assertIn("release em producao", decision.reasons)

    def test_destructive_preview_requires_human(self):
        decision = evaluate_release(
            ReleaseEnvironment.PREVIEW,
            RiskProfile(destructive_data_change=True),
        )
        self.assertFalse(decision.may_release_autonomously)
        self.assertTrue(decision.human_gate_required)

    def test_paid_service_in_dev_requires_human(self):
        decision = evaluate_release(
            ReleaseEnvironment.DEV,
            RiskProfile(new_paid_service=True),
        )
        self.assertTrue(decision.human_gate_required)


if __name__ == "__main__":
    unittest.main()
