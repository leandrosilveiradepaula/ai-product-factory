"""Contract checks for opt-in paid execution in GitHub Actions.

These tests never access OpenAI, GitHub Actions, or the Control Plane.
"""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
WF=(ROOT/".github/workflows/autonomous-runner.yml")
RUNTIME=(ROOT/"src/ai_product_factory/runtime_cli.py")


class PrimaryActivationWorkflowTests(unittest.TestCase):
    def test_product_and_direct_are_explicit_opt_in_default_false(self):
        workflow=WF.read_text()
        opt_in="FACTORY_PRIMARY_MODEL_ENABLED: ${{ vars.FACTORY_PRIMARY_MODEL_ENABLED == 'true' && 'true' || 'false' }}"
        self.assertEqual(workflow.count(opt_in),3)  # Product, Direct, and preclaim dispatcher
        self.assertNotIn('FACTORY_PRIMARY_MODEL_ENABLED: "true"',workflow)
        self.assertNotIn('FACTORY_PRIMARY_MODEL_ENABLED: "false"',workflow)

    def test_job_scopes_and_budget_ceiling_not_weakened(self):
        workflow=WF.read_text()
        product=workflow.split("\n  product-stage:\n",1)[1].split("\n  change-set-integration:\n",1)[0]
        direct=workflow.split("\n  direct:\n",1)[1].split("\n  codex:\n",1)[0]
        for job in (product,direct):
            self.assertIn("environment: openai-api",job)
            self.assertIn('FACTORY_MODEL_BUDGET_USD: "10.00"',job)
            self.assertIn('FACTORY_MODEL_RESERVE_USD: "0.50"',job)
            self.assertIn("OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}",job)
            self.assertIn("vars.FACTORY_PRIMARY_MODEL_ENABLED == 'true'",job)
        self.assertIn("steps.readiness.outputs.primary_model == 'true'",product)
        self.assertIn("env.FACTORY_PRIMARY_MODEL_ENABLED == 'true'",direct)

    def test_runtime_checks_cost_and_auth_before_any_claim(self):
        source=RUNTIME.read_text()
        for mode in ("def run_product_once(", "def run_direct_once("):
            body=source.split(mode,1)[1].split("\ndef ",1)[0]
            self.assertIn("require_primary_runtime_enabled()",body)
            self.assertIn("require_paid_runtime_budget()",body)
        self.assertIn("health.unknown_cost_events>0",source)
        self.assertIn('os.getenv("FACTORY_PRIMARY_MODEL_ENABLED")!="true"',source)

    def test_never_introduce_runtime_merge_or_paid_probe(self):
        workflow=WF.read_text()
        self.assertNotIn("gh pr merge",workflow)
        self.assertNotIn("auto-merge",workflow)


if __name__=="__main__":
    unittest.main()
