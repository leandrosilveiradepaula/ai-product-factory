import unittest

from ai_product_factory.evidence import EvidenceBundle
from ai_product_factory.models import (
    Complexity,
    ExecutionRoute,
    LifecycleStage,
    ProjectState,
    RiskProfile,
    TaskProfile,
)
from ai_product_factory.orchestrator import decide_execution
from ai_product_factory.state_machine import transition
from ai_product_factory.usage import summarize_usage


class GreenfieldOfflineAutonomyTests(unittest.TestCase):
    def test_low_risk_greenfield_path_needs_no_model_or_human_gate(self):
        state = ProjectState(project_key="greenfield-offline")
        for stage in (
            LifecycleStage.SPECIFICATION,
            LifecycleStage.PLANNING,
            LifecycleStage.IMPLEMENTATION,
            LifecycleStage.REVIEW,
            LifecycleStage.VALIDATION,
            LifecycleStage.PREVIEW,
        ):
            transition(state, stage)

        decision = decide_execution(
            TaskProfile(
                complexity=Complexity.LOW,
                estimated_files=2,
                direct_tools_sufficient=True,
            ),
            RiskProfile(),
        )
        self.assertEqual(decision.route, ExecutionRoute.DIRECT)
        self.assertFalse(decision.human_gate_required)

        evidence = EvidenceBundle(
            source_commit="source",
            candidate_commit="candidate",
            ci_status="success",
            metadata={"offline": True, "external_model_calls": 0},
        )
        self.assertEqual(evidence.to_dict()["ci_status"], "success")
        self.assertEqual(evidence.to_dict()["metadata"]["external_model_calls"], 0)

        usage = summarize_usage([])
        self.assertEqual(usage.calls, 0)
        self.assertEqual(usage.input_tokens, 0)
        self.assertEqual(usage.output_tokens, 0)

        transition(state, LifecycleStage.RELEASE)
        transition(state, LifecycleStage.OPERATIONS)
        self.assertEqual(state.stage, LifecycleStage.OPERATIONS)

    def test_production_greenfield_path_stops_at_human_gate(self):
        state = ProjectState(project_key="greenfield-production")
        for stage in (
            LifecycleStage.SPECIFICATION,
            LifecycleStage.PLANNING,
            LifecycleStage.IMPLEMENTATION,
            LifecycleStage.REVIEW,
            LifecycleStage.VALIDATION,
            LifecycleStage.PREVIEW,
        ):
            transition(state, stage)

        decision = decide_execution(
            TaskProfile(complexity=Complexity.LOW, direct_tools_sufficient=True),
            RiskProfile(production_change=True),
        )
        self.assertFalse(decision.codex.should_use)
        self.assertTrue(decision.human_gate_required)
        transition(state, LifecycleStage.HUMAN_GATE)
        self.assertEqual(state.stage, LifecycleStage.HUMAN_GATE)


if __name__ == "__main__":
    unittest.main()
