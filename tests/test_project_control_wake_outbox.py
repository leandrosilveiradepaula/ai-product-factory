import unittest
from pathlib import Path
from unittest.mock import MagicMock
from ai_product_factory.project_control_wake_outbox import ControlWakeOutbox

ROOT = Path(__file__).resolve().parents[1]

class Tests(unittest.TestCase):
 def test_sql_contract(self):
  sql=(ROOT/"supabase/migrations/20261019002000_project_control_wake_outbox.sql").read_text()
  for marker in ("after insert on public.factory_project_execution_commands",
   "new.command not in ('start','resume','restart')",
   "unique(project_id,command_id)","for update skip locked",
   "enable row level security","status='suppressed'","status='exhausted'",
   "lease_until<=now()","factory_observe_project_control_wakes",
   "'project.control.wake_delivery_acknowledged'","'project.control.wake_observed'",
   "to service_role"):
   self.assertIn(marker,sql)
  self.assertEqual(sql.count("create function public.factory_"),4)
 def test_console_dispatch_after_commit(self):
  control=(ROOT/"apps/console/lib/control-plane.ts").read_text()
  command=control.split("export async function commandProjectExecution",1)[1].split("export async function enqueueProjectBootstrap",1)[0]
  self.assertIn("deliverProjectControlWake(commandId)",command)
  self.assertLess(command.index("if(!response.ok)"),command.index("deliverProjectControlWake(commandId)"))
 def test_worker_observes_no_dispatch_or_model(self):
  worker=(ROOT/"src/ai_product_factory/project_control_wake_outbox.py").read_text()
  wf=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
  self.assertIn("--mode project-control-wake",wf)
  for forbidden in ("OPENAI_API_KEY","merge_pull_request","workflow_dispatch"):
   self.assertNotIn(forbidden,worker)
 def test_empty(self):
  out=ControlWakeOutbox(url="https://example.supabase.co",service_role_key="secret")
  out.rpc=MagicMock(return_value={"observed":0,"suppressed":0})
  self.assertEqual(out.observe_one(owner="gha-1"),{"status":"empty","observed":False})
 def test_observed(self):
  out=ControlWakeOutbox(url="https://example.supabase.co",service_role_key="secret")
  out.rpc=MagicMock(return_value={"observed":2,"suppressed":1})
  answer=out.observe_batch(owner="gha-1",limit=3)
  self.assertEqual(answer["observed_count"],2)
  self.assertEqual(answer["suppressed_count"],1)
  self.assertEqual(out.rpc.call_args.args[0],"factory_observe_project_control_wakes")
 def test_invalid_results(self):
  out=ControlWakeOutbox(url="https://example.supabase.co",service_role_key="secret")
  out.rpc=MagicMock(return_value={"observed":4,"suppressed":0})
  with self.assertRaises(RuntimeError):out.observe_batch(owner="gha-1",limit=3)
 def test_invalid_owner(self):
  out=ControlWakeOutbox(url="https://example.supabase.co",service_role_key="secret")
  with self.assertRaises(ValueError):out.observe_one(owner="bad owner")
