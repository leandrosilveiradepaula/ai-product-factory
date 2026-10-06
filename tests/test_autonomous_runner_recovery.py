from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=ROOT/".github"/"workflows"/"autonomous-runner.yml"


class AutonomousRunnerRecoveryTests(unittest.TestCase):
    def test_shared_recovery_runs_for_schedule_wake_and_manual_dispatch(self):
        text=WORKFLOW.read_text()
        self.assertIn("Recover expired leases in the shared scheduler runner",text)
        self.assertIn("github.event_name == 'schedule'",text)
        self.assertIn("github.event_name == 'issue_comment'",text)
        self.assertIn("github.event_name == 'workflow_dispatch'",text)
        self.assertIn("runtime_cli --mode recovery --max-attempts 3",text)


if __name__=="__main__":
    unittest.main()
