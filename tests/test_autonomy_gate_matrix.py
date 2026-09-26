import unittest

from ai_product_factory.models import Complexity, ExecutionRoute, RiskProfile, TaskProfile
from ai_product_factory.orchestrator import decide_execution
from ai_product_factory.release_policy import ReleaseEnvironment, evaluate_release


class AutonomyGateMatrixTests(unittest.TestCase):
    def test_low_risk_non_production_is_autonomous(self):
        for environment in (ReleaseEnvironment.DEV, ReleaseEnvironment.PREVIEW):
            with self.subTest(environment=environment):
                decision=evaluate_release(environment,RiskProfile())
                self.assertTrue(decision.may_release_autonomously)
                self.assertFalse(decision.human_gate_required)

    def test_each_documented_risk_requires_human_in_non_production(self):
        risks={
            "production_change": RiskProfile(production_change=True),
            "destructive_data_change": RiskProfile(destructive_data_change=True),
            "expands_sensitive_access": RiskProfile(expands_sensitive_access=True),
            "new_paid_service": RiskProfile(new_paid_service=True),
            "material_requirement_change": RiskProfile(material_requirement_change=True),
        }
        for environment in (ReleaseEnvironment.DEV, ReleaseEnvironment.PREVIEW):
            for name,risk in risks.items():
                with self.subTest(environment=environment,risk=name):
                    decision=evaluate_release(environment,risk)
                    self.assertFalse(decision.may_release_autonomously)
                    self.assertTrue(decision.human_gate_required)

    def test_production_is_human_for_every_risk_profile(self):
        profiles=(
            RiskProfile(),
            RiskProfile(production_change=True),
            RiskProfile(destructive_data_change=True),
            RiskProfile(expands_sensitive_access=True),
            RiskProfile(new_paid_service=True),
            RiskProfile(material_requirement_change=True),
        )
        for risk in profiles:
            decision=evaluate_release(ReleaseEnvironment.PROD,risk)
            self.assertTrue(decision.human_gate_required)
            self.assertFalse(decision.may_release_autonomously)

    def test_execution_complexity_does_not_create_human_gate(self):
        complex_task=TaskProfile(complexity=Complexity.HIGH,estimated_files=40,deep_debug=True,large_refactor=True)
        decision=decide_execution(complex_task,RiskProfile())
        self.assertEqual(decision.route,ExecutionRoute.CODEX)
        self.assertFalse(decision.human_gate_required)

    def test_simple_task_cannot_bypass_real_risk_gate(self):
        simple=TaskProfile(complexity=Complexity.LOW,estimated_files=1)
        decision=decide_execution(simple,RiskProfile(expands_sensitive_access=True))
        self.assertEqual(decision.route,ExecutionRoute.DIRECT)
        self.assertTrue(decision.human_gate_required)


if __name__=="__main__":
    unittest.main()
