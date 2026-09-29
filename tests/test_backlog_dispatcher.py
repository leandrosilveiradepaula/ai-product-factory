import unittest
from ai_product_factory.backlog_dispatcher import BacklogDispatcher,PlannedTask
from ai_product_factory.models import ExecutionRoute

class BacklogDispatcherTests(unittest.TestCase):
 def test_small_task_routes_direct_without_gate(self):
  d=BacklogDispatcher().decide(PlannedTask("t","p","small","x","low",{},{"estimated_files":2}))
  self.assertEqual(d.execution.route,ExecutionRoute.DIRECT);self.assertFalse(d.execution.human_gate_required)
 def test_complex_refactor_routes_codex_without_invoking_it(self):
  d=BacklogDispatcher().decide(PlannedTask("t","p","refactor","x","very_high",{},{"large_refactor":True,"estimated_files":20}))
  self.assertEqual(d.execution.route,ExecutionRoute.CODEX);self.assertTrue(d.execution.codex.should_use)
 def test_production_risk_is_independent_from_execution_route(self):
  d=BacklogDispatcher().decide(PlannedTask("t","p","config","x","low",{"production_change":True},{"estimated_files":1}))
  self.assertEqual(d.execution.route,ExecutionRoute.DIRECT);self.assertTrue(d.execution.human_gate_required)

 def test_profiles_routing_telemetry_without_model_call(self):
  d=BacklogDispatcher().decide(PlannedTask("t","p","impact","x","medium",{},{
   "estimated_files":5,"impacted_components":9,"impact_unknowns":4,
   "historical_repair_rate":0.45,"historical_direct_first_pass":0.5,
   "historical_codex_first_pass":0.8,"historical_codex_cost_ratio":1.5,
  }))
  self.assertEqual(d.profile.impacted_components,9)
  self.assertEqual(d.profile.impact_unknowns,4)
  self.assertEqual(d.execution.codex.policy_version,"v2")
  self.assertEqual(d.execution.route,ExecutionRoute.CODEX)
 def test_invalid_historical_rate_fails_closed(self):
  with self.assertRaises(ValueError):
   BacklogDispatcher().decide(PlannedTask("t","p","bad","x","low",{},{"historical_repair_rate":1.5}))

if __name__=="__main__":unittest.main()
