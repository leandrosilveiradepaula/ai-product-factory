"""Recovery and ad-hoc worker invocations cannot bypass route-specific readiness."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()


class RouteIsolatedRecoveryContract(unittest.TestCase):
 def test_recovery_does_not_schedule_work(self):
  body=RUNTIME.split("def run_recovery_once(",1)[1].split("\ndef run_product_once(",1)[0]
  self.assertNotIn("schedule_next(",body)
  self.assertNotIn("schedule_run(",body)
  self.assertNotIn("schedule_eligible_direct(",body)
  self.assertIn("scheduler.recover_expired()",body)
  self.assertIn('"deferred_to_readiness_gated_dispatch":True',body)

 def test_workers_use_only_own_assigned_route(self):
  for name,route,next_name in (
   ("run_direct_once","direct","run_codex_once"),
   ("run_codex_once","codex","run_change_set_integration_once"),
  ):
   body=RUNTIME.split("def "+name+"(",1)[1].split("\ndef "+next_name+"(",1)[0]
   self.assertIn('_select_assigned_route_run(scheduler,"'+route+'"',body)
   self.assertNotIn("scheduler.schedule_next()",body)
  self.assertIn('items=matrix.get(route)',RUNTIME)
  self.assertIn('if route not in {"direct","codex"}:',RUNTIME)


if __name__=="__main__":
 unittest.main()
