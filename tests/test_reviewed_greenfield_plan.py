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
