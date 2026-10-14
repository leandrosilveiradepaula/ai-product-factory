"""Regression against a real 14 October scheduler failure.

The alert collector is an independent job: failure is still visible on the
scheduled workflow, but ready deterministic worker lanes must not be skipped
because an unrelated GitHub issue reconciliation or ledger read failed.
"""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
JOBS=re.findall(r"(?m)^  ([a-z][a-z0-9-]+):\n",SOURCE)

def job(name):
    head=f"  {name}:\n"
    if head not in SOURCE:raise AssertionError(name)
    return SOURCE.split(head,1)[1].split("\n  ",1)[0]

class SchedulerAlertIsolationContract(unittest.TestCase):
    def test_collector_failure_is_not_suppressed_or_relabelled_success(self):
        collector=job("alerts")
        self.assertIn("    needs: schedule-probe",collector)
        self.assertIn("always()",collector)
        self.assertIn("github.event_name == 'schedule'",collector)
        self.assertIn("github.event_name == 'workflow_dispatch'",collector)
        self.assertIn("inputs.run_alerts == true",collector)
        self.assertIn("run: python -m ai_product_factory.runtime_cli --mode alerts",collector)
        self.assertNotIn("continue-on-error: true",collector)
        self.assertNotIn("|| true",collector)

    def test_schedule_probe_stays_fatal_for_probe_failure_but_not_collector(self):
        probe=job("schedule-probe")
        self.assertIn("--mode schedule-probe",probe)
        self.assertIn("--mode recovery",probe)
        self.assertIn("schedule_probe.native_observed", (ROOT/"src/ai_product_factory/supabase_schedule_probe.py").read_text()) if (ROOT/"src/ai_product_factory/supabase_schedule_probe.py").exists() else self.assertIn("Probe durable work queues without side effects",probe)
        self.assertNotIn("--mode alerts",probe)
        self.assertNotIn("issues: write",probe)
        self.assertNotIn("continue-on-error: true\n        run: python -m ai_product_factory.runtime_cli --mode schedule-probe",probe)

    def test_alert_collector_has_only_its_existing_issue_scope(self):
        collector=job("alerts")
        self.assertIn("      contents: read",collector)
        self.assertIn("      id-token: write",collector)
        self.assertIn("      issues: write",collector)
        self.assertNotIn("FACTORY_GITHUB_TOKEN",collector)
        for banned in ("--mode recovery","--mode schedule-probe",
                       "--mode dispatch","--mode direct","--mode codex",
                       "--mode product","--mode preview","--mode release",
                       "OPENAI_API_KEY","VERCEL_TOKEN","actions: write",
                       "contents: write"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned,collector)

    def test_core_job_dependencies_do_not_include_alerts(self):
        for name in ("github-access-preflight","product-stage","dispatch","direct",
                     "preview","release-followup"):
            with self.subTest(job=name):
                worker=job(name)
                self.assertNotIn("needs: [alerts",worker)
                self.assertNotIn("needs.alerts.",worker)
                self.assertNotIn("needs: alerts",worker)

    def test_crons_and_triggers_unchanged(self):
        self.assertEqual(SOURCE.count("    - cron:"),2)
        self.assertIn('cron: "17 * * * *"',SOURCE)
        self.assertIn('cron: "47 * * * *"',SOURCE)
        self.assertIn("  workflow_run:",SOURCE)
        self.assertIn("  issue_comment:",SOURCE)
        self.assertIn("  workflow_dispatch:",SOURCE)
        self.assertNotIn("pull_request_target:",SOURCE)

if __name__=="__main__":
    unittest.main()
