import json,unittest
from unittest.mock import patch
from ai_product_factory.supabase_delivery_store import SupabaseDeliveryStore
class Response:
 def __init__(self,data):self.data=data
 def __enter__(self):return self
 def __exit__(self,*a):return False
 def read(self):return json.dumps(self.data).encode() if self.data is not None else b""
class Tests(unittest.TestCase):
 def test_status_uses_rpc(self):
  with patch("urllib.request.urlopen",return_value=Response({"run_id":"r","task_id":"t","status":"pr_open","candidate_commit":"abc"})) as call:
   out=SupabaseDeliveryStore(url="https://x.supabase.co",service_role_key="secret").update_run_status("r","pr_open",candidate_commit="abc")
  self.assertEqual(out.candidate_commit,"abc");self.assertTrue(call.call_args.args[0].full_url.endswith("/rpc/factory_update_run_delivery_status"));self.assertNotIn(b"secret",call.call_args.args[0].data)
 def test_tool_usage_uses_rpc(self):
  with patch("urllib.request.urlopen",return_value=Response(9)) as call:
   out=SupabaseDeliveryStore(url="https://x.supabase.co",service_role_key="secret").record_tool_usage(run_id="r",tool_family="github",operation="commit",estimated_cost=0)
  self.assertEqual(out,9);self.assertTrue(call.call_args.args[0].full_url.endswith("/rpc/factory_record_delivery_tool_usage"))
 def test_console_release_finalization_uses_bounded_rpc(self):
  with patch("urllib.request.urlopen",return_value=Response({"run_id":"r","task_id":"t","status":"merged","merge_sha":"m","idempotent":False})) as call:
   out=SupabaseDeliveryStore(url="https://x.supabase.co",service_role_key="secret").finalize_console_human_release("r",candidate_commit="abc",merge_sha="m")
  self.assertEqual(out["status"],"merged")
  req=call.call_args.args[0]
  self.assertTrue(req.full_url.endswith("/rpc/factory_finalize_console_human_release"))
  self.assertIn(b'"p_candidate_commit": "abc"',req.data)
  self.assertIn(b'"p_merge_sha": "m"',req.data)
if __name__=="__main__":unittest.main()
