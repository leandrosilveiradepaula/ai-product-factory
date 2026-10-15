from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261015093000_atomic_project_intake_bootstrap.sql").read_text()
CONTROL=(ROOT/"apps/console/lib/control-plane.ts").read_text()
PAGE=(ROOT/"apps/console/app/projects/new/review/page.tsx").read_text()

class AtomicProjectStartTests(unittest.TestCase):
 def test_one_transaction_instead_of_split_console_writes(self):
  for marker in ("factory_start_project_intake_v1(","public.factory_create_project_intake(","public.factory_finalize_project_attachments(","public.factory_enqueue_project_bootstrap(","v_count IS DISTINCT FROM p_expected_attachments","v_cycle->>'run_id'"):
   self.assertIn(marker,SQL)
  self.assertIn("rpc/factory_start_project_intake_v1",CONTROL)
  self.assertIn("createProjectIntakeAndBootstrap(clean,intake.draftId,expectedCount)",PAGE)
  for unsafe in ("await createProjectIntake(clean)","await enqueueProjectBootstrap(","await finalizeProjectDraftFiles("):
   self.assertNotIn(unsafe,PAGE)

 def test_replay_and_attachment_security(self):
  for marker in ("bootstrap_request_id","bootstrap_attachment_count","bootstrap_operator_id","v_spec IS DISTINCT FROM p_spec","p_draft_id::text","a.operator_user_id", "previous intake lacks initial run","'created',false","draft attachment count changed"):
   self.assertIn(marker.lower().replace("a.operator_user_id","operator_user_id"),SQL.lower())
  self.assertIn("countProjectDraftFiles(intake.draftId)",PAGE)
  self.assertIn("v_manifest->>'bootstrap_operator_id' IS DISTINCT FROM p_operator_user_id::text",SQL)
  self.assertIn("pg_catalog.pg_advisory_xact_lock",SQL)
  self.assertIn("p_project_kind IS NULL",SQL)
  self.assertIn("p_operator_user_id:operator.userId",CONTROL)
  self.assertIn("p_draft_id:draftId",CONTROL)

 def test_authorization_and_fail_closed_response(self):
  lowered=SQL.lower()
  for marker in ("security invoker","set search_path to ''","from public, anon, authenticated","to service_role;"):
   self.assertIn(marker,lowered)
  self.assertNotIn("security definer",lowered)
  self.assertNotIn("merge_pull_request",lowered)
  for marker in ("result.project_id","result.task_id","result.run_id","result.request_id!==draftId","result.attachment_count!==expectedCount",'typeof result.created!=="boolean"'):
   self.assertIn(marker,CONTROL)

 def test_production_migration_gate_is_explicit(self):
  ops=(ROOT/"docs/OPERATIONS.md").read_text()
  self.assertIn("before merging or deploying the Console change",ops)
  self.assertIn("human gate",ops.lower())

if __name__=="__main__":unittest.main()
