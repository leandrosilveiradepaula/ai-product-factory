"""Offline contract for owner-only alert reconciliation via GitHub issue comment.

This trigger is separate from /factory-wake: it must never wake executors,
lease recovery, dispatch, Primary/Codex, Preview or release processing.
"""
from pathlib import Path
import re
import unittest

WORKFLOW=Path(__file__).resolve().parents[1]/".github/workflows/autonomous-runner.yml"


def jobs(source: str) -> dict[str,str]:
    body = source.split("\njobs:\n",1)[1]
    matches = list(re.finditer(r"(?m)^  ([a-z][a-z0-9-]*):\n",body))
    return {m.group(1):body[m.end():matches[i+1].start() if i+1<len(matches) else len(body)]
            for i,m in enumerate(matches)}


def job_needs(body: str) -> set[str]:
    match=re.search(r"(?m)^    needs:\s*(.+)$",body)
    if not match:
        return set()
    value=match.group(1).strip()
    if value.startswith("[") and value.endswith("]"):
        return {x.strip() for x in value[1:-1].split(",")}
    return {value}


class OwnerAlertsOnlyContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=WORKFLOW.read_text(encoding="utf-8")
        cls.jobs=jobs(cls.source)

    def test_exact_owner_comment_and_issue_gate(self):
        gate=self.jobs["alerts-owner-comment"].splitlines()[0].strip()
        self.assertIn("github.event_name == 'issue_comment'",gate)
        self.assertIn("github.event.comment.body == '/factory-alerts'",gate)
        self.assertIn("github.event.comment.author_association == 'OWNER'",gate)
        self.assertIn("!github.event.issue.pull_request",gate)
        self.assertNotIn("contains(",gate)
        self.assertNotIn("startsWith(",gate)

    def test_owner_comment_job_has_no_execution_or_recovery_commands(self):
        job=self.jobs["alerts-owner-comment"]
        self.assertEqual(job.count("--mode alerts"),1)
        for banned in ("--mode recovery","--mode schedule-probe","--mode dispatch",
                       "--mode product","--mode direct","--mode codex",
                       "--mode preview","--mode release","OPENAI_API_KEY",
                       "CODEX_ACCESS_TOKEN","FACTORY_GITHUB_TOKEN"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned,job)
        self.assertEqual(job_needs(job),set())

    def test_control_plane_and_issue_scopes_are_protected(self):
        job=self.jobs["alerts-owner-comment"]
        self.assertIn("      contents: read",job)
        self.assertIn("      id-token: write",job)
        self.assertIn("      issues: write",job)
        self.assertIn("uses: ./.github/actions/control-plane-oidc",job)
        self.assertIn("Require protected Control Plane access",job)
        self.assertIn("exit 1",job)
        self.assertIn('FACTORY_GITHUB_ALERTS_ENABLED: "true"',job)

    def test_other_jobs_are_rooted_in_original_schedule_probe(self):
        root=self.jobs["schedule-probe"]
        self.assertIn("github.event.comment.body == '/factory-wake'",root)
        self.assertIn("github.event.comment.author_association == 'OWNER'",root)
        self.assertNotIn("/factory-alerts",root)
        for name,body in self.jobs.items():
            if name in ("schedule-probe","alerts-owner-comment","journey-readonly","continuation-offline-preflight"):
                continue
            seen=set()
            pending=[name]
            while pending:
                current=pending.pop()
                if current in seen:
                    continue
                seen.add(current)
                pending.extend(job_needs(self.jobs[current]))
            self.assertIn("schedule-probe",seen,name)

    def test_read_only_auditor_is_separate_and_cannot_wake_scheduler(self):
        audit=self.jobs["journey-readonly"]
        self.assertIn("github.event_name == 'workflow_dispatch'",audit)
        self.assertIn("inputs.run_journey_audit == true",audit)
        self.assertIn("audit_autonomy_journey.py",audit)
        self.assertEqual(job_needs(audit),set())
        self.assertIn("inputs.run_journey_audit != true",self.jobs["schedule-probe"])
        for invalid in ("--mode product","--mode dispatch","--mode direct",
                        "--mode codex","--mode preview","--mode release",
                        "FACTORY_PRIMARY_MODEL_ENABLED","CODEX_ACCESS_TOKEN"):
            with self.subTest(invalid=invalid):
                self.assertNotIn(invalid,audit)

    def test_existing_alerts_only_dispatch_and_cron_are_unchanged(self):
        self.assertIn("inputs.run_alerts == true",self.jobs["alerts"])
        self.assertIn("github.event_name == 'schedule'",self.jobs["schedule-probe"])
        self.assertNotIn("python -m ai_product_factory.runtime_cli --mode alerts",self.jobs["schedule-probe"])
        self.assertIn("python -m ai_product_factory.runtime_cli --mode alerts",self.jobs["alerts"])
        self.assertIn("github.event_name == 'schedule'",self.jobs["alerts"])
        self.assertIn("always()",self.jobs["alerts"])

if __name__=="__main__":
    unittest.main()
