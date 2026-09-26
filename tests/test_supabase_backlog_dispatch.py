import json,unittest
from unittest.mock import patch
from ai_product_factory.models import ExecutionRoute
from ai_product_factory.supabase_backlog_dispatch import SupabaseBacklogDispatch
class Response:
 def __init__(self,data):self.data=data
 def __enter__(self):return self
 def __exit__(self,*a):return False
 def read(self):return json.dumps(self.data).encode() if self.data is not None else b""
class Tests(unittest.TestCase):
 def test_claims_and_records_route(self):
  claimed={"run_id":"r","task_id":"t","project_id":"p","project_key":"demo","title":"small","description":"x","complexity":"low","risk":{},"metadata":{"estimated_files":1}}
  with patch("urllib.request.urlopen",side_effect=[Response(claimed),Response(None)]) as call:
   d=SupabaseBacklogDispatch(url="https://example.supabase.co",service_role_key="secret").dispatch_next("demo")
  self.assertEqual(d.execution.route,ExecutionRoute.DIRECT);self.assertEqual(call.call_count,2);self.assertNotIn(b"secret",call.call_args_list[0].args[0].data)
 def test_empty_backlog_returns_none_without_decision_write(self):
  with patch("urllib.request.urlopen",return_value=Response(None)) as call:
   d=SupabaseBacklogDispatch(url="https://example.supabase.co",service_role_key="secret").dispatch_next("demo")
  self.assertIsNone(d);self.assertEqual(call.call_count,1)

 def test_global_dispatch_uses_oldest_active_project(self):
  claimed={"run_id":"r","task_id":"t","project_id":"p","project_key":"demo","title":"small","description":"x","complexity":"low","risk":{},"metadata":{"estimated_files":1}}
  responses=[
   Response([{"project_id":"p"}]),
   Response([{"project_key":"demo"}]),
   Response(claimed),
   Response(None),
  ]
  with patch("urllib.request.urlopen",side_effect=responses) as call:
   d=SupabaseBacklogDispatch(url="https://example.supabase.co",service_role_key="secret").dispatch_next_any()
  self.assertEqual(d.task.project_key,"demo")
  self.assertEqual(call.call_count,4)

 def test_global_dispatch_empty_is_read_only(self):
  with patch("urllib.request.urlopen",return_value=Response([])) as call:
   d=SupabaseBacklogDispatch(url="https://example.supabase.co",service_role_key="secret").dispatch_next_any()
  self.assertIsNone(d)
  self.assertEqual(call.call_count,1)
if __name__=="__main__":unittest.main()
