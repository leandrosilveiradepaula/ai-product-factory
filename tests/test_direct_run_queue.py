import json,unittest
from unittest.mock import patch
from ai_product_factory.direct_run_queue import SupabaseDirectRunQueue
class Response:
 def __init__(self,data):self.data=data
 def __enter__(self):return self
 def __exit__(self,*a):return False
 def read(self):return json.dumps(self.data).encode() if self.data is not None else b""
class Tests(unittest.TestCase):
 def test_claim_maps_direct_item(self):
  d={"run_id":"r","project_id":"project-uuid","execution_generation":1,"task_id":"t","project_key":"p","repository":"owner/repo","issue_number":None,"title":"x","description":"y","branch":"factory/task-t","human_gate_required":False}
  with patch("urllib.request.urlopen",return_value=Response(d)):
   item=SupabaseDirectRunQueue(url="https://x.supabase.co",service_role_key="secret").claim_next("w")
  self.assertEqual(item.repository,"owner/repo");self.assertIsNone(item.issue_number)
 def test_empty_queue(self):
  with patch("urllib.request.urlopen",return_value=Response(None)):
   self.assertIsNone(SupabaseDirectRunQueue(url="https://x.supabase.co",service_role_key="secret").claim_next("w"))

 def test_claim_rejects_stale_identity_and_invalid_epoch(self):
     base={"run_id":"run-1","agent_key":"development","project_id":"project-uuid","execution_generation":2,"task_id":"task","project_key":"p","repository":"owner/repo","title":"Work","branch":"factory/work"}
     queue=SupabaseDirectRunQueue(url="https://x.supabase.co",service_role_key="secret")
     cases=[
         ({"run_id":"different"},"different run ID"),
         ({"agent_key":"review"},"different assigned agent"),
         ({"execution_generation":0},"invalid execution generation"),
         ({"execution_generation":True},"invalid execution generation"),
         ({"execution_generation":"2"},"invalid execution generation"),
         ({"project_id":""},"missing project capability"),
     ]
     for override,message in cases:
         with self.subTest(override=override),patch("urllib.request.urlopen",return_value=Response({**base,**override})):
             with self.assertRaisesRegex(RuntimeError,message):
                 queue.claim_next("worker",agent_key="development",run_id="run-1")

 def test_rejects_invalid_routed_contract(self):
  base={"run_id":"run","project_id":"project","execution_generation":1,"task_id":"task","project_key":"demo","repository":"owner/repo","title":"Work","branch":"factory/work","human_gate_required":False}
  cases=[
   ({"run_id":""},"missing required run_id"),
   ({"repository":""},"missing required repository"),
   ({"title":None},"missing required title"),
   ({"human_gate_required":"false"},"invalid human gate"),
   ({"wave":True},"invalid wave"),
   ({"wave":0},"invalid wave"),
   ({"change_set_id":"cs"},"incomplete change set binding"),
   ({"work_unit_id":"wu"},"incomplete change set binding"),
  ]
  queue=SupabaseDirectRunQueue(url="https://x.supabase.co",service_role_key="secret")
  for override,message in cases:
   with self.subTest(override=override),patch("urllib.request.urlopen",return_value=Response({**base,**override})):
    with self.assertRaisesRegex(RuntimeError,message):
     queue.claim_next("worker")

 def test_rejects_incoherent_claim_metadata(self):
  base={"run_id":"run","project_id":"project","execution_generation":1,"task_id":"task","project_key":"demo","repository":"owner/repo","title":"Work","branch":"factory/work"}
  cases=[
   ({"issue_number":True},"invalid issue number"),
   ({"issue_number":0},"invalid issue number"),
   ({"wave":2},"wave requires change set binding"),
   ({"change_set_id":"cs","work_unit_id":"wu","wave":2},""),
   ({"change_set_id":123,"work_unit_id":"wu"},"invalid change_set_id"),
   ({"change_set_id":"cs","work_unit_id":123},"invalid work_unit_id"),
   ({"description":[]},"invalid description"),
  ]
  queue=SupabaseDirectRunQueue(url="https://x.supabase.co",service_role_key="secret")
  for override,message in cases:
   if not message:continue
   with self.subTest(override=override),patch("urllib.request.urlopen",return_value=Response({**base,**override})):
    with self.assertRaisesRegex(RuntimeError,message):
     queue.claim_next("worker")

 def test_claim_requires_coherent_wave_and_codex_level(self):
  base={"run_id":"run","project_id":"project","execution_generation":1,"task_id":"task","project_key":"demo","repository":"owner/repo","title":"Work","branch":"factory/work"}
  cases=[
   ({"change_set_id":"cs","work_unit_id":"wu"},"change set requires wave"),
  ]
  queue=SupabaseDirectRunQueue(url="https://x.supabase.co",service_role_key="secret")
  for override,message in cases:
   with self.subTest(override=override),patch("urllib.request.urlopen",return_value=Response({**base,**override})):
    with self.assertRaisesRegex(RuntimeError,message):
     queue.claim_next("worker")

 def test_invalid_claim_filters_do_not_contact_control_plane(self):
  queue=SupabaseDirectRunQueue(url="https://x.supabase.co",service_role_key="secret")
  with patch("urllib.request.urlopen") as request:
   for args in [("",None,None),("worker","",None),("worker",None,"")]:
    with self.subTest(args=args),self.assertRaises(ValueError):
     queue.claim_next(args[0],agent_key=args[1],run_id=args[2])
   request.assert_not_called()

if __name__=="__main__":unittest.main()
