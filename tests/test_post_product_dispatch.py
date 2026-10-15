from pathlib import Path
import unittest

from ai_product_factory.runner_signals import dispatch_queue_ready, product_run_completed

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=ROOT/".github/workflows/autonomous-runner.yml"


class PostProductDispatchTests(unittest.TestCase):
    def test_product_run_completion_requires_actual_claim_and_success(self):
        for payload in (
            None, {}, "completed",
            {"claimed":False,"status":"completed"},
            {"claimed":True,"status":"blocked"},
            {"claimed":True,"status":"failed"},
            {"claimed":True,"status":None},
            {"claimed":"true","status":"completed"},
        ):
            with self.subTest(payload=payload):
                self.assertFalse(product_run_completed(payload))
        self.assertTrue(product_run_completed({"claimed":True,"status":"completed"}))

    def test_dispatch_gate_uses_fresh_control_plane_bool(self):
        for payload in (None,{},{"dispatch_work":None},{"dispatch_work":False},
                        {"dispatch_work":"true"},{"product_work":True}):
            with self.subTest(payload=payload):
                self.assertFalse(dispatch_queue_ready(payload))
        self.assertTrue(dispatch_queue_ready({"dispatch_work":True}))

    def test_product_stage_probes_only_after_real_completed_run(self):
        workflow=WORKFLOW.read_text()
        product=workflow.split("\n  product-stage:\n",1)[1].split("\n  change-set-integration:\n",1)[0]
        self.assertIn("dispatch_work: ${{ steps.post_product_probe.outputs.dispatch_work }}",product)
        self.assertIn("id: product_run",product)
        self.assertIn("product_run_completed(result)",product)
        self.assertIn("id: post_product_probe",product)
        self.assertIn("steps.product_run.outputs.completed == 'true'",product)
        self.assertIn("dispatch_queue_ready(result)",product)
        self.assertIn("--mode schedule-probe > /tmp/factory-post-product-probe.json",product)
        self.assertIn("steps.readiness.outputs.primary_model == 'true'",product)

    def test_dispatch_never_wakes_only_on_initial_product_work(self):
        workflow=WORKFLOW.read_text()
        dispatch=workflow.split("\n  dispatch:\n",1)[1].split("\n  direct:\n",1)[0]
        self.assertIn("needs.schedule-probe.outputs.dispatch_work == 'true'",dispatch)
        self.assertIn("needs.product-stage.outputs.dispatch_work == 'true'",dispatch)
        self.assertNotIn("needs.schedule-probe.outputs.product_work == 'true'",dispatch)
        self.assertIn("needs.product-stage.result != 'failure'",dispatch)
        self.assertIn("inputs.project_key != ''",dispatch)

    def test_cost_security_and_release_controls_unchanged(self):
        workflow=WORKFLOW.read_text()
        product=workflow.split("\n  product-stage:\n",1)[1].split("\n  change-set-integration:\n",1)[0]
        self.assertIn("FACTORY_PRIMARY_MODEL_ENABLED: ${{ vars.FACTORY_PRIMARY_MODEL_ENABLED == 'true' && 'true' || 'false' }}",product)
        self.assertIn('FACTORY_MODEL_BUDGET_USD: "10.00"',product)
        self.assertIn('FACTORY_MODEL_RESERVE_USD: "0.50"',product)
        self.assertNotIn("merge_pull_request",workflow)
        self.assertNotIn("gh pr merge",workflow)


if __name__=="__main__":
    unittest.main()
