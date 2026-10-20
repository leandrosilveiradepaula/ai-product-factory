"""Protect human operator start/pause semantics in scheduler READ contracts."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261020181000_fence_scheduler_eligibility_manual_control.sql").read_text().lower()
PORTFOLIO=SQL.split("create or replace function public.factory_portfolio_candidates(",1)[1].split("create or replace function public.factory_peek_planned_work(",1)[0]
PEEK=SQL.split("create or replace function public.factory_peek_planned_work(",1)[1].split("revoke all on function",1)[0]

class SchedulerHumanControlEligibilityTests(unittest.TestCase):
 def test_only_current_selectors_are_changed(self):
  self.assertEqual(SQL.count("create or replace function"),2)
  self.assertIn("begin;",SQL)
  self.assertIn("commit;",SQL)
  self.assertNotIn("update public.factory_tasks",SQL)
  self.assertNotIn("insert into public.factory_runs",SQL)
  self.assertNotIn("delete from",SQL)
  self.assertNotIn("security definer",SQL)
 def test_portfolio_filters_control_before_aggregating_candidates(self):
  self.assertIn("join public.factory_project_execution_controls ctl on ctl.project_id=p.id and ctl.state='running' and ctl.generation>0",PORTFOLIO)
  self.assertIn("where p.is_active=true",PORTFOLIO)
  self.assertIn("where has_runnable_work and not paused and active_runs<max_active_workers",PORTFOLIO)
  for required in ("tp.status='ready'","u.status='pending' and u.wave=cs.current_wave",
                   "unit_task.status='queued'","not v_has_p0 or incident_rank=0"):
   self.assertIn(required,PORTFOLIO)
 def test_project_planned_peek_fails_closed_before_returning_work(self):
  self.assertIn("if not exists(select 1 from public.factory_project_execution_controls ctl",PEEK)
  self.assertIn("ctl.project_id=v_project_id and ctl.state='running' and ctl.generation>0",PEEK)
  self.assertIn("then return '[]'::jsonb; end if;",PEEK)
  self.assertLess(PEEK.index("ctl.project_id=v_project_id"),PEEK.index("from public.factory_change_set_work_units u"))
  self.assertIn("if v_team_status is distinct from 'ready' then return '[]'::jsonb",PEEK)
 def test_acl_does_not_widen_legacy_dispatch_or_public_api(self):
  self.assertIn("revoke all on function public.factory_portfolio_candidates(integer) from public,anon,authenticated",SQL)
  self.assertIn("revoke all on function public.factory_peek_planned_work(text,integer) from public,anon,authenticated",SQL)
  self.assertIn("grant execute on function public.factory_peek_planned_work(text,integer) to service_role",SQL)
  self.assertNotIn("grant execute on function public.factory_dispatch_next_planned_task",SQL)
  self.assertNotIn("grant execute on function public.factory_dispatch_preapproved_planned_task(",SQL)
 def test_runtime_uses_v2_transactional_claims(self):
  adapter=(ROOT/"src/ai_product_factory/supabase_backlog_dispatch.py").read_text()
  self.assertIn('self._rpc("factory_peek_planned_work"',adapter)
  self.assertIn('self._rpc("factory_dispatch_preapproved_planned_task_v2"',adapter)
  self.assertNotIn('self._rpc("factory_dispatch_next_planned_task"',adapter)
if __name__=="__main__": unittest.main()
