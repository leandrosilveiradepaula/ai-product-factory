import unittest
from pathlib import Path

class PrimaryModelRunnerGateTests(unittest.TestCase):
    def test_primary_model_disabled_for_scheduled_runner_jobs(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/autonomous-runner.yml").read_text()
        self.assertNotIn('FACTORY_PRIMARY_MODEL_ENABLED: "true"', workflow)
        strict_opt_in = "FACTORY_PRIMARY_MODEL_ENABLED: ${{ vars.FACTORY_PRIMARY_MODEL_ENABLED == 'true' && 'true' || 'false' }}"
        self.assertEqual(workflow.count(strict_opt_in), 2)  # Protected jobs only
        dispatch=workflow.split("\n  dispatch:\n",1)[1].split("\n  direct:\n",1)[0]
        self.assertIn("FACTORY_PRIMARY_MODEL_ENABLED: ${{ needs.product-stage.outputs.primary_ready == 'true' && 'true' || 'false' }}",dispatch)
        self.assertNotIn("OPENAI_API_KEY:",dispatch)
        self.assertNotIn('FACTORY_PRIMARY_MODEL_ENABLED: ${{ vars.FACTORY_PRIMARY_MODEL_ENABLED }}', workflow)
        self.assertNotIn("|| 'true'", workflow)
        self.assertNotIn("FACTORY_MODEL_RESERVE_USD", workflow)
        self.assertNotIn("FACTORY_MODEL_BUDGET_USD", workflow)
        self.assertIn("FACTORY_PRIMARY_AUTH_MODE", workflow)

if __name__ == "__main__":
    unittest.main()
