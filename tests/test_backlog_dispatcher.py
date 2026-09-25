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

if __name__=="__main__":unittest.main()
