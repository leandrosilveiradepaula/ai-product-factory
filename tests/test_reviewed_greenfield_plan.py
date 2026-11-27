import hashlib
import unittest
from unittest.mock import patch

from ai_product_factory import reviewed_greenfield_plan as reviewed
from ai_product_factory.agent_scheduler import AgentProfile
from ai_product_factory.model_executor import ModelExecutor
from ai_product_factory.product_stage_executor import ProductStageExecutor
from ai_product_factory.runtime_worker import WorkItem


class NoModel:
    def execute(self, request):
        raise AssertionError("assisted plan must not call a model")


class ReadOnlySource:
    def __init__(self, files):
        self.files = files

    def get_file_text(self, path, *, ref):
        assert ref == reviewed._RECORD["source_commit"]
        return self.files[path]


class ReviewedPlanTests(unittest.TestCase):
    def context(self, record):
        text = "authorized source plan"
        record["request_digest"] = hashlib.sha256(text.encode()).hexdigest()
        return {
            "manifest": {"onboarding_mode": "greenfield", "source": "factory-console"},
            "journey_binding_v2": {**{k: record[k] for k in
                ("project_id","journey_id","request_id","repository","source_commit")},
                "execution_generation": record["generation"], "source_mode": "main_snapshot"},
            "journey_request": {"text": text, "digest":record["request_digest"],
                "source":"github-owner","authorization_event_id":"7162981651",
                "control_issue_number":1055,"control_issue_repository":"leandrosilveiradepaula/ai-product-factory"},
            "_verified_resume_origin":{"source_run_id":record["source_run_id"],
                "snapshot_id":record["source_commit"],"request_id":record["request_id"],
                "generation":record["generation"],"prior_kind":"greenfield"},
            "_verified_resume_prior_stages":{
                "discovery":{"problem":"Incomplete","_evidence":{"provider_ref":"actual-discovery"}},
                "specification":{"scope":"Studio","_evidence":{"provider_ref":"actual-spec"}}},
            "current_state_facts":{"live_candidate":{
                "observed_from":"journey_delivery_binding_v2","repository":record["repository"],
                "journey_id":record["journey_id"],"sha":record["source_commit"],
                "source_evidence":{"assessed_commit":record["source_commit"],
                    "status":"bounded_source_inspected","inspected_files":[{"path":"app/server.js"}]}}}
        }

    def test_assisted_plan_real_executor_and_exact_source(self):
        from copy import deepcopy
        record = deepcopy(reviewed._RECORD)
        ctx = self.context(record)
        source_files={p: "reviewed bytes for "+p for p in record["source_blobs"]}
        record["source_blobs"]={p:hashlib.sha1(b"blob "+str(len(v.encode())).encode()+b"\0"+v.encode(),usedforsecurity=False).hexdigest()
                                for p,v in source_files.items()}
        with patch.object(reviewed,"_RECORD",record):
            args=(record["run_id"],record["task_id"],record["project_id"],record["generation"],ctx)
            with self.assertRaises(PermissionError):
                reviewed.admit_reviewed_plan(*args,{})
            admitted=reviewed.admit_reviewed_plan(*args,{"reviewed_plan_recovery":record["plan_id"]})
            with self.assertRaises(PermissionError):
                reviewed.verify_reviewed_plan_source(admitted,ReadOnlySource({**source_files,"app/server.js":"changed"}))
            verified=reviewed.verify_reviewed_plan_source(admitted,ReadOnlySource(source_files))
            item=WorkItem(record["run_id"],record["task_id"],record["project_id"],record["project_key"],("planning",),
                          verified,execution_generation=record["generation"],worker_id="worker",journey_id=record["journey_id"])
            dev=AgentProfile("dev","development",("implementation","migration_authoring"),
                             ("github_write","github_read"),{},1,0.5,True)
            result=ProductStageExecutor(ModelExecutor(primary=NoModel()),team_profiles=(dev,)).execute(item,"planning")
            self.assertEqual(len(result["tasks"]),4)
            self.assertEqual(result["_team_plan"]["status"],"ready")
            self.assertFalse(result["_evidence"]["model_invoked"])
            self.assertFalse(result["_evidence"]["autonomous_model_planning"])
            self.assertNotIn("provider_ref",result["_evidence"])
            self.assertIsNone(reviewed.reviewed_plan_output(WorkItem("other","task","project","other",("planning",),{}),"planning"))
            with self.assertRaises(PermissionError):
                reviewed.reviewed_plan_output(WorkItem("other","task","project","other",("planning",),verified),"planning")
            with self.assertRaises(PermissionError):
                reviewed.admit_reviewed_plan(record["run_id"],record["task_id"],record["project_id"],2,ctx,{"reviewed_plan_recovery":record["plan_id"]})

    def test_claim_and_normal_stage_materialization(self):
        # Run the actual claim/source admission, executor and persistence code
        # together using isolated transport and RPC boundaries. No model call.
        from copy import deepcopy
        from test_v2_merged_source_preflight import fixture, MergeSourceTransport
        from ai_product_factory.github_rest import GitHubRestAdapter
        from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue
        from ai_product_factory.runtime_worker import RuntimeWorker, WorkStatus

        for native in (False, True):
            with self.subTest(native=native):
                record = deepcopy(reviewed._RECORD)
                binding,snapshot,source,resume,journey,manifest = fixture()
                # The ordinary merge-source regression uses a different run.
                # For this recovery, bind the exact incident and owner request.
                rid = record["run_id"]
                resume["id"] = rid
                snapshot.update(text="Authorized reviewed plan",source="github-owner",
                    authorization_event_id="7162981651",control_issue_number=1055,
                    control_issue_repository="leandrosilveiradepaula/ai-product-factory")
                snapshot["digest"] = hashlib.sha256(snapshot["text"].encode()).hexdigest()
                record["request_digest"] = snapshot["digest"]
                journey["request_digest"] = snapshot["digest"]
                resume["metadata"]["reviewed_plan_recovery"] = record["plan_id"]
                transport = MergeSourceTransport()
                for path in record["source_blobs"]:
                    transport.files.setdefault(path,"Reviewed source "+path)
                record["source_blobs"] = {path:hashlib.sha1(
                    b"blob "+str(len(transport.files[path].encode())).encode()+b"\0"+
                    transport.files[path].encode(),usedforsecurity=False).hexdigest()
                    for path in record["source_blobs"]}
                project = {"id":record["project_id"],"project_key":record["project_key"],
                    "repository":record["repository"]}
                queue = SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="synthetic")
                rpc_calls = []
                def rpc(name,payload):
                    rpc_calls.append((name,payload))
                    if name=="factory_claim_next_run":
                        return {"run_id":rid,"task_id":record["task_id"],"project_id":record["project_id"],
                            "project_key":record["project_key"],"execution_generation":1,
                            "stages":["planning"],"context":{"manifest":manifest}}
                    if name=="factory_record_execution_team_plan":
                        return {"id":"team","status":"ready"}
                    if name=="factory_materialize_change_set":
                        return {"change_set_id":"change","status":"planned"}
                    if name in {"factory_record_runtime_stage","factory_persist_product_stage",
                        "factory_record_requirement_trace","factory_record_project_brain_snapshot",
                        "factory_record_definition_of_done","factory_finish_run"}:
                        return {}
                    raise AssertionError("unexpected RPC "+name)
                def get(path):
                    if path.startswith("factory_runs?select=journey_id&id=eq."):
                        return [{"journey_id":record["journey_id"]}]
                    if path.startswith("factory_projects?"):
                        return [project]
                    if path.startswith("factory_journeys?"):
                        return [journey]
                    if path.startswith("factory_runs?select=id,task_id,journey_id,status,metadata&id=eq."):
                        return [resume]
                    if path.startswith("factory_runs?select=id,task_id,journey_id,status,execution_route,source_commit,metadata&id=eq."):
                        return [source]
                    if path.startswith(("factory_project_state_snapshots?","factory_tasks?","factory_project_github_access?")):
                        return []
                    if path.startswith("factory_runs?select=id,task_id,status,metadata&task_id=eq."):
                        return [source]
                    raise AssertionError(path)
                queue._get=get
                queue._rpc=rpc
                queue.assert_execution_epoch=lambda item: None
                github=GitHubRestAdapter(repository=record["repository"],token="synthetic",transport=transport)
                dev=AgentProfile("development","development",("implementation","migration_authoring"),
                                 ("github_write","github_read"),{},1,0.5,True)
                handler=ProductStageExecutor(ModelExecutor(primary=NoModel()),team_profiles=(dev,))
                env=({"FACTORY_PRIMARY_MODEL_PROVIDER":"infodive_ibm_cloud","FACTORY_INFODIVE_VPS_WORKER_ENABLED":"true"}
                     if native else {"GITHUB_ACTIONS":"true"})
                with patch.object(reviewed,"_RECORD",record),patch.dict("os.environ",env,clear=True), \
                     patch("ai_product_factory.supabase_runtime_queue.GitHubRestAdapter",return_value=github), \
                     patch.object(queue,"_github_for_project",return_value=github):
                    outcome=RuntimeWorker(queue=queue,handler=handler,worker_id="worker").run_once()
                self.assertEqual(outcome.status,WorkStatus.COMPLETED,outcome.error)
                calls=[name for name,_ in rpc_calls]
                self.assertEqual(calls.count("factory_materialize_change_set"),1)
                self.assertEqual(calls.count("factory_record_execution_team_plan"),1)
                self.assertEqual(calls.count("factory_record_requirement_trace"),1)
                persisted=next(p["p_output"] for n,p in rpc_calls if n=="factory_persist_product_stage")
                self.assertEqual(len(persisted["tasks"]),4)
                self.assertFalse(persisted["_evidence"]["autonomous_model_planning"])
                self.assertNotIn("provider_ref",persisted["_evidence"])
                self.assertEqual(rpc_calls[-1][1]["p_status"],"completed")
                self.assertTrue(all(method=="GET" for method,_ in transport.calls))
