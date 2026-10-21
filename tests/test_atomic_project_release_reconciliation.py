"""Release reconciliation does not silently promote external early merges."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261021093000_atomic_release_project_state.sql").read_text()
PY=(ROOT/"src/ai_product_factory/project_release_reconciliation.py").read_text()
class Contracts(unittest.TestCase):
 def test_fail_closed_eligibility_and_access(self):
  for c in ("FOR UPDATE","FOR SHARE","ctl.state <> 'running'",
   "run.status <> 'merged'","rel.status <> 'released'",
   "rel.report->>'merge_sha'","'product_readiness_followup'",
   "'project.state.reconciled_after_release'","'global_readiness_evidence_required'"):
   self.assertIn(c,SQL)
  self.assertIn("SECURITY INVOKER",SQL)
  self.assertIn("FROM PUBLIC,anon,authenticated",SQL)
  self.assertIn("TO service_role",SQL)
  self.assertNotIn("SECURITY DEFINER",SQL)
 def test_only_one_runtime_mutation(self):
  self.assertIn("rpc/factory_reconcile_project_release_atomic",PY)
  self.assertNotIn('"PATCH"',PY)
  self.assertNotIn('"factory_project_state_snapshots"',PY)
  self.assertNotIn('"factory_audit_events"',PY)
if __name__=="__main__":unittest.main()
