"""Operational regression: VPS wake and native cron both reconcile alerts.

No new OIDC grant, no model/recovery work on alert-only issue comments,
and no direct issue writes from schedule-probe.
"""
from pathlib import Path
import re
import unittest

SOURCE = (
    Path(__file__).resolve().parents[1] /
    ".github/workflows/autonomous-runner.yml"
).read_text(encoding="utf-8")


def job(name: str) -> str:
    match = re.search(
        r"(?ms)^  " + re.escape(name) +
        r":\n(.*?)(?=^  [a-zA-Z][a-zA-Z0-9_-]*:\n|\Z)", SOURCE
    )
    if match is None:
        raise AssertionError(name)
    return match.group(1)


class VPSAlertReconciliationContract(unittest.TestCase):
    def test_vps_wake_dispatch_runs_alerts_without_special_manual_flag(self):
        alerts = job("alerts")
        gate = next(line for line in alerts.splitlines()
                    if line.strip().startswith("if:"))
        self.assertIn("github.event_name == 'workflow_dispatch'", gate)
        self.assertIn("needs.schedule-probe.result == 'success'", gate)
        self.assertIn("github.event_name == 'schedule'", gate)
        self.assertIn("always()", gate)
        self.assertNotIn("inputs.run_alerts == true", gate)
        self.assertIn("run: python -m ai_product_factory.runtime_cli --mode alerts",
                      alerts)

    def test_reconciler_stays_separate_and_unprivileged_for_work(self):
        alerts = job("alerts")
        probe = job("schedule-probe")
        self.assertIn("needs: schedule-probe", alerts)
        self.assertIn("issues: write", alerts)
        self.assertNotIn("issues: write", probe)
        self.assertNotIn("--mode alerts", probe)
        self.assertNotIn("FACTORY_GITHUB_TOKEN", alerts)
        for forbidden in (
            "--mode recovery", "--mode direct", "--mode codex",
            "--mode product", "--mode dispatch", "--mode preview",
            "--mode release", "OPENAI_API_KEY", "VERCEL_TOKEN",
            "contents: write", "actions: write", "continue-on-error: true",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, alerts)

    def test_read_only_dispatch_does_not_enter_alerts(self):
        # Every read-only dispatch mode already skips schedule-probe.
        # The alert job additionally requires a successful probe.
        probe = job("schedule-probe")
        alerts = job("alerts")
        for flag in (
            "inputs.run_journey_audit != true",
            "inputs.run_offline_preflight != true",
            "inputs.run_admission_diagnosis != true",
        ):
            self.assertIn(flag, probe)
        self.assertIn("needs.schedule-probe.result == 'success'", alerts)
        self.assertNotIn("needs: alerts", probe)
        self.assertNotIn("--mode alerts", probe)

    def test_owner_alert_command_remains_independent(self):
        owner = job("alerts-owner-comment")
        self.assertIn("github.event.comment.body == '/factory-alerts'", owner)
        self.assertIn("github.event.comment.author_association == 'OWNER'", owner)
        self.assertIn("issues: write", owner)
        self.assertNotIn("needs: schedule-probe", owner)
        self.assertEqual(owner.count("--mode alerts"), 1)


if __name__ == "__main__":
    unittest.main()
