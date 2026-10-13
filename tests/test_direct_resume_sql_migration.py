"""Static SQL contract for transactional Direct-only resumption.

No production writes or paid model calls.
"""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261013224500_schedule_eligible_direct_run.sql").read_text()
PY=(ROOT/"src/ai_product_factory/agent_scheduler.py").read_text()
RUNTIME=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()


class DirectResumeSafetyTests(unittest.TestCase):
 def test_filters_and_lock_before_assignment(self):
  for marker in (
   "r.status='queued'", "r.execution_route='direct'",
   "t.status='queued_execution'", "proj.is_active=true",
   "p_run_id is null or r.id=p_run_id", "p_project_key is null",
   "for update of r skip locked", "ra.status in ('assigned','claimed')",
   "coalesce(v_task.required_capabilities,'[]'::jsonb)",
   "coalesce(v_task.scope_keys,'[]'::jsonb)",
   "factory_schedule_run_agent(", "'agent.assigned'",
  ):
   with self.subTest(marker=marker): self.assertIn(marker,SQL)
  self.assertLess(SQL.index("for update of r skip locked"),SQL.index("factory_schedule_run_agent("))
  self.assertNotIn("execution_route in ('direct','codex')",SQL)

 def test_privileges_and_sql_body_complete(self):
  self.assertEqual(SQL.count("create or replace function"),1)
  self.assertEqual(SQL.count("as $$"),1)
  self.assertEqual(SQL.count("$$;"),1)
  self.assertEqual(SQL.count("'")%2,0)
  self.assertIn("security invoker",SQL)
  self.assertIn("from public,anon,authenticated;",SQL)
  self.assertIn("to service_role;",SQL)
  self.assertNotIn("security definer",SQL)
  self.assertNotIn("truncate ",SQL.lower())

 def test_python_gate_and_exact_or_approved_resume(self):
  code=RUNTIME.split("def run_dispatch_once(",1)[1].split("\ndef main(",1)[0]
  self.assertIn('if "direct" in allowed_routes',code)
  self.assertIn("resumed_direct+=1",code)
  self.assertIn("if decision.execution.human_gate_required:",code)
  self.assertIn('"scheduled_existing"',code)
  self.assertNotIn("scheduler.schedule_next()",code)
  self.assertIn('"factory_schedule_eligible_direct_run"',PY)
  self.assertIn("if run_id is not None and assignment.run_id!=run_id:",PY)

if __name__=="__main__":unittest.main()
