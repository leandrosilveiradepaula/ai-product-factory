"""A six-hour no-extra-cron fallback only publishes alerts after a verified gap.

This does NOT repair missing GitHub Actions schedule events or wake workers.
Existing preflight schedule and production release gates remain unchanged.
"""
from pathlib import Path
import re
import unittest

PATH=Path(__file__).resolve().parents[1]/".github/workflows/control-plane-oidc-preflight.yml"

def section(text:str,name:str)->str:
    x=re.search(rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)",text)
    if x is None:raise AssertionError("missing job: "+name)
    return x.group(1)

class TestOIDCFallback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.yaml=PATH.read_text()
        cls.preflight=section(cls.yaml,"preflight")
        cls.fallback=section(cls.yaml,"scheduler-gap-fallback")

    def test_no_added_schedule_or_altered_existing_cron(self):
        self.assertEqual(self.yaml.count('cron: "13 */6 * * *"'),1)
        self.assertEqual(self.yaml.count("  schedule:"),1)
        self.assertIn("workflow_dispatch:",self.yaml)
        self.assertIn("  vercel-quota:",self.yaml)

    def test_preflight_reads_durable_heartbeat_only_when_scheduled(self):
        self.assertIn("steps.scheduler_health.outputs.scheduler_gap",self.preflight)
        self.assertIn("SupabaseSchedulerLivenessReader().read()",self.preflight)
        self.assertIn("evaluate_scheduler_liveness(state)",self.preflight)
        self.assertIn("github.event_name == 'schedule'",self.preflight)
        self.assertIn("PYTHONPATH: src",self.preflight)
        self.assertIn("read_only_scheduler_gap=",self.preflight)
        self.assertNotIn("--mode dispatch",self.preflight)

    def test_fallback_is_conditional_and_does_not_expand_preflight_token_permissions(self):
        self.assertIn("needs: preflight",self.fallback)
        self.assertIn("needs.preflight.result == 'success'",self.fallback)
        self.assertIn("needs.preflight.outputs.scheduler_gap == 'true'",self.fallback)
        self.assertIn("github.event_name == 'schedule'",self.fallback)
        self.assertNotIn("issues: write",self.preflight)
        for permission in ("contents: read","id-token: write","issues: write"):
            self.assertIn(permission,self.fallback)

    def test_fallback_does_not_have_work_execution_or_paid_credentials(self):
        self.assertEqual(self.fallback.count("--mode alerts"),1)
        for forbidden in ("--mode product","--mode dispatch","--mode direct",
                          "--mode codex","--mode preview","--mode release",
                          "--mode recovery","--mode schedule-probe",
                          "OPENAI_API_KEY","CODEX_ACCESS_TOKEN",
                          "FACTORY_GITHUB_TOKEN","VERCEL_TOKEN"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden,self.fallback)
        self.assertIn("factory-scheduler-gap-fallback",self.fallback)
        self.assertIn("uses: ./.github/actions/control-plane-oidc",self.fallback)

    def test_no_alert_fallback_for_manual_or_push_preflight(self):
        condition=next(line for line in self.fallback.splitlines() if line.strip().startswith("if:"))
        self.assertIn("github.event_name == 'schedule'",condition)
        self.assertIn("needs.preflight.outputs.scheduler_gap == 'true'",condition)
        self.assertNotIn("github.event_name == 'workflow_dispatch'",condition)
        self.assertNotIn("github.event_name == 'push'",condition)

if __name__=="__main__":unittest.main()
