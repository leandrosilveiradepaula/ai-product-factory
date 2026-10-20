"""Scheduler signals must not wake work on an operator-paused project."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"supabase/migrations/20261020183500_fence_scheduler_queue_signals_manual_control.sql"
SQL=PATH.read_text().lower()
def block(name,next_name):
    return SQL.split("'"+name+"'",1)[1].split("'"+next_name+"'",1)[0]

class SchedulerSignalOperatorGate(unittest.TestCase):
 def test_active_work_signals_are_state_and_generation_fenced(self):
    pairs=(("product_work","routed_execution_work"),
           ("routed_execution_work","codex_manual_work"),
           ("codex_manual_work","integration_work"),
           ("specialist_security_work","specialist_qa_work"),
           ("specialist_qa_work","specialist_operations_work"))
    for name,next_name in pairs:
        with self.subTest(name=name):
            s=block(name,next_name)
            self.assertIn("factory_project_execution_controls c",s)
            self.assertIn("c.state='running'",s)
            self.assertIn("c.generation>0",s)
            self.assertIn("p.is_active=true",s)
    operations=block("specialist_operations_work", "no_such_label") if False else SQL.split("'specialist_operations_work'",1)[1].split(");",1)[0]
    self.assertIn("c.state='running'",operations)
    self.assertIn("c.generation>0",operations)
 def test_observational_ci_release_signals_do_not_claim_work(self):
    self.assertIn("'ci_work', exists(",SQL)
    self.assertIn("'release_work', exists(",SQL)
    self.assertIn("r.status='ci_pending'",SQL)
    self.assertIn("r.status='awaiting_release'",SQL)
 def test_migration_keeps_existing_runtime_permissions_and_no_new_writes(self):
    self.assertIn("returns jsonb",SQL)
    self.assertIn("language sql",SQL)
    self.assertIn("stable",SQL)
    self.assertIn("set search_path to ''",SQL)
    self.assertIn("revoke all on function public.factory_scheduler_queue_signals() from public,anon,authenticated",SQL)
    self.assertIn("grant execute on function public.factory_scheduler_queue_signals() to service_role",SQL)
    self.assertNotIn("security definer",SQL)
    for token in ("insert into","update public.","delete from","factory_claim_","factory_dispatch_","openai","model_call"):
        self.assertNotIn(token,SQL)
 def test_no_new_scheduler_or_auto_merge(self):
    wf=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
    self.assertIn("factory-autonomous-runner",wf)
    self.assertIn("--mode schedule-probe",wf)
    self.assertNotIn("auto-merge",SQL)
if __name__=="__main__": unittest.main()
