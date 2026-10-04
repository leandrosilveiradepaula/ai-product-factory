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
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "tasks":[{"task_key":"ui","title":"Build UI","required_capabilities":["ui"],"scope_keys":["apps/console"],"depends_on":[]}]
            }),provider_ref="ref-plan",usage={"input_tokens":10})
        p.execute=execute
        ui=AgentProfile("ui","ui",("ui","ux"),("github_write","model_primary"),{"preferred":"primary"},2,0.75,True)
        h=ProductStageExecutor(ModelExecutor(primary=p),team_profiles=(ui,))
        out=h.execute(item(),"planning")
        self.assertEqual(out["_team_plan"]["status"],"ready")
        self.assertEqual(out["_team_plan"]["selected_agents"][0]["agent_key"],"ui")
        self.assertEqual(len(p.requests),1)


    def test_planning_context_exposes_only_active_registry_vocabulary(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "tasks":[{"task_key":"api","title":"Build API","required_capabilities":["implementation"],"scope_keys":["src"],"depends_on":[],"preferred_agent_role":"development"}]
            }),provider_ref="ref-plan",usage={"input_tokens":10})
        p.execute=execute
        active=AgentProfile("development","development",("implementation","debug"),("github_write","model_primary"),{"preferred":"primary"},2,1.5,True)
        inactive=AgentProfile("old","legacy",("implementation",),("github_write",),{"preferred":"primary"},1,0.1,False)
        h=ProductStageExecutor(ModelExecutor(primary=p),team_profiles=(active,inactive))
        h.execute(item(),"planning")
        payload=json.loads(p.requests[0].context)
        self.assertEqual(payload["execution_registry"],[{
            "agent_key":"development",
            "role":"development",
            "capabilities":["implementation","debug"],
            "allowed_tools":["github_write","model_primary"],
        }])
        self.assertIn("canonical vocabulary",p.requests[0].constraints[4])
        self.assertIn("Human approval/release is a gate",p.requests[0].constraints[5])

    def test_planning_rejects_product_task_without_pre_pr_builder_lane(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "tasks":[{
                    "task_key":"reconcile_repo_directives",
                    "title":"Reconcile repository directives",
                    "required_capabilities":["planning","dependency_graph"],
                    "scope_keys":[],
                    "depends_on":[],
                    "preferred_agent_role":"product"
                }]
            }),provider_ref="ref-plan",usage={"input_tokens":10})
        p.execute=execute
        dev=AgentProfile("development","development",("implementation","debug"),("github_write","model_primary"),{"preferred":"primary"},2,1.5,True)
        product=AgentProfile("product","product",("planning","dependency_graph"),("github_read","model_primary"),{"preferred":"primary"},1,0.5,True)
        h=ProductStageExecutor(ModelExecutor(primary=p),team_profiles=(dev,product))
        with self.assertRaisesRegex(ValueError,"pre-PR builder lane"):
            h.execute(item(),"planning")

    def test_planning_accepts_builder_tasks_and_post_candidate_specialist_reviews(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "tasks":[{
                    "task_key":"redact_debug",
                    "title":"Redact debug output",
                    "required_capabilities":["implementation"],
                    "scope_keys":["src/app/debug"],
                    "depends_on":[],
                    "preferred_agent_role":"development"
                }],
                "specialist_reviews":["security","qa","operations"]
            }),provider_ref="ref-plan",usage={"input_tokens":10})
        p.execute=execute
        dev=AgentProfile("development","development",("implementation","debug"),("github_write","model_primary"),{"preferred":"primary"},2,1.5,True)
        security=AgentProfile("security","security",("security_review",),("github_read","model_primary"),{"preferred":"primary"},1,0.5,True)
        qa=AgentProfile("qa","qa",("tests",),("github_read","github_actions"),{"preferred":"deterministic"},1,0.25,True)
        operations=AgentProfile("operations","operations",("ci",),("github_actions",),{"preferred":"deterministic"},1,0.25,True)
        h=ProductStageExecutor(ModelExecutor(primary=p),team_profiles=(dev,security,qa,operations))
        out=h.execute(item(),"planning")
        self.assertEqual(out["_team_plan"]["status"],"ready")
        roles={row["role"] for row in out["_team_plan"]["advisory_specialist_lanes"]}
        self.assertEqual(roles,{"security","qa","operations"})
        self.assertEqual(out["_team_plan"]["waves"][0]["task_keys"],["redact_debug"])

    def test_planning_accepts_structured_post_candidate_specialist_reviews(self):
        p=Provider()
        structured_review={
            "role":"security",
            "review_key":"debug_security_post_candidate_review",
            "timing":"After candidate implementation.",
            "required_evidence":["Candidate revision identifier"],
            "review_criteria":["Confirm raw business records are not exposed."]
        }
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "tasks":[{
                    "task_key":"redact_debug",
                    "title":"Redact debug output",
                    "required_capabilities":["implementation"],
                    "scope_keys":["src/app/debug"],
                    "depends_on":[],
                    "preferred_agent_role":"development"
                }],
                "specialist_reviews":[structured_review]
            }),provider_ref="ref-plan",usage={"input_tokens":10})
        p.execute=execute
        dev=AgentProfile("development","development",("implementation","debug"),("github_write","model_primary"),{"preferred":"primary"},2,1.5,True)
        security=AgentProfile("security","security",("security_review",),("github_read","model_primary"),{"preferred":"primary"},1,0.5,True)
        h=ProductStageExecutor(ModelExecutor(primary=p),team_profiles=(dev,security))
        out=h.execute(item(),"planning")
        self.assertEqual(out["specialist_reviews"],[structured_review])
        advisory=next(x for x in out["_team_plan"]["advisory_specialist_lanes"] if x["role"]=="security")
        self.assertIn("debug_security_post_candidate_review",advisory["reasons"][0])

    def test_planning_rejects_structured_specialist_review_with_unknown_role(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "tasks":[{
                    "task_key":"api",
                    "title":"Build API",
                    "required_capabilities":["implementation"],
                    "scope_keys":["src"],
                    "depends_on":[]
                }],
                "specialist_reviews":[{"role":"compliance","review_key":"unsupported"}]
            }),provider_ref="ref-plan",usage={"input_tokens":10})
        p.execute=execute
        dev=AgentProfile("development","development",("implementation",),("github_write","model_primary"),{"preferred":"primary"},1,1.0,True)
        h=ProductStageExecutor(ModelExecutor(primary=p),team_profiles=(dev,))
        with self.assertRaisesRegex(ValueError,"unsupported specialist review role: compliance"):
            h.execute(item(),"planning")

    def test_planning_defaults_missing_title_from_task_key_before_team_plan(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "tasks":[{"task_key":"BUILD_API","required_capabilities":["implementation"],"scope_keys":["src"],"depends_on":[]}]
            }),provider_ref="ref-plan",usage={"input_tokens":10})
        p.execute=execute
        dev=AgentProfile("development","development",("implementation",),("github_write","model_primary"),{"preferred":"primary"},1,1.0,True)
        h=ProductStageExecutor(ModelExecutor(primary=p),team_profiles=(dev,))
        out=h.execute(item(),"planning")
        self.assertEqual(out["tasks"][0]["title"],"BUILD_API")
        self.assertEqual(out["_team_plan"]["task_assignments"][0]["title"],"BUILD_API")

if __name__=="__main__":
    unittest.main()
