import unittest
from ai_product_factory.browser_evidence import BrowserEvidence
from ai_product_factory.browser_evidence_store import BrowserEvidenceRecorder
class Store:
 def __init__(self):self.evals=[];self.audit=[]
 def record_evaluation(self,**kw):self.evals.append(kw)
 def record_audit_event(self,**kw):self.audit.append(kw)
class Tests(unittest.TestCase):
 def test_records_success(self):
  s=Store();e=BrowserEvidence("success","https://preview.example",("page_load","console_clean"))
  BrowserEvidenceRecorder(s).record(run_id="r1",evidence=e)
  self.assertEqual(s.evals[0]["eval_type"],"browser_e2e");self.assertEqual(s.audit[0]["event_type"],"preview.browser_evidence_recorded")
 def test_failure_is_recorded_then_rejected(self):
  s=Store()
  with self.assertRaises(ValueError):BrowserEvidenceRecorder(s).record(run_id="r1",evidence=BrowserEvidence("failure","https://preview.example",detail="console error"))
  self.assertEqual(s.evals[0]["status"],"failure")
if __name__=="__main__":unittest.main()
