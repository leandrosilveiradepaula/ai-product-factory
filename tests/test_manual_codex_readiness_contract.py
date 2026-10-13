"""Manual Codex handoff stays fail-closed and independent of paid Primary.

No network requests or paid models are used by this test suite.
"""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
MANUAL=(ROOT/"src/ai_product_factory/manual_codex_handoff.py").read_text()
RUNTIME=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()


class ManualCodexReadinessContractTests(unittest.TestCase):
    def test_unset_flag_cannot_claim_new_manual_handoff(self):
        self.assertIn('os.getenv("FACTORY_CODEX_MANUAL_FALLBACK_ENABLED") != "true"',MANUAL)
        self.assertNotIn('os.getenv("FACTORY_CODEX_MANUAL_FALLBACK_ENABLED", "true")',MANUAL)
        self.assertIn('os.getenv("FACTORY_CODEX_MANUAL_FALLBACK_ENABLED")=="true"',RUNTIME)

    def test_workflow_opt_in_matches_python_and_followup_stays_independent(self):
        job=WORKFLOW.split("\n  codex-manual:\n",1)[1].split("\n  preview:\n",1)[0]
        self.assertIn("vars.FACTORY_CODEX_MANUAL_FALLBACK_ENABLED == 'true'",job)
        self.assertIn("env.FACTORY_CODEX_MANUAL_FALLBACK_ENABLED == 'true'",job)
        self.assertNotIn("env.FACTORY_CODEX_MANUAL_FALLBACK_ENABLED != 'false'",job)
        followup=job.split("name: Resume at most one completed manual Codex handoff",1)[1]
        self.assertIn("steps.readiness.outputs.control_plane == 'true'",followup)
        self.assertNotIn("FACTORY_CODEX_MANUAL_FALLBACK_ENABLED",followup)
        self.assertNotIn("CODEX_ACCESS_TOKEN:",job)
        self.assertNotIn("OPENAI_API_KEY:",job)

    def test_issue_binding_marker_is_verified_before_state_transition(self):
        body=MANUAL.split("def prepare_once(",1)[1].split("\ndef followup_once(",1)[0]
        self.assertIn("if marker not in issue.body:",body)
        self.assertIn("issue.number != item.issue_number",body)
        self.assertLess(body.index("if marker not in issue.body:"),body.index("queue.mark_waiting(item.run_id)"))
        self.assertNotIn("merge_pull_request",body)


if __name__=="__main__":
    unittest.main()
