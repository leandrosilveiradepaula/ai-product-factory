from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
MIG=ROOT/"supabase/migrations/20261014160500_atomic_project_continuation.sql"
CONSOLE=(ROOT/"apps/console/lib/control-plane.ts").read_text()
PAGE=(ROOT/"apps/console/app/projects/[key]/request/page.tsx").read_text()

class AtomicProjectContinuationContractTests(unittest.TestCase):
 def test_shared_lock_and_atomic_rpc(self):
  sql=MIG.read_text()
  self.assertEqual(sql.upper().count('FOR UPDATE'),2)
  self.assertIn('factory_enqueue_project_continuation(',sql)
  self.assertIn('factory_enqueue_project_bootstrap(p_project_key text)',sql)
  self.assertIn("another active project cycle exists",sql)
  self.assertIn("v_original_requested_at",sql)
  self.assertIn("r.metadata->>'continuation_request_id'=p_request_id::text",sql)
  self.assertIn('v_previous_summary IS DISTINCT FROM v_request',sql)
  self.assertIn("parent.status IN ('completed','cancelled','failed','merged','integrated')",sql)
  self.assertIn("'project.continuation.requested'",sql)
  self.assertIn("'project.reconciliation.enqueued'",sql)
  self.assertIn("'enqueue_project_reconciliation'",sql)

 def test_boundary_remains_server_only_and_no_model_or_merge(self):
  sql=MIG.read_text().lower()
  self.assertIn('security invoker',sql)
  self.assertIn('revoke all on function public.factory_enqueue_project_continuation',sql)
  self.assertIn('grant execute on function public.factory_enqueue_project_continuation',sql)
  self.assertNotIn('security definer',sql)
  self.assertNotIn('merge_pull_request',sql)
  self.assertIn('rpc/factory_enqueue_project_continuation',CONSOLE)
  self.assertNotIn('PATCH',CONSOLE[CONSOLE.index('export async function enqueueProjectContinuation'):CONSOLE.index('export async function getDashboard')])
  self.assertNotIn('const activeTasks=project.tasks.filter',PAGE)

if __name__=="__main__":unittest.main()
