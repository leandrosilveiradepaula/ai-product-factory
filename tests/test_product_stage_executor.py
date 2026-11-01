import json
import unittest

from ai_product_factory.agent_scheduler import AgentProfile
from ai_product_factory.model_executor import ModelExecutor,ModelResult,ModelRole
from ai_product_factory.product_stage_executor import ProductStageExecutor
from ai_product_factory.product_stage_output_contract import PlanningNoActionableWork
from ai_product_factory.runtime_worker import WorkItem


class Provider:
    def __init__(self): self.requests=[]
    def execute(self,request):
        self.requests.append(request)
        output=(
            {"tasks":[{"task_key":"unit-test-builder","required_capabilities":["implementation"],
                       "scope_keys":["src/unit_test_module.py"],"depends_on":[]}],
             "decisions_needed":[]}
            if request.objective.startswith("Return explicit tasks array for implementation")
            else {"stage":"ok","assumptions":[]}
        )
        return ModelResult(
            ModelRole.PRIMARY,
            json.dumps(output),
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
    def test_v2_checkpoint_accepts_structured_summary_and_rejects_empty_object(self):
        class CountingProvider:
            def __init__(self): self.calls = 0
            def execute(self, request):
                self.calls += 1
                return ModelResult(ModelRole.PRIMARY, json.dumps({
                    "tasks": [{"task_key": "crm171-fix", "required_capabilities": ["implementation"],
                               "scope_keys": ["src/contracts.py"], "depends_on": []}],
                    "decisions_needed": []
                }))
        for summary, accepted in (
            ({"objective": "Fix CRM #171", "repository": {"name": "crm-infodive"}}, True),
            ({"active_work": {"objective": "Corrigir contratos CRM #209", "status": "running"}}, True),
            ({"active_work": {"objective": " Corrigir contratos "}, "objective": " "}, True),
            ({"active_work": {"objective": ""}}, False),
            ({"active_work": {"objective": "  "}}, False),
            ({"active_work": {"objective": ["CRM #209"]}}, False),
            ({"active_work": {"status": "running"}}, False),
            ({"active_work": "CRM #209"}, False),
            ({}, False),
            ({"repository": {"name": "crm-infodive"}}, False),
            ({"objective": "  "}, False),
        ):
            with self.subTest(summary=summary):
                provider = CountingProvider()
                handler = ProductStageExecutor(ModelExecutor(primary=provider))
                context = {
                    "_verified_resume_prior_stages": {
                        "reconciliation": {"summary": summary},
                        "gap_analysis": {"recommended_next_work": [{"item": "Fix CRM #171"}]},
                    },
                    "_verified_resume_origin": {"generation": 16},
                }
                work = WorkItem("run-171", "task-171", "project-171", "crm-infodive",
                                ("planning",), context, execution_generation=16)
                if accepted:
                    handler.execute(work, "planning")
                    self.assertEqual(provider.calls, 1)
                else:
                    with self.assertRaisesRegex(PermissionError, "verified planning checkpoint is invalid"):
                        handler.execute(work, "planning")
                    self.assertEqual(provider.calls, 0)

    def test_planning_without_tasks_or_decisions_is_not_successful(self):
        class EmptyProvider:
            def execute(self,request):
                return ModelResult(ModelRole.PRIMARY,json.dumps({"tasks":[],"decisions_needed":[]}))
        handler=ProductStageExecutor(ModelExecutor(primary=EmptyProvider()))
        with self.assertRaises(PlanningNoActionableWork) as outcome:
            handler.execute(item(),"planning")
        self.assertIn("no actionable tasks or decisions", str(outcome.exception))
        self.assertNotIn(("r","planning"),handler.outputs)

    def test_missing_tasks_array_is_not_silent_completion(self):
        class MissingProvider:
            def execute(self,request):
                return ModelResult(ModelRole.PRIMARY,json.dumps({"architecture":"summary"}))
        handler=ProductStageExecutor(ModelExecutor(primary=MissingProvider()))
        with self.assertRaisesRegex(ValueError,"explicit tasks array"):
            handler.execute(item(),"planning")
        self.assertNotIn(("r","planning"),handler.outputs)

    def test_crm_conditions_builder_mix_validates_without_pre_pr_qa(self):
        from ai_product_factory.product_stage_executor import _validate_pre_pr_planning_tasks
        agents=(
            AgentProfile("development","development",("implementation","debug","integration"),
                         ("github_write",),{},1,0.5,True),
            AgentProfile("ui","ui",("ui","ux","accessibility"),
                         ("github_write",),{},1,0.5,True),
            AgentProfile("qa","qa",("tests","regression"),
                         ("github_read",),{},1,0.5,True),
        )
        for role in ("development","ui",None):
            with self.subTest(role=role):
                task={"task_key":"automation-modal-conditions",
                      "required_capabilities":["implementation","ui","tests","regression"],
                      "scope_keys":["src/components/automations/NewAutomationModal.tsx"],
                      "depends_on":[]}
                if role: task["preferred_agent_role"]=role
                _validate_pre_pr_planning_tasks({"tasks":[task]},agents)

    def test_planning_failure_identifies_capability_conflict_without_bypass(self):
        from ai_product_factory.product_stage_executor import _validate_pre_pr_planning_tasks
        dev=AgentProfile("development","development",("implementation",),
                         ("github_write",),{},1,0.5,True)
        task={"task_key":"automation-modal-conditions","preferred_agent_role":"development",
              "required_capabilities":["implementation","security_review"],
              "scope_keys":["src/components/automations/NewAutomationModal.tsx"],"depends_on":[]}
        with self.assertRaisesRegex(ValueError,"blocker=no_single_agent_covers_task"):
            _validate_pre_pr_planning_tasks({"tasks":[task]},(dev,))
        task["required_capabilities"]=["implementation","unknown_capability"]
        with self.assertRaisesRegex(ValueError,"unknown_capability"):
            _validate_pre_pr_planning_tasks({"tasks":[task]},(dev,))

    def test_planning_qa_only_cannot_become_pre_pr_builder(self):
        from ai_product_factory.product_stage_executor import _validate_pre_pr_planning_tasks
        dev=AgentProfile("development","development",("implementation",),
                         ("github_write",),{},1,0.5,True)
        qa_task={"task_key":"qa-only","required_capabilities":["tests","regression"],
                 "scope_keys":["tests"],"depends_on":[]}
        with self.assertRaisesRegex(ValueError,"pre-PR builder lane"):
            _validate_pre_pr_planning_tasks({"tasks":[qa_task]},(dev,))

    def test_planning_implementation_and_tests_uses_canonical_builder_capabilities(self):
        development=AgentProfile("development","development",("implementation","debug"),("github_write",),{},1,0.5,True)
        output={"tasks":[{"task_key":"automation-modal-conditions",
            "required_capabilities":["implementation","tests"],
            "preferred_agent_role":"development",
            "scope_keys":["src/components/automations/NewAutomationModal.tsx"],
            "depends_on":[]}]}
        from ai_product_factory.product_stage_executor import _validate_pre_pr_planning_tasks
        _validate_pre_pr_planning_tasks(output,(development,))
        self.assertEqual(output["tasks"][0]["required_capabilities"],["implementation","tests"])

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


    def test_greenfield_can_reconcile_from_exact_live_code_without_invented_db_snapshot(self):
        from ai_product_factory.greenfield_source_context import live_greenfield_source_context
        from unittest.mock import MagicMock
        github=MagicMock()
        github.repository="owner/desk"
        github.get_branch_sha.return_value="b"*40
        github.list_file_paths.return_value=("README.md","package.json","src/domain/ticket.ts")
        github.get_file_text.side_effect=lambda name,ref: {
            "README.md":"# Desk",
            "package.json":'{"name":"desk"}',
            "src/domain/ticket.ts":"export const allowed = true;",
        }[name]
        manifest={
            "source":"factory-console","onboarding_mode":"greenfield",
            "bootstrap_request_id":"706c6b5d-f41f-4c23-ac78-df9d9a1e4c7d",
            "continuation_request":{
                "source":"github-owner",
                "summary":"Inspect src/domain/ticket.ts for a real gap.",
                "github":{"repository":"leandrosilveiradepaula/ai-product-factory",
                           "issue_number":1055,"actor_id":256917842},
            },
        }
        context=live_greenfield_source_context(
            project={"project_kind":"greenfield","repository":"owner/desk","manifest":manifest},
            context={"manifest":manifest,"current_state_facts":{}},
            github=github,
        )
        self.assertNotIn("state_snapshot",context)
        item=WorkItem("run","task","project","desk",("reconciliation",),context)
        provider=Provider()
        handler=ProductStageExecutor(ModelExecutor(primary=provider))
        result=handler.execute(item,"reconciliation")
        self.assertEqual(result["stage"],"ok")
        self.assertEqual(len(provider.requests),1)
        self.assertIn("Console greenfield",provider.requests[0].objective)
        payload=json.loads(provider.requests[0].context)
        self.assertEqual(payload["intake"]["current_state_facts"]["live_candidate"]["sha"],"b"*40)
        self.assertIsNone(payload["intake"]["current_state_facts"]["live_candidate"]["verified_open_pr"])

    def test_fake_greenfield_receipt_cannot_bypass_durable_snapshot(self):
        from copy import deepcopy
        manifest={
            "source":"factory-console","onboarding_mode":"greenfield",
            "bootstrap_request_id":"706c6b5d-f41f-4c23-ac78-df9d9a1e4c7d",
            "continuation_request":{"source":"github-owner","github":{
                "repository":"leandrosilveiradepaula/ai-product-factory",
                "issue_number":1055,"actor_id":256917842}},
        }
        good={"manifest":manifest,"current_state_facts":{"live_candidate":{
            "observed_from":"live_greenfield_main_exact_sha",
            "branch":"main","sha":"b"*40,"main_sha":"b"*40,
            "verified_open_pr":None,
            "governance":{"README.md":"# Desk","package.json":"{}"},
            "source_evidence":{"status":"bounded_source_inspected",
                "assessed_commit":"b"*40,"inspected_files":[{
                    "path":"src/domain/ticket.ts","content":"export const x=1;",
                    "assessed_commit":"b"*40
                }]},
        }}}
        for mutation in (
            lambda x:x["current_state_facts"]["live_candidate"].update({"sha":"c"*40}),
            lambda x:x["current_state_facts"]["live_candidate"].update({"verified_open_pr":{"number":5}}),
            lambda x:x["current_state_facts"]["live_candidate"]["source_evidence"].update({"status":"no_scoped_source_paths"}),
            lambda x:x["manifest"]["continuation_request"]["github"].update({"actor_id":4}),
            lambda x:x["current_state_facts"]["live_candidate"].update({"observed_from":"unverified"}),
            lambda x:x["current_state_facts"]["live_candidate"]["source_evidence"]["inspected_files"][0].update({"assessed_commit":"a"*40}),
        ):
            with self.subTest(mutation=mutation):
                context=deepcopy(good)
                mutation(context)
                provider=Provider()
                handler=ProductStageExecutor(ModelExecutor(primary=provider))
                with self.assertRaisesRegex(ValueError,"durable state snapshot"):
                    handler.execute(WorkItem("r","t","p","desk",("reconciliation",),context),"reconciliation")
                self.assertEqual(provider.requests,[])

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

    def test_non_executed_marker_is_rejected_before_it_chains_to_next_stage(self):
        class DeferredProvider:
            def execute(self,request):
                return ModelResult(
                    ModelRole.PRIMARY,
                    json.dumps({"placeholder":True,"summary":"not executed"}),
                    provider_ref="provider-ref",
                )
        h=ProductStageExecutor(ModelExecutor(primary=DeferredProvider()))
        with self.assertRaisesRegex(ValueError,"product_stage_output_not_executed"):
            h.execute(item(),"discovery")
        self.assertNotIn(("r","discovery"),h.outputs)

    def test_status_marker_is_rejected_before_planning_can_materialize_work(self):
        class SimulatedPlanProvider:
            def execute(self,request):
                return ModelResult(
                    ModelRole.PRIMARY,
                    json.dumps({
                        "execution_status":"simulated",
                        "tasks":[{"task_key":"unsafe","scope_keys":["src/app.py"],"depends_on":[]}],
                    }),
                    provider_ref="provider-ref",
                )
        h=ProductStageExecutor(ModelExecutor(primary=SimulatedPlanProvider()))
        with self.assertRaisesRegex(ValueError,"product_stage_output_not_executed"):
            h.execute(item(),"planning")
        self.assertNotIn(("r","planning"),h.outputs)

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
