"""Greenfield human decision resumes an actionable, source-bound first-code plan.

Offline only: never contacts a real model, API, Supabase, or releases.
"""
import copy
import json
import unittest

from ai_product_factory.model_executor import ModelExecutor, ModelResult, ModelRole
from ai_product_factory.product_stage_executor import ProductStageExecutor
from ai_product_factory.runtime_worker import WorkItem
from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue

PROJECT_ID="19f0f200-3777-46c6-969a-acf0d3426ff1"
GATE_ID="5d506e38-713c-4825-9513-730603853482"


def fixture():
    refs=[{"kind":"url","value":"https://github.com/example/repo/issues/14"}]
    manifest={
        "source":"factory-console","onboarding_mode":"greenfield",
        "references":refs,
        "human_decisions":[{"gate_id":GATE_ID,"response":"Build a full editor from my approved input."}],
    }
    intake={
        "summary":"Studio for multi-channel video scripts and scene prompts.",
        "users":"Editors and reviewers.",
        "must_have":"SRT timeline, IV image/video pairs, clean exports, consistency QA.",
        "references":refs,
    }
    return manifest,intake


def queue_with_sources(manifest,intake):
    q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="example")
    seen=[]
    def read(path):
        seen.append(path)
        if path.startswith("factory_projects?select=id,project_kind,manifest&"):
            return [{"id":PROJECT_ID,"project_kind":"greenfield","manifest":manifest}]
        if path.startswith("factory_product_specs?select=project_id,version,status,spec&"):
            return [{"project_id":PROJECT_ID,"version":1,"status":"draft","spec":intake}]
        raise AssertionError("Unexpected source read: "+path)
    q._get=read
    q._rpc=lambda *_: (_ for _ in ()).throw(AssertionError("no mutation allowed"))
    return q,seen


class FakePrimary:
    def __init__(self):
        self.requests=[]
    def execute(self,request):
        self.requests.append(request)
        return ModelResult(
            ModelRole.PRIMARY,
            json.dumps({
                "tasks":[{
                    "task_key":"first-application-foundation",
                    "title":"Build first application foundation",
                    "required_capabilities":["implementation"],
                    "scope_keys":["application-foundation"],
                    "depends_on":[],
                    "acceptance_criteria":["Real code exists with offline checks"],
                }],
                "decisions_needed":[],
            }),
            provider_ref="offline-fixture",
            usage={"input_tokens":7},
        )


class GreenfieldApprovedPlanningContextTests(unittest.TestCase):
    def test_original_approved_intake_is_hydrated_without_any_side_effects(self):
        manifest,intake=fixture()
        q,reads=queue_with_sources(manifest,intake)
        enriched=q._approved_greenfield_planning_context(
            PROJECT_ID,{"manifest":manifest,"task":"Replan after decision"})
        self.assertEqual(enriched["intake_spec"],intake)
        self.assertEqual(enriched["manifest"]["human_decisions"],manifest["human_decisions"])
        self.assertEqual(len(reads),2)
        self.assertIn("project_id=eq."+PROJECT_ID,reads[1])
        self.assertIn("version=eq.1",reads[1])
        self.assertNotIn("model",str(reads).lower())

    def test_actionable_new_product_is_not_treated_as_existing_code_defect(self):
        manifest,intake=fixture()
        q,_=queue_with_sources(manifest,intake)
        context=q._approved_greenfield_planning_context(PROJECT_ID,{"manifest":manifest})
        fake=FakePrimary()
        handler=ProductStageExecutor(ModelExecutor(primary=fake))
        item=WorkItem("run","task",PROJECT_ID,"dark-channel-studio",("planning",),context)
        result=handler.execute(item,"planning")
        self.assertEqual(result["tasks"][0]["task_key"],"first-application-foundation")
        self.assertEqual(len(fake.requests),1)
        req=fake.requests[0]
        self.assertIn("GREENFIELD IMPLEMENTATION INSTRUCTION",req.objective)
        self.assertIn("Never require a pre-existing source-code",req.objective)
        payload=json.loads(req.context)
        self.assertEqual(payload["intake"]["intake_spec"],intake)
        self.assertEqual(payload["intake"]["manifest"]["human_decisions"],manifest["human_decisions"])

    def test_existing_or_unapproved_project_never_inherits_greenfield_authority(self):
        manifest,intake=fixture()
        for broken in (
            {"source":"imported"},
            {"onboarding_mode":"existing"},
            {"human_decisions":[]},
        ):
            unapproved={**manifest,**broken}
            q,reads=queue_with_sources(manifest,intake)
            answer=q._approved_greenfield_planning_context(PROJECT_ID,{"manifest":unapproved})
            self.assertNotIn("intake_spec",answer)
            self.assertEqual(reads,[])
        fake=FakePrimary()
        handler=ProductStageExecutor(ModelExecutor(primary=fake))
        handler.execute(WorkItem("r","t","p","old-crm",("planning",),{"manifest":{}}),"planning")
        self.assertNotIn("GREENFIELD IMPLEMENTATION INSTRUCTION",fake.requests[0].objective)

    def test_fails_closed_when_intake_or_project_was_modified(self):
        manifest,intake=fixture()
        for failure in ("wrong_project","wrong_kind","drifted_manifest","wrong_version",
                        "missing_spec","not_draft","wrong_refs","missing_summary",
                        "conflicting_original","invalid_decision","invalid_gate"):
            q,_=queue_with_sources(manifest,intake)
            context={"manifest":copy.deepcopy(manifest)}
            prior=q._get
            def faulty_read(path):
                rows=copy.deepcopy(prior(path))
                if failure=="wrong_project" and path.startswith("factory_projects?"):
                    rows[0]["id"]="wrong"
                if failure=="wrong_kind" and path.startswith("factory_projects?"):
                    rows[0]["project_kind"]="existing"
                if failure=="drifted_manifest" and path.startswith("factory_projects?"):
                    rows[0]["manifest"]["human_decisions"]=[]
                if path.startswith("factory_product_specs?"):
                    if failure=="wrong_version":rows[0]["version"]=2
                    elif failure=="missing_spec":rows.clear()
                    elif failure=="not_draft":rows[0]["status"]="candidate"
                    elif failure=="wrong_refs":rows[0]["spec"]["references"]=[]
                    elif failure=="missing_summary":rows[0]["spec"]["summary"]=""
                return rows
            q._get=faulty_read
            if failure=="conflicting_original":context["intake_spec"]={"summary":"other"}
            if failure=="invalid_decision":context["manifest"]["human_decisions"][0]["response"]=""
            if failure=="invalid_gate":context["manifest"]["human_decisions"][0]["gate_id"]="forged"
            with self.subTest(failure=failure),self.assertRaises(PermissionError):
                q._approved_greenfield_planning_context(PROJECT_ID,context)


if __name__ == "__main__":
    unittest.main()
