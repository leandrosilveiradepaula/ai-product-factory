import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock,patch

from ai_product_factory.models import ExecutionRoute
from ai_product_factory.supabase_backlog_dispatch import SupabaseBacklogDispatch


class Response:
 def __init__(self,data):self.data=data
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def read(self):return json.dumps(self.data).encode() if self.data is not None else b""


def candidate(*,complexity="low",metadata=None,task_id="t",work_unit_id="u"):
 return {"task_id":task_id,"project_key":"demo","title":"planned",
  "description":"x","complexity":complexity,"risk":{},
  "metadata":metadata or {"estimated_files":1},
  "work_unit_id":work_unit_id,"fingerprint":"a"*32}


class DispatchTests(unittest.TestCase):
 def make_dispatch(self,allowed_routes,preview,claimed):
  requests=[]
  def urlopen(req,timeout=30):
   body=json.loads(req.data)
   name=req.full_url.rsplit("/",1)[-1]
   requests.append((name,body))
   if name=="factory_peek_planned_work":return Response(preview)
   if name=="factory_dispatch_preapproved_planned_task":return Response(claimed)
   raise AssertionError("unexpected dispatch RPC: "+name)
  with patch("urllib.request.urlopen",side_effect=urlopen):
   decision=SupabaseBacklogDispatch(
     url="https://example.supabase.co",service_role_key="secret"
   ).dispatch_next("demo",allowed_routes=allowed_routes)
  return decision,requests

 def test_atomic_claim_records_route_in_same_rpc(self):
  decision,calls=self.make_dispatch(("direct",),[candidate()],{"run_id":"r","task_id":"t"})
  self.assertEqual(decision.execution.route,ExecutionRoute.DIRECT)
  self.assertEqual(decision.run_id,"r")
  self.assertEqual([x[0] for x in calls],[
    "factory_peek_planned_work","factory_dispatch_preapproved_planned_task"])
  args=calls[1][1]
  self.assertEqual(args["p_route"],"direct")
  self.assertEqual(args["p_work_unit_id"],"u")
  self.assertEqual(args["p_fingerprint"],"a"*32)
  self.assertNotIn("p_run_id",args)
  self.assertNotIn("secret",str(args))

 def test_no_allowed_routes_cannot_even_read_queue(self):
  with patch("urllib.request.urlopen") as request:
   got=SupabaseBacklogDispatch(
     url="https://example.supabase.co",service_role_key="secret"
   ).dispatch_next("demo",allowed_routes=())
  self.assertIsNone(got)
  request.assert_not_called()

 def test_direct_only_cannot_claim_codex_task(self):
  complex_task=candidate(complexity="very_high",metadata={
    "large_refactor":True,"estimated_files":25})
  decision,calls=self.make_dispatch(("direct",),[complex_task],None)
  self.assertIsNone(decision)
  self.assertEqual([name for name,_ in calls],["factory_peek_planned_work"])

 def test_codex_only_skips_direct_and_claims_codex(self):
  complex_task=candidate(complexity="very_high",metadata={
    "large_refactor":True,"estimated_files":25},
    task_id="complex",work_unit_id="complex-unit")
  decision,calls=self.make_dispatch(
    ("codex",),[candidate(),complex_task],{"run_id":"run","task_id":"complex"})
  self.assertEqual(decision.execution.route,ExecutionRoute.CODEX)
  self.assertEqual(decision.run_id,"run")
  self.assertEqual(calls[1][1]["p_work_unit_id"],"complex-unit")
  self.assertEqual(calls[1][1]["p_route"],"codex")

 def test_concurrent_race_returns_no_claim_without_double_write(self):
  got,calls=self.make_dispatch(("direct",),[candidate()],None)
  self.assertIsNone(got)
  self.assertEqual(len(calls),2)

 def test_inconsistent_return_blocks_all_downstream_work(self):
  with self.assertRaisesRegex(RuntimeError,"inconsistent task"):
   self.make_dispatch(("direct",),[candidate()],{"run_id":"r","task_id":"different"})

 def test_malformed_preview_is_fail_closed(self):
  with self.assertRaisesRegex(RuntimeError,"must be an array"):
   self.make_dispatch(("direct",),{"work_unit_id":"u"},None)

 def test_global_dispatch_preserves_portfolio_order(self):
  portfolio=MagicMock()
  selected=SimpleNamespace(project_key="demo",soft_preemption_active=False)
  portfolio.candidates.return_value=(selected,)
  dispatcher=SupabaseBacklogDispatch(
    url="https://example.supabase.co",service_role_key="secret",portfolio=portfolio)
  with patch.object(dispatcher,"dispatch_next",return_value=MagicMock()) as call:
   result=dispatcher.dispatch_next_any(allowed_routes=("codex",))
  self.assertIsNotNone(result)
  call.assert_called_once_with("demo",allowed_routes=("codex",))
  portfolio.record.assert_called_once_with(
    selected,(selected,),outcome="dispatched")

 def test_no_portfolio_candidates_does_not_read_work_queue(self):
  portfolio=MagicMock();portfolio.candidates.return_value=()
  dispatcher=SupabaseBacklogDispatch(
    url="https://example.supabase.co",service_role_key="secret",portfolio=portfolio)
  with patch.object(dispatcher,"dispatch_next") as call:
   result=dispatcher.dispatch_next_any(allowed_routes=("direct",))
  self.assertIsNone(result)
  call.assert_not_called()
  portfolio.record.assert_called_once_with(None,(),outcome="empty_or_raced")


if __name__=="__main__":
 unittest.main()
