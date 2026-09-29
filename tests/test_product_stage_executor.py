import json
import unittest

from ai_product_factory.agent_scheduler import AgentProfile
from ai_product_factory.model_executor import ModelExecutor,ModelResult,ModelRole
from ai_product_factory.product_stage_executor import ProductStageExecutor
from ai_product_factory.runtime_worker import WorkItem


class Provider:
    def __init__(self): self.requests=[]
    def execute(self,request):
        self.requests.append(request)
        return ModelResult(
            ModelRole.PRIMARY,
            json.dumps({"stage":"ok","assumptions":[]}),
            provider_ref=f"ref-{len(self.requests)}",
            usage={"input_tokens":10},
        )


def item():
    return WorkItem("r","t","p","demo",("discovery","specification","planning"),{"summary":"build x"})


def existing_item():
    return WorkItem(
        "r-existing","t-existing","p-existing","crm-infodive",
        ("reconciliation","gap_analysis","planning"),
        {
            "manifest":{"reconcile_first":True},
            "intake_spec":{"summary":"verify existing CRM"},
            "state_snapshot":{
                "summary":"repository inspected read-only",
                "evidence":[{"source":"github","head_sha":"abc"}],
                "gaps":[],
                "constraints":["read-only"],
                "source_status":{"github_repository":"available"},
            },
        },
    )


class ProductStageExecutorTests(unittest.TestCase):
    def test_product_stages_use_primary_and_chain_prior_evidence(self):
        p=Provider();h=ProductStageExecutor(ModelExecutor(primary=p));i=item()
        d=h.execute(i,"discovery");h.execute(i,"specification");h.execute(i,"planning")
        self.assertEqual(d["_evidence"]["provider_ref"],"ref-1")
        self.assertEqual(len(p.requests),3)
        self.assertIn('"discovery"',p.requests[1].context)

    def test_existing_project_reconciliation_uses_snapshot_and_chains_gap_analysis(self):
        p=Provider();h=ProductStageExecutor(ModelExecutor(primary=p));i=existing_item()
        h.execute(i,"reconciliation")
        h.execute(i,"gap_analysis")
        h.execute(i,"planning")
        self.assertEqual(len(p.requests),3)
        self.assertIn("state_snapshot",p.requests[0].context)
        self.assertIn('"reconciliation"',p.requests[1].context)
        self.assertIn('"gap_analysis"',p.requests[2].context)
        self.assertIn("Do not claim tests",p.requests[0].constraints[2])

    def test_reconciliation_fails_closed_without_durable_snapshot(self):
        p=Provider();h=ProductStageExecutor(ModelExecutor(primary=p))
        i=WorkItem("r","t","p","existing",("reconciliation",),{"manifest":{"reconcile_first":True}})
        with self.assertRaisesRegex(ValueError,"durable state snapshot"):
            h.execute(i,"reconciliation")
        self.assertEqual(p.requests,[])

    def test_invalid_json_fails_closed(self):
        class Bad:
            def execute(self,request): return ModelResult(ModelRole.PRIMARY,"not-json")
        h=ProductStageExecutor(ModelExecutor(primary=Bad()))
        with self.assertRaisesRegex(ValueError,"invalid JSON"):
            h.execute(item(),"discovery")

    def test_codex_is_not_used_for_bootstrap(self):
        primary=Provider()
        class Codex:
            def execute(self,request): raise AssertionError("Codex must not be called")
        h=ProductStageExecutor(ModelExecutor(primary=primary,codex=Codex()))
        h.execute(item(),"discovery")
        self.assertEqual(len(primary.requests),1)

    def test_planning_derives_team_plan_without_extra_model_call(self):
        p=Provider()
        p.execute=lambda request: ModelResult(ModelRole.PRIMARY,json.dumps({
            "tasks":[{"task_key":"ui","title":"Build UI","required_capabilities":["ui"],"scope_keys":["apps/console"],"depends_on":[]}]
        }),provider_ref="ref-plan",usage={"input_tokens":10})
        ui=AgentProfile("ui","ui",("ui","ux"),("github_write","model_primary"),{"preferred":"primary"},2,0.75,True)
        h=ProductStageExecutor(ModelExecutor(primary=p),team_profiles=(ui,))
        out=h.execute(item(),"planning")
        self.assertEqual(out["_team_plan"]["status"],"ready")
        self.assertEqual(out["_team_plan"]["selected_agents"][0]["agent_key"],"ui")
        self.assertEqual(len(p.requests),1)


if __name__=="__main__":
    unittest.main()
