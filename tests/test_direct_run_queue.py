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
  d={"run_id":"r","task_id":"t","project_key":"p","repository":"owner/repo","issue_number":None,"title":"x","description":"y","branch":"factory/task-t","human_gate_required":False}
  with patch("urllib.request.urlopen",return_value=Response(d)):
   item=SupabaseDirectRunQueue(url="https://x.supabase.co",service_role_key="secret").claim_next("w")
  self.assertEqual(item.repository,"owner/repo");self.assertIsNone(item.issue_number)
 def test_empty_queue(self):
  with patch("urllib.request.urlopen",return_value=Response(None)):
   self.assertIsNone(SupabaseDirectRunQueue(url="https://x.supabase.co",service_role_key="secret").claim_next("w"))
if __name__=="__main__":unittest.main()
