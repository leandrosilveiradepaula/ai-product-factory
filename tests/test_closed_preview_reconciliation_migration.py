from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase/migrations/20261013210000_reconcile_closed_preview_candidate.sql"

class ClosedPreviewReconciliationMigrationTests(unittest.TestCase):
 def setUp(self):
  self.sql=MIGRATION.read_text()

 def test_exact_pr_and_change_set_evidence_required(self):
  for marker in ("p_github_merged is distinct from false",
                 "p_github_state is distinct from 'closed'",
                 "v_evidence->>'head_sha' is distinct from p_candidate_commit",
                 "v_evidence->>'pr' is distinct from p_pr_number::text",
                 "v_set.release_run_id is distinct from p_run_id",
                 "v_set.root_task_id is distinct from v_task.id",
                 "v_run.status<>'preview_ready' or v_set.status<>'ci_pending'"):
   self.assertIn(marker,self.sql)

 def test_only_terminal_state_with_durable_audit(self):
  self.assertIn("status='cancelled'",self.sql)
  self.assertIn("status='superseded'",self.sql)
  self.assertIn("preview.closed_unmerged_pr_reconciled",self.sql)
  self.assertIn("'idempotent',true",self.sql)
  self.assertNotIn("delete from",self.sql.lower())
  self.assertNotIn("update public.factory_tasks",self.sql.lower())
  self.assertNotIn("update public.factory_change_set_work_units",self.sql.lower())

 def test_service_role_only(self):
  self.assertIn("security invoker",self.sql)
  self.assertIn("revoke all on function public.factory_reconcile_closed_preview_candidate",self.sql)
  self.assertIn("grant execute on function public.factory_reconcile_closed_preview_candidate",self.sql)
  self.assertIn("to service_role;",self.sql)

if __name__=="__main__":unittest.main()
