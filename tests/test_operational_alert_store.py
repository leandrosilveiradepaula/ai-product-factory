import unittest
from ai_product_factory.operational_alerts import OperationalAlert
from ai_product_factory.operational_alert_store import OperationalAlertRecorder
class Store:
 def __init__(self):self.events=[]
 def record_audit_event(self,**kw):self.events.append(kw)
class Tests(unittest.TestCase):
 def test_records_only_supplied_active_alerts(self):
  s=Store();n=OperationalAlertRecorder(s).record_for_run(run_id="r1",alerts=(OperationalAlert("dead_letter","critical","exhausted"),))
  self.assertEqual(n,1);self.assertEqual(s.events[0]["payload"]["code"],"dead_letter")
 def test_empty_alerts_are_silent(self):
  s=Store();self.assertEqual(OperationalAlertRecorder(s).record_for_run(run_id="r1",alerts=()),0);self.assertEqual(s.events,[])
if __name__=="__main__":unittest.main()
