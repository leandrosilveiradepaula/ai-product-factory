import unittest
from pathlib import Path

class PrimaryModelRunnerGateTests(unittest.TestCase):
    def test_primary_model_disabled_for_scheduled_runner_jobs(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/autonomous-runner.yml").read_text()
        self.assertNotIn('FACTORY_PRIMARY_MODEL_ENABLED: "true"', workflow)
        self.assertEqual(workflow.count('FACTORY_PRIMARY_MODEL_ENABLED: "false"'), 2)
        self.assertIn("FACTORY_MODEL_RESERVE_USD", workflow)
        self.assertIn("FACTORY_PRIMARY_AUTH_MODE", workflow)

if __name__ == "__main__":
    unittest.main()
