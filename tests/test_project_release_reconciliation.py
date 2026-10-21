import unittest
from ai_product_factory.project_release_reconciliation import SupabaseProjectReleaseReconciler
P="11111111-1111-4111-8111-111111111111"
R="22222222-2222-4222-8222-222222222222"
M="b"*40
C="a"*40
REPORT={"project_id":P,"run_id":R,"candidate_commit":C,"status":"released",
        "report":{"merge_sha":M,"product_readiness":{"ready":False,"status":"not_assessed"}}}
class Tests(unittest.TestCase):
 def test_exact_report_and_one_atomic_mutation(self):
  calls=[]
  rec=object.__new__(SupabaseProjectReleaseReconciler)
  def req(method,path,payload=None):
   calls.append((method,path,payload))
   return [REPORT] if method=="GET" else {"project_id":P,"merge_sha":M,"idempotent":False,"lifecycle_stage":"operations"}
  rec._request=req
  self.assertEqual(rec.reconcile(project_id=P,run_id=R,merge_sha=M)["lifecycle_stage"],"operations")
  self.assertEqual([x[0] for x in calls],["GET","POST"])
  self.assertIn("rpc/factory_reconcile_project_release_atomic",calls[1][1])
  self.assertEqual(len(calls[1][2]["p_followup"]["pending_domains"]),6)
 def test_absent_report_cannot_fallback_to_three_writes(self):
  calls=[]
  rec=object.__new__(SupabaseProjectReleaseReconciler)
  def req(method,path,payload=None):
   calls.append((method,path))
   if method=="GET":return []
   raise RuntimeError("RPC unavailable")
  rec._request=req
  with self.assertRaisesRegex(RuntimeError,"RPC unavailable"):
   rec.reconcile(project_id=P,run_id=R,merge_sha=M)
  self.assertEqual([x[0] for x in calls],["GET","POST"])
 def test_receipt_validation(self):
  rec=object.__new__(SupabaseProjectReleaseReconciler)
  rec._request=lambda method,path,payload=None: [REPORT] if method=="GET" else {"idempotent":True}
  with self.assertRaisesRegex(RuntimeError,"invalid atomic"):
   rec.reconcile(project_id=P,run_id=R,merge_sha=M)
if __name__=="__main__":unittest.main()
