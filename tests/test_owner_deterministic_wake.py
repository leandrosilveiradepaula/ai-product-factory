"""Owner-only deterministic settlement wake contract (no API/model/network calls).

Regression: on 2026-10-21 owner /factory-wake launched schedule-probe, but
project-control, release outbox and legacy-readiness steps were skipped.
The protected workflow must match schedule's deterministic housekeeping
without treating arbitrary issue comments as authorized events.
"""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
PROBE=WORKFLOW.split("\n  schedule-probe:\n",1)[1].split("\n  github-access-preflight:\n",1)[0]
OWNER_EXACT="github.event.comment.body == '/factory-wake'"
OWNER_ROLE="github.event.comment.author_association == 'OWNER'"
OWNER_RECEIPT="steps.owner_wake.outputs.verified == 'true'"

SETTLEMENT={
    "Settle quiescent manual project controls": "--mode project-control-settle",
    "Settle only previously observed human release state": "--mode release-state-settle",
    "Repair readiness for current verified legacy human releases":
        "--mode legacy-release-readiness-repair",
    "Observe committed project control wake": "--mode project-control-wake",
}


def section(title:str)->str:
    anchor="      - name: "+title+"\n"
    if PROBE.count(anchor)!=1:
        raise AssertionError("expected exactly one schedule-probe step: "+title)
    body=PROBE.split(anchor,1)[1].split("\n      - ",1)[0]
    return body


class OwnerDeterministicWakeTests(unittest.TestCase):
    def test_job_level_owner_gate_remains_exact(self):
        job_gate=PROBE.split("    runs-on:",1)[0]
        self.assertIn("github.event_name != 'issue_comment'",job_gate)
        self.assertIn(OWNER_EXACT,job_gate)
        self.assertIn(OWNER_ROLE,job_gate)
        self.assertIn("github.event.workflow_run.event == 'schedule'",job_gate)
        self.assertIn("github.event.workflow_run.repository.full_name == github.repository",job_gate)

    def test_owner_receipt_requires_both_identity_and_exact_command(self):
        step=section("Authenticate exact owner wake for deterministic settlement")
        self.assertIn("id: owner_wake",step)
        self.assertIn("github.event_name == 'issue_comment'",step)
        self.assertIn(OWNER_EXACT,step)
        self.assertIn(OWNER_ROLE,step)
        self.assertIn('echo \'verified=true\' >> "$GITHUB_OUTPUT"',step)
        self.assertNotIn("env.GITHUB_TOKEN",step)
        self.assertNotIn("model",step.lower())

    def test_all_four_housekeeping_lanes_opt_in_to_verified_owner_wake(self):
        for label,mode in SETTLEMENT.items():
            with self.subTest(step=label):
                step=section(label)
                self.assertIn(OWNER_RECEIPT,step)
                self.assertIn("github.event_name == 'issue_comment'",step)
                self.assertIn("github.event_name == 'schedule'",step)
                self.assertIn("github.event_name == 'repository_dispatch'",step)
                self.assertIn("steps.backup_wake.outputs.wake == 'true'",step)
                self.assertIn(mode,step)
        self.assertEqual(PROBE.count(OWNER_RECEIPT),4)

    def test_owner_wake_only_touches_expected_deterministic_steps(self):
        # Product/direct/CI/Preview remain guarded by their existing queue
        # admission logic. The owner receipt never appears in another job.
        self.assertEqual(WORKFLOW.count(OWNER_RECEIPT),4)
        self.assertEqual(PROBE.count("id: owner_wake"),1)
        other=WORKFLOW.split("\n  github-access-preflight:\n",1)[1]
        self.assertNotIn("owner_wake.outputs",other)
        self.assertNotIn("OPENAI_API_KEY:",PROBE)
        self.assertNotIn("gh pr merge",PROBE)
        self.assertNotIn("auto-merge",WORKFLOW)

    def test_untrusted_comment_does_not_produce_receipt(self):
        receipt=section("Authenticate exact owner wake for deterministic settlement")
        # All checks must be in the SAME step-level if, not merely comments.
        guard=next(x.strip() for x in receipt.splitlines() if x.strip().startswith("if:"))
        self.assertIn("github.event_name == 'issue_comment' && ",guard)
        self.assertIn(OWNER_EXACT+" && "+OWNER_ROLE,guard)
        self.assertNotIn("||",guard)
        self.assertNotIn("!=",guard)

    def test_owner_wake_does_not_redefine_read_only_journey_audit(self):
        self.assertIn('run: python -m ai_product_factory.runtime_cli --mode schedule-probe',PROBE)
        self.assertIn("github.event_name == 'issue_comment' ||",section(
            "Recover expired leases in the shared scheduler runner"))
        # A manual journey audit must stay distinct from a scheduler wake.
        self.assertIn("run_journey_audit != true",PROBE)
        self.assertIn("journey-readonly:",WORKFLOW)


if __name__=="__main__":
    unittest.main()
