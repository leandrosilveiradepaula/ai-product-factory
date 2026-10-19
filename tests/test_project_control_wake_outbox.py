import unittest
from pathlib import Path
from unittest.mock import MagicMock
from ai_product_factory.project_control_wake_outbox import ControlWakeOutbox
ROOT=Path(__file__).resolve().parents[1]
class Tests(unittest.TestCase):
 def test_only_commands_generate_durable_wakes(self):
  sql=(ROOT/"supabase/migrations/20261019002000_project_control_wake_outbox.sql").read_text()
  for marker in ("after insert on public.factory_project_execution_commands",
     "new.command not in ('start','resume','restart')","unique(project_id,command_id)",
     "for update skip locked","enable row level security",
     "status='suppressed'","status='exhausted'","lease_until<=now()",
     "p_result not in ('dispatched','observed','failed')","to service_role"):
   self.assertIn(marker,sql)
  self.assertEqual(sql.count("create function public.factory_"),3)
 def test_console_has_postcommit_wake_only(self):
  control=(ROOT/"apps/console/lib/control-plane.ts").read_text()
  command=control.split("export async function commandProjectExecution",1)[1].split("export async function enqueueProjectBootstrap",1)[0]
  self.assertIn("deliverProjectControlWake(commandId)",command)
  self.assertLess(command.index('if(!response.ok)'),command.index("deliverProjectControlWake(commandId)"))
  self.assertIn("result.state",command)
  self.assertNotIn("deliverProjectControlWake(commandId)",control.split("export async function commandProjectExecution",1)[0])
 def test_worker_observes_not_dispatches_or_calls_model(self):
  worker=(ROOT/"src/ai_product_factory/project_control_wake_outbox.py").read_text()
  wf=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
  self.assertIn("--mode project-control-wake",wf)
  for forbidden in ("OPENAI_API_KEY","merge_pull_request","workflow_dispatch"):
   self.assertNotIn(forbidden,worker)
 def test_empty(self):
  out=ControlWakeOutbox(url="https://example.supabase.co",service_role_key="secret")
  out.rpc=lambda *_:None
  self.assertEqual(out.observe_one(owner="gha-1"),{"status":"empty","observed":False})
 def test_observed(self):
  out=ControlWakeOutbox(url="https://example.supabase.co",service_role_key="secret")
  out.rpc=MagicMock(side_effect=[
   {"id":"123","status":"claimed","attempt":1},
   {"id":"123","status":"observed"}
  ])
  self.assertTrue(out.observe_one(owner="gha-1")["observed"])
  self.assertEqual(out.rpc.call_args.args[1]["p_result"],"observed")
 def test_unapplied_migration_is_inert_for_scheduled_runner(self):
  from unittest.mock import patch
  from urllib.error import HTTPError
  out=ControlWakeOutbox(url="https://example.supabase.co",service_role_key="secret")
  missing=HTTPError("https://example.supabase.co/rest/v1/rpc/factory_claim_project_control_wake",404,"not found",{},None)
  with patch("urllib.request.urlopen",side_effect=missing):
   result=out.observe_one(owner="gha-123")
  self.assertEqual(result,{"status":"unconfigured","observed":False})

 def test_scheduler_observes_only_after_queue_probe(self):
  workflow=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
  self.assertLess(workflow.index("Probe durable work queues without side effects"),
                  workflow.index("Observe committed project control wake"))
  self.assertIn("steps.probe.outcome == 'success'",workflow.split("Observe committed project control wake",1)[1].split("- name:",1)[0])

 def test_pre_migration_console_preserves_old_committed_wake(self):
  ts=(ROOT/"apps/console/lib/project-control-wake-outbox.ts").read_text()
  self.assertIn('===404)',ts)
  self.assertIn("return requestIntakeWorkerWake()",ts)
  function=(ROOT/"apps/console/lib/control-plane.ts").read_text()
  segment=function.split("export async function commandProjectExecution",1)[1].split("export async function enqueueProjectBootstrap",1)[0]
  self.assertLess(segment.index('if(!response.ok)'),segment.index("deliverProjectControlWake(commandId)"))

 def test_invalid_owner(self):
  out=ControlWakeOutbox(url="https://example.supabase.co",service_role_key="secret")
  with self.assertRaises(ValueError):out.observe_one(owner="bad owner")
