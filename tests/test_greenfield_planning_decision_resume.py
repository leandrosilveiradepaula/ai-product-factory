"""Greenfield human decisions resume planning without imported-project reconciliation."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261015210000_greenfield_planning_decision_resume.sql").read_text()
PROMPT=(ROOT/"src/ai_product_factory/product_stage_executor.py").read_text()
PREVIOUS=(ROOT/"supabase/migrations/20261004185900_materialize_planning_decisions.sql").read_text()

class GreenfieldPlanningDecisionResumeTests(unittest.TestCase):
 def test_new_greenfield_decisions_do_not_require_imported_snapshot(self):
  self.assertIn("v_project_kind text;",SQL)
  self.assertIn("select project_kind into v_project_kind",SQL)
  self.assertIn("v_project_kind='greenfield'",SQL)
  self.assertIn("then jsonb_build_array('planning')",SQL)
  self.assertIn("else jsonb_build_array('reconciliation','gap_analysis','planning')",SQL)
  self.assertIn("'reconcile_first',(v_project_kind<>'greenfield')",SQL)
  self.assertIn("existing-project reconciliation requires a durable state snapshot",PROMPT)
  self.assertIn("manifest.human_decisions contains human-approved answers",PROMPT)

 def test_existing_project_and_human_gate_semantics_are_preserved(self):
  for needle in [
   "if v_gate.status <> 'pending' then raise exception",
   "planning decision requires an explicit response",
   "v_resume_external_key:='planning-decision-reconcile-'",
   "'decision_gate_id',p_gate_id",
   "if v_decision_only then",
   "elsif p_resolution='approved' then",
   "security invoker",
   "revoke all on function public.factory_resolve_human_gate",
   "grant execute on function public.factory_resolve_human_gate",
  ]:
   self.assertIn(needle,SQL)
   self.assertIn(needle,PREVIOUS)

 def test_backfill_is_bounded_and_writes_durable_audit(self):
  self.assertIn("p.project_kind='greenfield'",SQL)
  self.assertIn("r.status='created'",SQL)
  self.assertIn("r.attempt_count=0",SQL)
  self.assertIn("t.status='queued'",SQL)
  self.assertIn("r.metadata->>'source'='planning-decision'",SQL)
  self.assertIn("r.metadata->'stages'='[\"reconciliation\",\"gap_analysis\",\"planning\"]'::jsonb",SQL)
  self.assertIn("g.id::text=r.metadata->>'decision_gate_id'",SQL)
  self.assertIn("g.status='approved'",SQL)
  self.assertIn("planning_decision.greenfield_stages_corrected",SQL)
  self.assertIn("'no_paid_model_call',true",SQL)
  self.assertNotIn("delete from",SQL.lower())
  self.assertNotIn("truncate",SQL.lower())

 def test_no_automatic_release_or_quota_changes(self):
  for forbidden in ("auto_merge","github merge","FACTORY_MODEL_BUDGET_USD","openai_api_key"):
   self.assertNotIn(forbidden,SQL)

if __name__=="__main__":
 unittest.main()
