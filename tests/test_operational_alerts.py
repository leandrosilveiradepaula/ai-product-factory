import unittest
from decimal import Decimal
from ai_product_factory.operational_alerts import OperationalHealth,evaluate_operational_alerts
class Tests(unittest.TestCase):
 def test_healthy_has_no_alerts(self):self.assertEqual(evaluate_operational_alerts(OperationalHealth()),())
 def test_incidents_generate_alerts(self):
  alerts=evaluate_operational_alerts(OperationalHealth(expired_leases=1,dead_letter_runs=2,failed_runs=3,unknown_cost_events=1))
  self.assertEqual({a.code for a in alerts},{"expired_lease","dead_letter","failed_runs","unknown_cost"})
 def test_budget_exhaustion_is_critical(self):
  alerts=evaluate_operational_alerts(OperationalHealth(known_cost=Decimal("5"),budget=Decimal("5")))
  self.assertEqual(alerts[0].code,"budget_exhausted");self.assertEqual(alerts[0].severity,"critical")
 def test_missing_ci_after_one_dispatch_alerts_once(self):
  from ai_product_factory.operational_alerts import OPERATIONAL_ALERT_CODES
  alerts=evaluate_operational_alerts(OperationalHealth(stale_ci_dispatches=2))
  self.assertEqual([(a.code,a.severity) for a in alerts],[("stalled_ci","warning")])
  self.assertIn("stalled_ci",OPERATIONAL_ALERT_CODES)
  self.assertIn("2 CI candidate(s)",alerts[0].message)
 def test_stale_preview_warning(self):
  alerts=evaluate_operational_alerts(OperationalHealth(stale_preview_runs=3))
  self.assertEqual([(a.code,a.severity) for a in alerts],[("stale_preview","warning")])
if __name__=="__main__":unittest.main()
