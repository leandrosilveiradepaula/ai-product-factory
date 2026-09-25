import unittest

from ai_product_factory.models import Complexity, ExecutionRoute, RiskProfile, TaskProfile
from ai_product_factory.orchestrator import decide_execution


class OrchestratorTests(unittest.TestCase):
    def test_simple_low_risk_task_runs_directly_without_gate(self):
        decision = decide_execution(TaskProfile(complexity=Complexity.LOW, estimated_files=2))
        self.assertEqual(decision.route, ExecutionRoute.DIRECT)
        self.assertFalse(decision.human_gate_required)
        self.assertFalse(decision.codex.should_use)

    def test_complex_refactor_routes_to_codex_without_implying_human_gate(self):
        decision = decide_execution(TaskProfile(
            complexity=Complexity.HIGH,
            estimated_files=30,
            large_refactor=True,
            deep_debug=True,
        ))
        self.assertEqual(decision.route, ExecutionRoute.CODEX)
        self.assertTrue(decision.codex.should_use)
        self.assertFalse(decision.human_gate_required)

    def test_simple_production_change_is_direct_but_requires_gate(self):
        decision = decide_execution(
            TaskProfile(complexity=Complexity.LOW, estimated_files=1),
            RiskProfile(production_change=True),
        )
        self.assertEqual(decision.route, ExecutionRoute.DIRECT)
        self.assertFalse(decision.codex.should_use)
        self.assertTrue(decision.human_gate_required)
        self.assertIn("mudanca em producao", decision.gate_reasons)

    def test_invalid_codex_threshold_is_rejected(self):
        with self.assertRaises(ValueError):
            decide_execution(TaskProfile(), codex_minimum_level=5)


if __name__ == "__main__":
    unittest.main()
