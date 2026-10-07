import json,unittest
from unittest.mock import patch
from ai_product_factory.supabase_delivery_store import SupabaseDeliveryStore
from ai_product_factory.product_readiness import assess_product_readiness,REQUIRED_COVERAGE_BY_DOMAIN,REQUIRED_DOMAINS
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
 def test_resource_limit_signal_uses_existing_rpc_without_inventing_percent(self):
  with patch("urllib.request.urlopen",return_value=Response("snapshot-id")) as call:
   out=SupabaseDeliveryStore(url="https://x.supabase.co",service_role_key="secret").record_resource_limit_signal(
    provider="vercel",resource_key="team",metric_key="deployments_daily",
    quality="provider_blocked",source="preview-runtime-signal",unit="deployments",
    window_key="rolling_24h",metadata={"candidate_commit":"abc"},
   )
  self.assertEqual(out,"snapshot-id")
  req=call.call_args.args[0]
  self.assertTrue(req.full_url.endswith("/rpc/factory_record_resource_limit"))
  payload=json.loads(req.data.decode())
  self.assertIsNone(payload["p_used_value"]);self.assertIsNone(payload["p_limit_value"])
  self.assertEqual(payload["p_quality"],"provider_blocked")
  self.assertEqual(payload["p_metadata"],{"candidate_commit":"abc"})
 def test_console_release_finalization_uses_bounded_rpc(self):
  with patch("urllib.request.urlopen",return_value=Response({"run_id":"r","task_id":"t","status":"merged","merge_sha":"m","idempotent":False})) as call:
   out=SupabaseDeliveryStore(url="https://x.supabase.co",service_role_key="secret").finalize_console_human_release("r",candidate_commit="abc",merge_sha="m")
  self.assertEqual(out["status"],"merged")
  req=call.call_args.args[0]
  self.assertTrue(req.full_url.endswith("/rpc/factory_finalize_console_human_release"))
  self.assertIn(b'"p_candidate_commit": "abc"',req.data)
  self.assertIn(b'"p_merge_sha": "m"',req.data)
 def test_fail_preview_marks_run_and_task_and_audits(self):
  responses=[
   Response({"run_id":"r","task_id":"t","status":"failed","candidate_commit":"abc"}),
   Response([{"id":"t","status":"failed"}]),
   Response([{"id":1}]),
  ]
  with patch("urllib.request.urlopen",side_effect=responses) as call:
   out=SupabaseDeliveryStore(url="https://x.supabase.co",service_role_key="secret").fail_preview(
    "r",candidate_commit="abc",reason="browser failed"
   )
  self.assertEqual(out.status,"failed")
  self.assertIn("/rpc/factory_update_run_delivery_status",call.call_args_list[0].args[0].full_url)
  self.assertIn("factory_tasks?id=eq.t",call.call_args_list[1].args[0].full_url)
  self.assertIn("factory_audit_events",call.call_args_list[2].args[0].full_url)

 def test_product_readiness_persists_exact_commit_and_audit(self):
  verification={
   "security":"reviewed","observability_operations":"observed","test_strategy":"executed",
   "product_experience":"observed","documentation":"reviewed","functional_completeness":"reviewed",
  }
  domains={
   key:{
    "status":"passed","reason":"verified","evidence":[f"evidence:{key}"],
    "coverage":list(REQUIRED_COVERAGE_BY_DOMAIN[key]),"verification_state":verification[key],
   }
   for key in REQUIRED_DOMAINS
  }
  assessment=assess_product_readiness(assessed_commit="abc",assessment_ref="audit:1",domains=domains)
  responses=[Response([{"id":"eval"}]),Response([{"id":1}])]
  with patch("urllib.request.urlopen",side_effect=responses) as call:
   out=SupabaseDeliveryStore(url="https://x.supabase.co",service_role_key="secret").record_product_readiness(run_id="r",assessment=assessment)
  self.assertEqual(out,[{"id":"eval"}])
  eval_payload=json.loads(call.call_args_list[0].args[0].data.decode())
  self.assertEqual(eval_payload["eval_type"],"product_readiness")
  self.assertEqual(eval_payload["baseline_ref"],"abc")
  self.assertEqual(eval_payload["status"],"passed")
  self.assertTrue(eval_payload["result"]["ready"])
  audit_payload=json.loads(call.call_args_list[1].args[0].data.decode())
  self.assertEqual(audit_payload["event_type"],"product_readiness.assessed")

if __name__=="__main__":unittest.main()
