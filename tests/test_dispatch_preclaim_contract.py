from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=(ROOT/".github/workflows/autonomous-runner.yml").read_text()

class PreclaimDispatchSafetyContractTests(unittest.TestCase):
    def test_secret_isolation_and_boolean_signal(self):
        product=WORKFLOW.split("\n  product-stage:\n",1)[1].split("\n  change-set-integration:\n",1)[0]
        dispatch=WORKFLOW.split("\n  dispatch:\n",1)[1].split("\n  direct:\n",1)[0]
        self.assertIn("primary_ready: ${{ steps.readiness.outputs.primary_model }}",product)
        self.assertIn("needs.schedule-probe.outputs.dispatch_work == 'true'",product)
        self.assertIn("FACTORY_DISPATCH_PRIMARY_READY: ${{ needs.product-stage.outputs.primary_ready == 'true' && 'true' || 'false' }}",dispatch)
        self.assertNotIn("OPENAI_API_KEY:",dispatch)
        self.assertNotIn("OPENAI_IDENTITY_TOKEN_FILE:",dispatch)

    def test_budget_and_switch_default_off(self):
        dispatch=WORKFLOW.split("\n  dispatch:\n",1)[1].split("\n  direct:\n",1)[0]
        self.assertIn("FACTORY_PRIMARY_MODEL_ENABLED: ${{ vars.FACTORY_PRIMARY_MODEL_ENABLED == 'true' && 'true' || 'false' }}",dispatch)
        self.assertIn('FACTORY_MODEL_BUDGET_USD: "4.00"',dispatch)
        self.assertIn('FACTORY_MODEL_RESERVE_USD: "0.50"',dispatch)

    def test_dispatch_only_preflight_does_not_invoke_product_model(self):
        product=WORKFLOW.split("\n  product-stage:\n",1)[1].split("\n  change-set-integration:\n",1)[0]
        worker=product.split("name: Process at most one product-stage run",1)[1].split("name: Probe freshly materialized",1)[0]
        self.assertIn("needs.schedule-probe.outputs.product_work == 'true'",worker)
        self.assertIn("steps.readiness.outputs.primary_model == 'true'",worker)

    def test_python_gate_precedes_claim(self):
        source=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()
        body=source.split("def run_dispatch_once(",1)[1].split("\ndef main(",1)[0]
        self.assertLess(body.index("require_dispatch_claim_readiness()"),body.index("SupabaseBacklogDispatch()"))
        readiness=source.split("def require_dispatch_claim_readiness()",1)[1].split("\ndef run_dispatch_once(",1)[0]
        self.assertIn("require_primary_runtime_enabled()",readiness)
        self.assertIn("require_paid_runtime_budget()",readiness)
        self.assertIn('os.getenv("FACTORY_DISPATCH_PRIMARY_READY")!="true"',readiness)

if __name__=="__main__":
    unittest.main()
