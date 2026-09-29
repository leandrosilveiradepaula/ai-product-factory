import unittest
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]


class ArchitectureExtensionAcceptanceTests(unittest.TestCase):
    def test_change_set_pipeline_is_single_candidate_and_fail_closed(self):
        migration=(ROOT/"supabase/migrations/20260929033000_factory_change_sets.sql").read_text()
        workflow=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
        runtime=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()
        builder=(ROOT/"src/ai_product_factory/change_set_worker.py").read_text()
        integrator=(ROOT/"src/ai_product_factory/change_set_integrator.py").read_text()
        github=(ROOT/"src/ai_product_factory/github_rest.py").read_text()

        self.assertIn("factory_change_sets",migration)
        self.assertIn("factory_change_set_work_units",migration)
        self.assertIn("factory_materialize_change_set",migration)
        self.assertIn("factory_bind_change_set_source",migration)
        self.assertIn("factory_claim_change_set_integration",migration)
        self.assertIn("factory_complete_change_set_integration",migration)
        self.assertIn("factory_prepare_change_set_release",migration)
        self.assertIn("factory_recover_change_sets",migration)
        self.assertGreaterEqual(migration.count("enable row level security"),2)
        self.assertIn("security invoker",migration)
        self.assertIn("change-set-integration:",workflow)
        self.assertIn("--mode change-set-integration",workflow)
        self.assertIn("ChangeSetBuilderWorker",runtime)
        self.assertIn("ChangeSetIntegrator",runtime)
        self.assertNotIn("create_pull_request",builder)
        self.assertIn("Change Set file conflict",integrator)
        self.assertIn("final Change Set PR head does not match integrated candidate",integrator)
        self.assertNotIn("merge_pull_request",integrator)
        self.assertNotIn("def merge_pull_request",github)

    def test_adaptive_concurrency_guardrails_are_collected(self):
        policy=(ROOT/"src/ai_product_factory/adaptive_concurrency.py").read_text()
        migration=(ROOT/"supabase/migrations/20260929030000_factory_adaptive_concurrency.sql").read_text()
        self.assertIn("unknown paid cost blocks execution",policy)
        self.assertIn('quota in {"blocked","critical"}',policy)
        self.assertIn("factory_agent_concurrency_decisions",migration)
        self.assertIn("security invoker",migration)

    def test_specialist_review_jobs_remain_read_only(self):
        workflow=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
        start=workflow.index("\n  specialist-security:")
        end=workflow.index("\n  release-followup:")
        region=workflow[start:end]
        self.assertNotIn("contents: write",region)
        self.assertNotIn("pull-requests: write",region)
        self.assertIn("--specialist-role security",region)
        self.assertIn("--specialist-role qa",region)
        self.assertIn("--specialist-role operations",region)


if __name__=="__main__":
    unittest.main()
