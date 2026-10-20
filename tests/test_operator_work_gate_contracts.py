"""Operator pause fencing for agent assignment, specialist dispatch and repair."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261020190000_fence_agent_specialist_and_repair_control.sql").read_text()
FUNCTIONS=("factory_claim_agent_slot","factory_schedule_run_agent",
           "factory_schedule_next_unassigned_run","factory_claim_specialist_lane",
           "factory_enqueue_specialist_lanes","factory_enqueue_repair_from_specialist")
class OperatorWorkGateTests(unittest.TestCase):
 def test_six_existing_functions_only(self):
  self.assertEqual(re.findall(r"CREATE OR REPLACE FUNCTION public\.(factory_[a-z_]+)",SQL),list(FUNCTIONS))
  self.assertEqual(SQL.count("$function$;"),len(FUNCTIONS))
  self.assertEqual(SQL.count("SECURITY DEFINER"),0)
  self.assertNotIn("GRANT EXECUTE",SQL)
  self.assertNotIn("DROP FUNCTION",SQL)
 def test_agent_claim_checks_control_before_any_assignment(self):
  block=SQL.split("CREATE OR REPLACE FUNCTION public.factory_claim_agent_slot",1)[1].split("CREATE OR REPLACE FUNCTION",1)[0]
  self.assertIn("perform public.factory_assert_project_running(v_project_id);",block)
  self.assertLess(block.index("factory_assert_project_running"),block.index("insert into public.factory_run_agent_assignments"))
 def test_agent_scheduler_checks_project_before_selecting_agent(self):
  block=SQL.split("CREATE OR REPLACE FUNCTION public.factory_schedule_run_agent",1)[1].split("CREATE OR REPLACE FUNCTION",1)[0]
  self.assertIn("perform public.factory_assert_project_running(",block)
  self.assertLess(block.index("factory_assert_project_running"),block.index("select a.* into v_agent"))
 def test_unassigned_scheduler_never_selects_paused_project(self):
  block=SQL.split("CREATE OR REPLACE FUNCTION public.factory_schedule_next_unassigned_run",1)[1].split("CREATE OR REPLACE FUNCTION",1)[0]
  self.assertIn("c.state='running' and c.generation>0",block)
  self.assertIn("p.is_active=true",block)
 def test_specialist_claim_correlated_to_own_project(self):
  block=SQL.split("CREATE OR REPLACE FUNCTION public.factory_claim_specialist_lane",1)[1].split("CREATE OR REPLACE FUNCTION",1)[0]
  self.assertIn("from public.factory_specialist_lane_jobs j",block)
  self.assertIn("where p.id=j.project_id and p.is_active=true",block)
  self.assertIn("c.state='running' and c.generation>0",block)
  self.assertLess(block.index("c.state='running'"),block.index("update public.factory_specialist_lane_jobs"))
 def test_specialists_and_repair_require_running_before_mutation(self):
  for name,marker in (
    ("factory_enqueue_specialist_lanes","perform public.factory_assert_project_running(v_project_id);"),
    ("factory_enqueue_repair_from_specialist","perform public.factory_assert_project_running(v_job.project_id);"),
  ):
   with self.subTest(name=name):
    block=SQL.split("CREATE OR REPLACE FUNCTION public."+name,1)[1].split("CREATE OR REPLACE FUNCTION",1)[0]
    self.assertIn(marker,block)
    self.assertLess(block.index(marker),block.index("insert into public.factory_specialist_lane_jobs" if name=="factory_enqueue_specialist_lanes" else "insert into public.factory_tasks"))
 def test_no_wake_or_paid_provider_access(self):
  self.assertNotIn("github",SQL.lower())
  self.assertNotIn("openai",SQL.lower())
  self.assertNotIn("auto_merge",SQL.lower())
  self.assertNotIn("service_role",SQL.lower())
if __name__=="__main__":unittest.main()
