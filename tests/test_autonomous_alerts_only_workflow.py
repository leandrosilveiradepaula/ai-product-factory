from pathlib import Path
import re
import unittest

WORKFLOW=Path(__file__).resolve().parents[1]/".github/workflows/autonomous-runner.yml"
OTHER_JOBS=("github-access-preflight","product-stage","change-set-integration","ci-followup","specialist-security","specialist-qa","specialist-operations","release-followup","dispatch","direct","codex","codex-manual","preview","codex-route-preflight")

def body(text,name):
    match=re.search(r"(?ms)^  "+re.escape(name)+r":\n(.*?)(?=^  [a-zA-Z][a-zA-Z0-9_-]*:\n|\Z)",text)
    if not match: raise AssertionError(name)
    return match.group(1)

class TestAlertsOnlyWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text=WORKFLOW.read_text()
    def test_alerts_independent_of_release(self):
        alert=body(self.text,"alerts")
        self.assertIn("needs: schedule-probe",alert)
        self.assertNotIn("needs: release-followup",alert)
        self.assertIn("inputs.run_alerts == true",alert)
        self.assertIn("--mode alerts",alert)
    def test_all_other_jobs_skip_alerts_only(self):
        for job in OTHER_JOBS:
            with self.subTest(job=job):
                header=next(x for x in body(self.text,job).splitlines() if x.strip().startswith("if:"))
                self.assertIn("(github.event_name != 'workflow_dispatch' || inputs.run_alerts != true)",header)
    def test_shared_runner_skips_recovery_and_probe_on_manual_alerts(self):
        probe=body(self.text,"schedule-probe")
        self.assertIn("inputs.run_alerts != true",probe)
        self.assertIn("Probe durable work queues without side effects",probe)
        self.assertIn("--mode recovery",probe)
    def test_scheduled_alerts_preserved(self):
        self.assertIn("if: ${{ github.event_name == 'schedule' }}",body(self.text,"schedule-probe"))
        self.assertIn("--mode alerts",body(self.text,"schedule-probe"))

if __name__=="__main__":
    unittest.main()
