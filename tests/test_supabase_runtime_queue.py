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
    def test_execution_epoch_requires_positive_generation(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{})
        with patch("urllib.request.urlopen") as call:
            with self.assertRaisesRegex(RuntimeError,"generation"):
                q.assert_execution_epoch(item)
            call.assert_not_called()

    def test_execution_epoch_rejects_bool_zero_negative_and_string(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        with patch("urllib.request.urlopen") as network:
            for generation in (True, False, 0, -1, "3", 3.0):
                with self.subTest(generation=generation):
                    item=WorkItem("r","t","p","demo",(),{},generation)
                    with self.assertRaisesRegex(RuntimeError,"generation"):
                        q.assert_execution_epoch(item)
            network.assert_not_called()

    def test_stale_epoch_backend_rejection_blocks_stage_and_terminal_writes(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{},2)
        calls=[]
        def rpc(name,payload):
            calls.append(name)
            if name=="factory_assert_project_execution_epoch":
                raise RuntimeError("project execution epoch revoked")
            raise AssertionError("side effect admitted: "+name)
        q._rpc=rpc
        for operation in (
            lambda: q.record_stage_event(item,"planning","started"),
            lambda: q.record_stage(item,StageEvidence("planning","completed",{})),
            lambda: q.complete(item),
            lambda: q.fail(item,"failure"),
        ):
            with self.assertRaisesRegex(RuntimeError,"revoked"):
                operation()
        self.assertEqual(calls,["factory_assert_project_execution_epoch"]*4)

    def test_claimed_run_without_epoch_cannot_write_stage_or_finish(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        with patch("urllib.request.urlopen",return_value=Response({
            "run_id":"r","task_id":"t","project_id":"p","project_key":"demo",
            "stages":["discovery"],"context":{}
        })):
            with self.assertRaisesRegex(RuntimeError,"generation"):
                q.claim_next("worker")

    def test_noncompleted_stage_evidence_never_persists_product_data(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{},2)
        with patch("urllib.request.urlopen") as network:
            for status in ("started","failed","pending"):
                with self.subTest(status=status):
                    with self.assertRaises(ValueError):
                        q.record_stage(item,StageEvidence("planning",status,{}))
            network.assert_not_called()

    def test_execution_epoch_calls_privileged_rpc(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{},3)
        with patch("urllib.request.urlopen",return_value=Response(None)) as call:
            q.assert_execution_epoch(item)
        req=call.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/rpc/factory_assert_project_execution_epoch"))
        self.assertEqual(json.loads(req.data),{"p_project_id":"p","p_generation":3})
        self.assertNotIn(b"secret",req.data)

    def test_claim_maps_rpc_payload_without_leaking_key(self):
        payload={"run_id":"r","task_id":"t","project_id":"p","project_key":"demo","stages":["discovery"],"context":{"x":1},"execution_generation":1}
        with patch("urllib.request.urlopen",return_value=Response(payload)) as call:
            q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
            item=q.claim_next("w")
        self.assertEqual(item.project_key,"demo")
        self.assertEqual(item.stages,("discovery",))
        req=call.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/rest/v1/rpc/factory_claim_next_run"))
        self.assertNotIn(b"secret",req.data)

    def test_claim_rejects_missing_or_invalid_generation(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        base={"run_id":"r","task_id":"t","project_id":"p","project_key":"demo",
              "stages":["discovery"],"context":{}}
        for generation in (None,0,-1,True,"2"):
            with self.subTest(generation=generation):
                q._rpc=lambda name,args: {**base,"execution_generation":generation}
                with self.assertRaisesRegex(RuntimeError,"generation"):
                    q.claim_next("worker")

    def test_claim_rejects_malformed_rpc_payloads(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        for payload in ([], "unexpected", {"stages":"planning"},
                        {"stages":[None]}, {"stages":[""]},
                        {"stages":[],"context":[]}, {"stages":{}},
                        {"stages":[42]}):
            with self.subTest(payload=payload):
                q._rpc=lambda name,args: payload
                with self.assertRaises((RuntimeError,KeyError,TypeError)):
                    q.claim_next("worker")

    def test_claim_carries_generation_from_database(self):
        payload={"run_id":"r","task_id":"t","project_id":"p","project_key":"demo",
                 "stages":["discovery"],"context":{},"execution_generation":7}
        with patch("urllib.request.urlopen",return_value=Response(payload)):
            q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
            item=q.claim_next("worker")
        self.assertEqual(item.execution_generation,7)

    def test_terminal_and_stage_rpcs(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{},3)
        with patch("urllib.request.urlopen",return_value=Response(None)) as call:
            q.record_stage(item,StageEvidence("discovery","completed",{"ok":True}))
            q.complete(item);q.fail(item,"x")
        self.assertEqual(call.call_count,7)

    def test_terminal_failure_without_generation_never_writes(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{})
        with patch("urllib.request.urlopen") as call:
            with self.assertRaisesRegex(RuntimeError,"generation"):
                q.fail(item,"error")
            call.assert_not_called()

    def test_reconciliation_and_gap_analysis_use_product_stage_persistence(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","crm-infodive",(),{},3)
        with patch("urllib.request.urlopen",return_value=Response(None)) as call:
            q.record_stage(item,StageEvidence("reconciliation","completed",{"summary":"ok"}))
            q.record_stage(item,StageEvidence("gap_analysis","completed",{"gaps":[]}))
        urls=[x.args[0].full_url for x in call.call_args_list]
        self.assertEqual(sum(url.endswith("/rest/v1/rpc/factory_record_runtime_stage") for url in urls),2)
        self.assertEqual(sum(url.endswith("/rest/v1/rpc/factory_persist_product_stage") for url in urls),2)

    def test_stage_lifecycle_event_uses_existing_runtime_stage_rpc(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{},3)
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
        item=WorkItem("r","t","p","demo",(),{},3)
        with self.assertRaises(ValueError):
            q.record_stage_event(item,"planning","mystery")


    def test_invalid_stage_event_never_contacts_backend(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{},3)
        with patch("urllib.request.urlopen") as call:
            with self.assertRaises(ValueError):
                q.record_stage_event(item,"planning","invalid")
            call.assert_not_called()

    def test_missing_generation_blocks_stage_write(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{})
        with patch("urllib.request.urlopen") as call:
            with self.assertRaisesRegex(RuntimeError,"generation"):
                q.record_stage(item,StageEvidence("planning","completed",{}))
            call.assert_not_called()

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

    def test_decision_resume_recovery_uses_dedicated_rpc(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        with patch("urllib.request.urlopen",return_value=Response({"created":1,"existing":0,"blocked":0})) as call:
            out=q.resume_resolved_decisions()
        self.assertEqual(out,{"created":1,"existing":0,"blocked":0})
        req=call.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/rest/v1/rpc/factory_resume_resolved_decisions"))
        self.assertEqual(json.loads(req.data.decode()),{})
        self.assertNotIn(b"secret",req.data)


    def test_terminal_descendant_reconciliation_uses_dedicated_rpc(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        payload={"completed_children":2,"cancelled_children":3,"superseded_change_sets":1}
        with patch("urllib.request.urlopen",return_value=Response(payload)) as call:
            out=q.reconcile_terminal_descendants()
        self.assertEqual(out,payload)
        req=call.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/rest/v1/rpc/factory_reconcile_terminal_task_descendants"))
        self.assertEqual(json.loads(req.data.decode()),{})
        self.assertNotIn(b"secret",req.data)


    def test_planning_stage_persists_execution_team_plan(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{},3)
        output={"tasks":[],"_team_plan":{"version":1,"status":"ready","profiles_selected":0,"planned_worker_peak":0,"blockers":[]}}
        with patch("urllib.request.urlopen",return_value=Response(None)) as call:
            q.record_stage(item,StageEvidence("planning","completed",output))
        urls=[x.args[0].full_url for x in call.call_args_list]
        self.assertTrue(any(url.endswith("/rest/v1/rpc/factory_record_execution_team_plan") for url in urls))
        self.assertGreaterEqual(call.call_count,3)


    def test_planning_decision_gate_skips_team_plan_and_change_set_materialization(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","crm-infodive",(),{"manifest":{}},3)
        output={
            "tasks":[{"task_key":"debug","title":"Debug","required_capabilities":["implementation"],"scope_keys":["src"],"depends_on":[]}],
            "decisions_needed":[{"decision_key":"approve_debug_contract","question":"What may remain visible?"}],
            "_team_plan":{"version":1,"status":"ready","profiles_selected":1,"planned_worker_peak":1,"blockers":[]},
        }
        calls=[]
        def rpc(name,payload):
            calls.append((name,payload))
            if name=="factory_persist_product_stage":
                return {"human_gate_id":"gate-1","created_tasks":0}
            if name=="factory_record_definition_of_done":
                return {"id":"dod-1"}
            if name in {
                "factory_assert_project_execution_epoch",
                "factory_record_runtime_stage",
                "factory_record_requirement_trace",
                "factory_record_project_brain_snapshot",
            }:
                return {}
            raise AssertionError(name)
        q._rpc=rpc
        q.record_stage(item,StageEvidence("planning","completed",output))
        names=[name for name,_ in calls]
        self.assertIn("factory_persist_product_stage",names)
        self.assertNotIn("factory_record_execution_team_plan",names)
        self.assertNotIn("factory_materialize_change_set",names)
        self.assertIn("factory_record_definition_of_done",names)


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


class CurrentStateFactsMigrationTests(unittest.TestCase):
    def test_claim_next_run_includes_current_control_plane_facts(self):
        from pathlib import Path
        sql=(Path(__file__).resolve().parents[1]/"supabase/migrations/20261004200200_factory_claim_current_state_facts.sql").read_text()
        compact=" ".join(sql.split())
        self.assertIn("'current_state_facts'",sql)
        self.assertIn("'recent_tasks'",sql)
        self.assertIn("factory_project_github_access",sql)
        self.assertIn("'observed_capabilities'",sql)
        self.assertIn("'pending_human_gates'",sql)
        self.assertIn("factory_human_gates",sql)
        self.assertIn("limit 25",sql.lower())
        self.assertNotIn("token",sql.lower())
        self.assertIn("revoke all on function public.factory_claim_next_run(text)",compact.lower())
        self.assertIn("grant execute on function public.factory_claim_next_run(text) to service_role",compact.lower())


class ProductStagePersistenceMigrationTests(unittest.TestCase):
    def test_reconciliation_runtime_migration_preserves_agent_fields(self):
        from pathlib import Path
        sql=(Path(__file__).resolve().parents[1]/"supabase/migrations/20261004145700_reconcile_product_stage_runtime.sql").read_text()
        self.assertIn("'reconciliation'",sql)
        self.assertIn("'gap_analysis'",sql)
        self.assertIn("factory_project_state_snapshots",sql)
        self.assertIn("'gap_analysis'",sql)
        self.assertIn("agent_role,required_capabilities,scope_keys",sql.replace("\n","" ).replace(" ",""))
        self.assertIn("preferred_agent_role",sql)
        self.assertIn("security invoker",sql.lower())


if __name__=="__main__":
    unittest.main()
