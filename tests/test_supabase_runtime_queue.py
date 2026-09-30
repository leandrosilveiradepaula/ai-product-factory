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

    def test_stage_lifecycle_event_uses_existing_runtime_stage_rpc(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{})
        with patch("urllib.request.urlopen",return_value=Response(None)) as call:
            q.record_stage_event(item,"planning","started")
        req=call.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/rest/v1/rpc/factory_record_runtime_stage"))
        body=json.loads(req.data.decode())
        self.assertEqual(body["p_stage"],"planning")
        self.assertEqual(body["p_status"],"started")
        self.assertEqual(body["p_output"],{})

    def test_stage_lifecycle_event_rejects_unknown_status(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{})
        with self.assertRaises(ValueError):
            q.record_stage_event(item,"planning","mystery")


    def test_retry_failed_run_uses_privileged_rpc_without_leaking_secret_in_body(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        payload={"source_run_id":"old","run_id":"new","status":"queued","task_status":"queued"}
        with patch("urllib.request.urlopen",return_value=Response(payload)) as call:
            out=q.retry_failed_run("old","operator retry after fix")
        self.assertEqual(out["run_id"],"new")
        req=call.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/rest/v1/rpc/factory_retry_failed_run"))
        body=json.loads(req.data.decode())
        self.assertEqual(body,{"p_source_run_id":"old","p_reason":"operator retry after fix"})
        self.assertNotIn(b"secret",req.data)

    def test_retry_failed_run_requires_source_and_reason_before_rpc(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        with patch("urllib.request.urlopen") as call:
            with self.assertRaises(ValueError):q.retry_failed_run("","reason")
            with self.assertRaises(ValueError):q.retry_failed_run("old"," ")
        call.assert_not_called()

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
        self.assertTrue(any(url.endswith("/rest/v1/rpc/factory_record_execution_team_plan") for url in urls))
        self.assertGreaterEqual(call.call_count,3)


    def test_rebuild_team_plan_uses_persisted_engineering_plan_and_materializes_ready_change_set(self):
        from ai_product_factory.agent_scheduler import AgentProfile
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        q._get=lambda path: (
            [{"id":"run-1","task_id":"task-1"}] if path.startswith("factory_runs?")
            else [{"id":"task-1","project_id":"project-1"}] if path.startswith("factory_tasks?")
            else [{"id":"project-1","manifest":{"engineering_plan":{"tasks":[{"task_key":"api","title":"API","required_capabilities":["implementation"],"scope_keys":["src"],"depends_on":[]}]}}}]
        )
        calls=[]
        def rpc(name,payload):
            calls.append((name,payload))
            if name=="factory_record_execution_team_plan":
                return {"id":"tp-1","status":"ready"}
            if name=="factory_materialize_change_set":
                return {"change_set_id":"cs-1","builder_work_units":1,"status":"planned"}
            raise AssertionError(name)
        q._rpc=rpc
        profile=AgentProfile("development","development",("implementation",),("github_write",),{"preferred":"primary"},1,1.0,True)
        out=q.rebuild_team_plan("run-1",(profile,))
        self.assertEqual(out["status"],"ready")
        self.assertEqual(out["change_set"]["change_set_id"],"cs-1")
        self.assertEqual([name for name,_ in calls],["factory_record_execution_team_plan","factory_materialize_change_set"])

if __name__=="__main__":
    unittest.main()
