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
        self.assertTrue(any("canonical vocabulary" in constraint for constraint in p.requests[0].constraints))
        self.assertTrue(any("Human approval/release is a gate" in constraint for constraint in p.requests[0].constraints))

    def test_planning_rejects_product_task_without_pre_pr_builder_lane(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "tasks":[{
                    "task_key":"reconcile_repo_directives",
                    "title":"Reconcile repository directives",
                    "required_capabilities":["planning","dependency_graph"],
                    "scope_keys":["src"],
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

    def test_planning_rejects_builder_task_without_write_scope(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "tasks":[{
                    "task_key":"unsafe",
                    "title":"Unsafe task",
                    "required_capabilities":["implementation"],
                    "scope_keys":[],
                    "depends_on":[],
                    "preferred_agent_role":"development"
                }]
            }),provider_ref="ref-plan",usage={"input_tokens":10})
        p.execute=execute
        dev=AgentProfile("development","development",("implementation",),("github_write","model_primary"),{"preferred":"primary"},1,1.0,True)
        h=ProductStageExecutor(ModelExecutor(primary=p),team_profiles=(dev,))
        with self.assertRaisesRegex(ValueError,"requires non-empty scope_keys"):
            h.execute(item(),"planning")

    def test_planning_preserves_safe_context_paths(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "tasks":[{
                    "task_key":"debug",
                    "title":"Debug remediation",
                    "required_capabilities":["implementation"],
                    "scope_keys":["src/app/debug"],
                    "context_paths":["AGENTS.md","docs/codex/CURRENT_TASK.md","src/app/debug/page.tsx"],
                    "depends_on":[],
                    "preferred_agent_role":"development"
                }]
            }),provider_ref="ref-plan",usage={"input_tokens":10})
        p.execute=execute
        dev=AgentProfile("development","development",("implementation",),("github_write","model_primary"),{"preferred":"primary"},1,1.0,True)
        h=ProductStageExecutor(ModelExecutor(primary=p),team_profiles=(dev,))
        out=h.execute(item(),"planning")
        self.assertEqual(
            out["_team_plan"]["task_assignments"][0]["context_paths"],
            ["AGENTS.md","docs/codex/CURRENT_TASK.md","src/app/debug/page.tsx"],
        )

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


    def test_planning_rejects_unknown_task_dependency(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "tasks":[{
                    "task_key":"redact_debug",
                    "title":"Redact debug output",
                    "required_capabilities":["implementation"],
                    "scope_keys":["src/app/debug"],
                    "depends_on":["gate_explicit_write_authorization"],
                    "preferred_agent_role":"development"
                }],
                "decisions_needed":[]
            }),provider_ref="ref-plan",usage={"input_tokens":10})
        p.execute=execute
        dev=AgentProfile("development","development",("implementation",),("github_write","model_primary"),{"preferred":"primary"},1,1.0,True)
        h=ProductStageExecutor(ModelExecutor(primary=p),team_profiles=(dev,))
        with self.assertRaisesRegex(ValueError,"unresolved dependency: redact_debug -> gate_explicit_write_authorization"):
            h.execute(item(),"planning")

    def test_planning_with_human_decision_defers_provisional_unknown_dependencies(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "tasks":[{
                    "task_key":"redact_debug",
                    "title":"Redact debug output",
                    "required_capabilities":["implementation"],
                    "scope_keys":["src/app/debug"],
                    "depends_on":["gate_debug_contract"],
                    "preferred_agent_role":"development"
                }],
                "decisions_needed":[{
                    "decision_key":"approve_debug_contract",
                    "decision_kind":"product_requirement",
                    "question":"Which diagnostic metadata may remain visible?",
                    "why_needed":"The allowed diagnostic contract is a product decision.",
                     "suggested_response":"Manter apenas metadados diagnósticos mínimos e sem dados brutos."
                }]
            }),provider_ref="ref-plan",usage={"input_tokens":10})
        p.execute=execute
        dev=AgentProfile("development","development",("implementation",),("github_write","model_primary"),{"preferred":"primary"},1,1.0,True)
        h=ProductStageExecutor(ModelExecutor(primary=p),team_profiles=(dev,))
        out=h.execute(item(),"planning")
        self.assertEqual(out["decisions_needed"][0]["decision_key"],"approve_debug_contract")
        self.assertEqual(out["tasks"][0]["depends_on"],["gate_debug_contract"])

    def test_planning_drops_business_priority_without_two_current_active_tasks(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "architecture":{},"workstreams":[],"tasks":[],"specialist_reviews":[],
                "dependencies":[],"test_strategy":{},"release_strategy":{},"risks":[],
                "decisions_needed":[
                    {"decision_key":"stale_priority","decision_kind":"business_priority",
                     "question":"Which first?","why_needed":"priority",
                     "candidate_work_keys":["closed-issue-10","debug-remediation"]},
                    {"decision_key":"debug_contract","decision_kind":"product_requirement",
                     "question":"What metadata?","why_needed":"contract","suggested_response":"Keep only minimal diagnostic metadata."}
                ]
            }),provider_ref="ref-priority",usage={"input_tokens":1})
        p.execute=execute
        h=ProductStageExecutor(ModelExecutor(primary=p))
        w=WorkItem("r","t","p","crm-infodive",("planning",),{
            "current_state_facts":{"recent_tasks":[
                {"external_key":"closed-issue-10","status":"completed"},
                {"external_key":"debug-remediation","status":"queued"}
            ]}
        })
        out=h.execute(w,"planning")
        self.assertEqual([d["decision_key"] for d in out["decisions_needed"]],["debug_contract"])

    def test_reconciliation_prompt_does_not_promote_historical_known_pending(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "observed_stage":"planning","summary":"stale pending ignored",
                "evidence":[],"gaps":[],"constraints":{},"source_status":{}
            }),provider_ref="ref-stale",usage={"input_tokens":1})
        p.execute=execute
        h=ProductStageExecutor(ModelExecutor(primary=p))
        w=WorkItem("r","t","p","crm-infodive",("reconciliation",),{
            "state_snapshot":{"summary":"old","evidence":[{"source":"old"}]},
            "intake_spec":{"known_pending":"GitHub issue #10"},
            "current_state_facts":{"recent_tasks":[{"external_key":"present-in-usd","status":"completed"}]}
        })
        h.execute(w,"reconciliation")
        request=p.requests[0]
        self.assertIn("known_pending",request.objective)
        self.assertIn("never call them active work",request.objective)
        self.assertTrue(any("known_pending" in constraint and "historical/unverified" in constraint for constraint in request.constraints))

    def test_reconciliation_prompt_prefers_current_state_facts(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "observed_stage":"planning",
                "summary":"current facts win",
                "evidence":[{"source":"current_state_facts","observation":"write ready"}],
                "gaps":[],
                "constraints":{},
                "source_status":{}
            }),provider_ref="ref-reconcile",usage={"input_tokens":10})
        p.execute=execute
        h=ProductStageExecutor(ModelExecutor(primary=p))
        w=WorkItem("r","t","p","crm-infodive",("reconciliation",),{
            "state_snapshot":{"summary":"old","evidence":[{"source":"old"}]},
            "current_state_facts":{"github_access":{"status":"ready","observed_capabilities":{"contents_write":"verified"}}}
        })
        h.execute(w,"reconciliation")
        request=p.requests[0]
        self.assertIn("current_state_facts",request.context)
        self.assertIn("newer operational evidence",request.objective)
        self.assertTrue(any("newer operational evidence" in constraint for constraint in request.constraints))

    def test_planning_rejects_noncanonical_human_decision_kind(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "tasks":[],
                "decisions_needed":[{
                    "decision_key":"confirm_github_app_write_path",
                    "decision_kind":"technical_readiness",
                    "question":"Is GitHub write ready?",
                    "why_needed":"Need to confirm capability."
                }]
            }),provider_ref="ref-plan",usage={"input_tokens":10})
        p.execute=execute
        dev=AgentProfile("development","development",("implementation",),("github_write","model_primary"),{"preferred":"primary"},1,1.0,True)
        h=ProductStageExecutor(ModelExecutor(primary=p),team_profiles=(dev,))
        with self.assertRaisesRegex(ValueError,"unsupported planning decision_kind: technical_readiness"):
            h.execute(item(),"planning")

    def test_planning_rejects_missing_decision_kind(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "tasks":[],
                "decisions_needed":[{
                    "decision_key":"approve_debug_contract",
                    "question":"Which metadata may remain visible?",
                    "why_needed":"Product contract is unresolved."
                }]
            }),provider_ref="ref-plan",usage={"input_tokens":10})
        p.execute=execute
        dev=AgentProfile("development","development",("implementation",),("github_write","model_primary"),{"preferred":"primary"},1,1.0,True)
        h=ProductStageExecutor(ModelExecutor(primary=p),team_profiles=(dev,))
        with self.assertRaisesRegex(ValueError,"unsupported planning decision_kind: <empty>"):
            h.execute(item(),"planning")

    def test_planning_accepts_scope_authorization_decision(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "tasks":[],
                "decisions_needed":[{
                    "decision_key":"authorize_debug_write_scope",
                    "decision_kind":"scope_authorization",
                    "question":"May the current task authorize writes to /debug?",
                    "why_needed":"The repository task scope must be expanded before implementation.",
                     "suggested_response":"Autorizar somente as alterações necessárias à correção e aos testes."
                }]
            }),provider_ref="ref-plan",usage={"input_tokens":10})
        p.execute=execute
        dev=AgentProfile("development","development",("implementation",),("github_write","model_primary"),{"preferred":"primary"},1,1.0,True)
        h=ProductStageExecutor(ModelExecutor(primary=p),team_profiles=(dev,))
        out=h.execute(item(),"planning")
        self.assertEqual(out["decisions_needed"][0]["decision_kind"],"scope_authorization")
        self.assertIn("Brazilian Portuguese (pt-BR)",p.requests[0].objective)
        self.assertIn("suggested_response",p.requests[0].objective)

    def test_planning_accepts_dependency_on_existing_task_key(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            return ModelResult(ModelRole.PRIMARY,json.dumps({
                "tasks":[
                    {
                        "task_key":"prepare_debug_contract",
                        "title":"Prepare implementation scaffold",
                        "required_capabilities":["implementation"],
                        "scope_keys":["src/app/debug"],
                        "depends_on":[],
                        "preferred_agent_role":"development"
                    },
                    {
                        "task_key":"redact_debug",
                        "title":"Redact debug output",
                        "required_capabilities":["implementation"],
                        "scope_keys":["src/app/debug"],
                        "depends_on":["prepare_debug_contract"],
                        "preferred_agent_role":"development"
                    }
                ]
            }),provider_ref="ref-plan",usage={"input_tokens":10})
        p.execute=execute
        dev=AgentProfile("development","development",("implementation",),("github_write","model_primary"),{"preferred":"primary"},1,1.0,True)
        h=ProductStageExecutor(ModelExecutor(primary=p),team_profiles=(dev,))
        out=h.execute(item(),"planning")
        self.assertEqual(out["_team_plan"]["status"],"ready")
        self.assertEqual(len(out["_team_plan"]["waves"]),2)

    def test_planning_rejects_duplicate_task_key(self):
        p=Provider()
        def execute(request):
            p.requests.append(request)
            task={
                "task_key":"same",
                "title":"Same task",
                "required_capabilities":["implementation"],
                "scope_keys":["src"],
                "depends_on":[]
            }
            return ModelResult(ModelRole.PRIMARY,json.dumps({"tasks":[task,dict(task)]}),provider_ref="ref-plan",usage={"input_tokens":10})
        p.execute=execute
        dev=AgentProfile("development","development",("implementation",),("github_write","model_primary"),{"preferred":"primary"},1,1.0,True)
        h=ProductStageExecutor(ModelExecutor(primary=p),team_profiles=(dev,))
        with self.assertRaisesRegex(ValueError,"duplicate planning task_key: same"):
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
