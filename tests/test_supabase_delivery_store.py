import io,json,unittest,urllib.error
from unittest.mock import patch,MagicMock
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
 def test_rpc_error_exposes_only_stable_provider_code(self):
  error=urllib.error.HTTPError("https://x.supabase.co/rest/v1/rpc/x",403,"forbidden",None,io.BytesIO(b'{"code":"42501","message":"permission denied for table secret_rows"}'))
  with patch("urllib.request.urlopen",side_effect=error):
   with self.assertRaisesRegex(RuntimeError,r"factory_update_run_delivery_status \(403; code=42501\)") as raised:
    SupabaseDeliveryStore(url="https://x.supabase.co",service_role_key="secret").update_run_status("r","completed")
  self.assertNotIn("secret_rows",str(raised.exception))
 def test_rpc_error_rejects_untrusted_provider_code(self):
  error=urllib.error.HTTPError("https://x.supabase.co/rest/v1/rpc/x",403,"forbidden",None,io.BytesIO(b'{"code":"raw error detail must not leak"}'))
  with patch("urllib.request.urlopen",side_effect=error):
   with self.assertRaisesRegex(RuntimeError,r"code=unknown") as raised:
    SupabaseDeliveryStore(url="https://x.supabase.co",service_role_key="secret").update_run_status("r","completed")
  self.assertNotIn("raw error",str(raised.exception))
 def test_rpc_error_preserves_only_bounded_broker_forbidden_code(self):
  error=urllib.error.HTTPError("https://x.supabase.co/rest/v1/rpc/x",403,"forbidden",None,io.BytesIO(b'{"error":"forbidden","detail":"do not leak"}'))
  with patch("urllib.request.urlopen",side_effect=error):
   with self.assertRaisesRegex(RuntimeError,r"code=broker_forbidden") as raised:
    SupabaseDeliveryStore(url="https://x.supabase.co",service_role_key="secret").update_run_status("r","completed")
  self.assertNotIn("do not leak",str(raised.exception))
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
  assessment=assess_product_readiness(assessed_commit="a"*40,assessment_ref="audit:1",domains=domains)
  responses=[Response([{"id":"eval"}]),Response([{"id":1}])]
  with patch("urllib.request.urlopen",side_effect=responses) as call:
   out=SupabaseDeliveryStore(url="https://x.supabase.co",service_role_key="secret").record_product_readiness(run_id="r",assessment=assessment)
  self.assertEqual(out,[{"id":"eval"}])
  eval_payload=json.loads(call.call_args_list[0].args[0].data.decode())
  self.assertEqual(eval_payload["eval_type"],"product_readiness")
  self.assertEqual(eval_payload["baseline_ref"],"a"*40)
  self.assertEqual(eval_payload["status"],"passed")
  self.assertTrue(eval_payload["result"]["ready"])
  audit_payload=json.loads(call.call_args_list[1].args[0].data.decode())
  self.assertEqual(audit_payload["event_type"],"product_readiness.assessed")

 def test_certification_uses_atomic_service_only_rpcs(self):
  store=SupabaseDeliveryStore.__new__(SupabaseDeliveryStore)
  store._rpc=MagicMock(side_effect=[
   {"certification_id":"c","run_id":"r","assessed_commit":"a"*40},
   {"run_id":"r","assessed_commit":"a"*40,"evaluation_status":"failed"},
  ])
  begun=store.begin_product_readiness_certification(project_key="factory",repository="owner/repo",assessed_commit="a"*40,evidence_digest="b"*64)
  domains={key:{"status":"failed","reason":"blocked","evidence":["e"],"coverage":[],"verification_state":""} for key in REQUIRED_DOMAINS}
  assessment=assess_product_readiness(assessed_commit="a"*40,assessment_ref="x",domains=domains)
  saved=store.persist_product_readiness_certification(certification_id="c",run_id="r",assessment=assessment,report={"criteria":{}},evidence_digest="b"*64)
  self.assertEqual((begun["run_id"],saved["evaluation_status"]),("r","failed"))
  self.assertEqual(store._rpc.call_args_list[0].args[0],"factory_begin_product_readiness_certification_v1")
  self.assertEqual(store._rpc.call_args_list[1].args[0],"factory_persist_product_readiness_certification_v1")

 def test_closed_pr_reconciliation_uses_narrow_rpc_and_validates_output(self):
     store=SupabaseDeliveryStore.__new__(SupabaseDeliveryStore)
     store._rpc=MagicMock(return_value={
         "run_id":"r","status":"cancelled","change_set_status":"superseded","idempotent":False})
     result=store.reconcile_closed_preview_candidate(
         "r",candidate_commit="a"*40,pr_number=19,
         github_state="closed",github_merged=False)
     self.assertEqual(result["status"],"cancelled")
     store._rpc.assert_called_once_with("factory_reconcile_closed_preview_candidate",{
         "p_run_id":"r","p_candidate_commit":"a"*40,"p_pr_number":19,
         "p_github_state":"closed","p_github_merged":False})

 def test_closed_pr_reconciliation_fails_closed_before_rpc(self):
     store=SupabaseDeliveryStore.__new__(SupabaseDeliveryStore)
     store._rpc=MagicMock()
     for state,merged in (("open",False),("closed",True),("closed",None)):
         with self.subTest(state=state,merged=merged):
             with self.assertRaises(ValueError):
                 store.reconcile_closed_preview_candidate(
                     "r",candidate_commit="a"*40,pr_number=19,
                     github_state=state,github_merged=merged)
     store._rpc.assert_not_called()

 def test_closed_pr_reconciliation_rejects_inconsistent_rpc_result(self):
     store=SupabaseDeliveryStore.__new__(SupabaseDeliveryStore)
     store._rpc=MagicMock(return_value={
         "run_id":"r","status":"completed","change_set_status":"completed"})
     with self.assertRaises(RuntimeError):
         store.reconcile_closed_preview_candidate(
             "r",candidate_commit="a"*40,pr_number=19,
             github_state="closed",github_merged=False)

 def test_preview_merge_browser_inventory_skips_unrelated_legacy_arrays(self):
  repo="leandrosilveiradepaula/crm-infodive"
  sha="d84f41938a5e36b4b5f86133434c900c433bffc1"
  verified={
   "id":"12345678-1234-4123-8123-123456789012",
   "evidence":{
    "target_repository":repo,"candidate_commit":sha,
    "preview":{"provider":"vercel","status":"browser_verified",
               "url":"https://crm-example.vercel.app",
               "browser_verifier_run_id":12345}
   },
   "source_status":{"browser_visual_validation":"success","vercel_preview":"resolved"},
   "constraints":{"production_merge_authorized":False},
   "gaps":[]
  }
  rows=[
   {"id":"77777777-0000-4000-8000-000000000000",
    "evidence":[{"domain":"security","status":"passed"}],
    "constraints":[],"source_status":{},"gaps":[]},
   {"id":"77777777-0000-4000-8000-000000000001",
    "evidence":{"target_repository":repo,"candidate_commit":"f"*40,
                "preview":[]},
    "constraints":{},"source_status":{},"gaps":[]},
   verified,
  ]
  with patch("urllib.request.urlopen",return_value=Response(rows)) as request:
   out=SupabaseDeliveryStore(
    url="https://x.supabase.co",service_role_key="secret"
   ).find_verified_nonproduction_browser_snapshot(
    project_id="2d30e00a-ff72-4044-b838-011c263ed672",
    repository=repo,merge_sha=sha,
   )
  self.assertEqual(out,{"snapshot_id":verified["id"],
                        "preview_url":"https://crm-example.vercel.app",
                        "verifier_run_id":12345})
  self.assertEqual(request.call_count,1)
  self.assertIn("limit=50",request.call_args.args[0].full_url)

 def test_preview_merge_browser_missing_exact_receipt_waits(self):
  with patch("urllib.request.urlopen",return_value=Response([
   {"id":"77777777-0000-4000-8000-000000000000",
    "evidence":[{"unrelated":"legacy"}],"gaps":[]}
  ])):
   result=SupabaseDeliveryStore(
    url="https://x.supabase.co",service_role_key="secret"
   ).find_verified_nonproduction_browser_snapshot(
    project_id="2d30e00a-ff72-4044-b838-011c263ed672",
    repository="leandrosilveiradepaula/crm-infodive",
    merge_sha="d84f41938a5e36b4b5f86133434c900c433bffc1",
   )
  self.assertIsNone(result)

 def test_preview_merge_matching_malformed_receipts_fail_closed(self):
  repo="leandrosilveiradepaula/crm-infodive"
  sha="d84f41938a5e36b4b5f86133434c900c433bffc1"
  for preview in ([],{},{"provider":"vercel","status":"browser_verified",
                        "url":"https://example.com","browser_verifier_run_id":10}):
   with self.subTest(preview=preview):
    with patch("urllib.request.urlopen",return_value=Response([
     {"id":"11111111-1111-4111-8111-111111111111",
      "evidence":{"target_repository":repo,"candidate_commit":sha,
                  "preview":preview},
      "source_status":{"browser_visual_validation":"success",
                       "vercel_preview":"resolved"},
      "constraints":{"production_merge_authorized":False},
      "gaps":[]}
    ])):
     with self.assertRaisesRegex(RuntimeError,"not a verified exact merge"):
      SupabaseDeliveryStore(
       url="https://x.supabase.co",service_role_key="secret"
      ).find_verified_nonproduction_browser_snapshot(
       project_id="2d30e00a-ff72-4044-b838-011c263ed672",
       repository=repo,merge_sha=sha)
  
if __name__=="__main__":unittest.main()
