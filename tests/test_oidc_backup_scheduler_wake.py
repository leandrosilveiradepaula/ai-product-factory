from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
W=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
P=(ROOT/".github/workflows/control-plane-oidc-preflight.yml").read_text()
def block(name):
    m=re.search(r"(?ms)^  "+re.escape(name)+r":\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)",W)
    if not m:raise AssertionError(name)
    return m.group(1)

class BackupWakeContract(unittest.TestCase):
    def test_reuses_existing_schedule_not_new_cron(self):
        self.assertEqual(W.count("    - cron:"),2)
        self.assertEqual(P.count("    - cron:"),1)
        self.assertIn('workflows: ["Control Plane OIDC preflight"]',W)
    def test_origin_and_success_filter(self):
        j=block("schedule-probe")
        for expected in ("github.event.workflow_run.event == 'schedule'",
                         "github.event.workflow_run.conclusion == 'success'",
                         "github.event.workflow_run.head_branch == 'main'",
                         "github.event.workflow_run.repository.full_name == github.repository"):
            self.assertIn(expected,j)
    def test_fallback_rechecks_durable_liveness(self):
        j=block("schedule-probe")
        self.assertIn("SupabaseSchedulerLivenessReader().read()",j)
        self.assertIn("evaluate_scheduler_liveness(liveness)",j)
        self.assertIn("steps.backup_wake.outputs.wake == 'true'",j)
        self.assertIn("set -euo pipefail",j)
    def test_normal_wakes_and_human_release_gates_preserved(self):
        j=block("schedule-probe")
        self.assertIn("'/factory-wake'",j)
        self.assertIn("github.event.comment.author_association == 'OWNER'",j)
        self.assertIn("--mode recovery",j)
        self.assertIn("--mode schedule-probe",j)
        self.assertIn("steps.probe.outputs.work_detected == 'false'",j)
        self.assertIn("cancel-in-progress: false",W)
        for name in ("product-stage","dispatch","direct","codex","preview","release-followup"):
            self.assertIn("needs: ",block(name))
    def test_oidc_broker_allows_only_exact_backup_runtime_workflow(self):
        edge=(ROOT/"supabase/functions/factory-runtime-control-plane/index.ts").read_text()
        self.assertIn('if(event==="workflow_run")',edge)
        self.assertIn('String(payload.workflow_ref??"")!==TRUSTED_BACKUP_WORKFLOW_REF',edge)
        self.assertIn('.github/workflows/autonomous-runner.yml@refs/heads/main',edge)
        self.assertIn('GitHub OIDC workflow_run workflow not allowed',edge)
        self.assertIn('if(!["schedule","workflow_dispatch","issue_comment","push"].includes(eventName))',edge)
        self.assertNotIn('["schedule","workflow_dispatch","issue_comment","push","workflow_run"].includes(eventName)',edge)
        self.assertIn('const workflowRef=String(identity.workflow_ref||"")',edge)
        self.assertIn('GENERIC_PROXY_WORKFLOW_REFS.has(workflowRef)',edge)

    def test_no_elevated_backup_credentials_or_merge(self):
        root=block("schedule-probe")
        self.assertNotIn("OPENAI_API_KEY",root)
        self.assertNotIn("FACTORY_GITHUB_TOKEN",root)
        self.assertNotIn("gh pr merge",root)
        self.assertNotIn("--mode product",root)
if __name__=="__main__":unittest.main()
