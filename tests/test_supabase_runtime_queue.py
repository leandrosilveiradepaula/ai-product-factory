import json
import unittest
from unittest.mock import patch

from ai_product_factory.runtime_worker import StageEvidence,WorkItem
from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue


class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return json.dumps(self.data).encode() if self.data is not None else b""


class SupabaseRuntimeQueueTests(unittest.TestCase):
    def test_claim_maps_rpc_payload_without_leaking_key(self):
        payload={"run_id":"r","task_id":"t","project_id":"p","project_key":"demo","stages":["discovery"],"context":{"x":1}}
        with patch("urllib.request.urlopen",return_value=Response(payload)) as call:
            q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
            item=q.claim_next("w")
        self.assertEqual(item.project_key,"demo")
        self.assertEqual(item.stages,("discovery",))
        req=call.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/rest/v1/rpc/factory_claim_next_run"))
        self.assertNotIn(b"secret",req.data)

    def test_terminal_and_stage_rpcs(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{})
        with patch("urllib.request.urlopen",return_value=Response(None)) as call:
            q.record_stage(item,StageEvidence("discovery","completed",{"ok":True}))
            q.complete(item);q.fail(item,"x")
        self.assertEqual(call.call_count,4)

    def test_recovery_rpc_is_bounded_and_service_secret_not_in_body(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        with patch("urllib.request.urlopen",return_value=Response({"requeued":1,"failed":0})) as call:
            out=q.recover_expired(3)
        self.assertEqual(out,{"requeued":1,"failed":0})
        req=call.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/rest/v1/rpc/factory_recover_expired_runs"))
        self.assertNotIn(b"secret",req.data)

    def test_planning_stage_persists_execution_team_plan(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{})
        output={"tasks":[],"_team_plan":{"version":1,"status":"ready","profiles_selected":0,"planned_worker_peak":0,"blockers":[]}}
        with patch("urllib.request.urlopen",return_value=Response(None)) as call:
            q.record_stage(item,StageEvidence("planning","completed",output))
        urls=[x.args[0].full_url for x in call.call_args_list]
        self.assertTrue(urls[-1].endswith("/rest/v1/rpc/factory_record_execution_team_plan"))
        self.assertEqual(call.call_count,3)


if __name__=="__main__":
    unittest.main()
