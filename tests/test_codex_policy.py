import unittest

from ai_product_factory.codex_policy import classify_codex_need
from ai_product_factory.models import Complexity, TaskProfile


class CodexPolicyTests(unittest.TestCase):
    def test_simple_change_does_not_use_codex(self):
        decision = classify_codex_need(TaskProfile(complexity=Complexity.LOW, estimated_files=2))
        self.assertFalse(decision.should_use)
        self.assertEqual(decision.policy_version,"v2")
        self.assertLess(decision.level, 3)

    def test_deep_large_refactor_uses_codex(self):
        decision = classify_codex_need(TaskProfile(
            complexity=Complexity.HIGH,
            estimated_files=30,
            deep_debug=True,
            large_refactor=True,
        ))
        self.assertTrue(decision.should_use)
        self.assertEqual(decision.level, 4)

    def test_medium_change_prefers_direct_execution(self):
        decision = classify_codex_need(TaskProfile(
            complexity=Complexity.MEDIUM,
            estimated_files=5,
            direct_tools_sufficient=True,
        ))
        self.assertFalse(decision.should_use)


    def test_confirmed_impact_and_unknowns_can_justify_codex(self):
        decision=classify_codex_need(TaskProfile(
            complexity=Complexity.MEDIUM,
            estimated_files=5,
            impacted_components=9,
            impact_unknowns=4,
        ))
        self.assertTrue(decision.should_use)
        self.assertIn("impacto confirmado em muitos componentes",decision.reasons)
        self.assertIn("impact analysis com unknowns relevantes",decision.reasons)

    def test_comparative_history_and_cost_can_keep_direct(self):
        decision=classify_codex_need(TaskProfile(
            complexity=Complexity.HIGH,
            estimated_files=10,
            impacted_components=8,
            historical_direct_first_pass=0.90,
            historical_codex_first_pass=0.60,
            historical_codex_cost_ratio=4.0,
        ))
        self.assertFalse(decision.should_use)
        self.assertIn("Direct tem vantagem historica relevante de first-pass",decision.reasons)
        self.assertIn("custo historico do Codex e alto versus Direct",decision.reasons)

    def test_missing_historical_telemetry_has_zero_influence(self):
        baseline=classify_codex_need(TaskProfile(complexity=Complexity.MEDIUM,estimated_files=5))
        explicit_none=classify_codex_need(TaskProfile(
            complexity=Complexity.MEDIUM,estimated_files=5,
            historical_repair_rate=None,historical_conflict_rate=None,
            historical_direct_first_pass=None,historical_codex_first_pass=None,
            historical_codex_cost_ratio=None,
        ))
        self.assertEqual(baseline.level,explicit_none.level)
        self.assertEqual(baseline.should_use,explicit_none.should_use)


if __name__ == "__main__":
    unittest.main()
