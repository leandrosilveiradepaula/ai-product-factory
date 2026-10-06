import unittest

from ai_product_factory.agent_scheduler import AgentProfile
from ai_product_factory.execution_team_planner import build_execution_team_plan


def profile(key,role,caps,tools=("github_read",),concurrency=1,budget=0.25):
    return AgentProfile(
        agent_key=key,
        role=role,
        capabilities=tuple(caps),
        allowed_tools=tuple(tools),
        model_policy={"preferred":"deterministic"},
        max_concurrency=concurrency,
        cost_budget_usd=budget,
        is_active=True,
    )


AGENTS=(
    profile("development","development",("implementation","migration_authoring","integration","debug"),("github_write","model_primary"),3,1.5),
    profile("ui","ui",("ui","ux","accessibility","figma","browser_evidence"),("github_write","browser","model_primary"),2,0.75),
    profile("security","security",("security_review","auth","rls","secrets","supply_chain"),("github_read","supabase","model_primary"),2,0.5),
    profile("qa","qa",("tests","evals","regression","quality_gate"),("github_read","github_actions","browser"),3,0.25),
    profile("operations","operations",("ci","deployments","quotas","costs","logs","health"),("github_actions","vercel_read"),2,0.25),
)


class ExecutionTeamPlannerTests(unittest.TestCase):
    def test_simple_task_uses_smallest_specialist_team(self):
        plan={"tasks":[{"task_key":"api","title":"Implement API","required_capabilities":["implementation"],"scope_keys":["src/api"],"depends_on":[]}]}
        out=build_execution_team_plan(plan,AGENTS)
        self.assertEqual(out["status"],"ready")
        self.assertEqual(out["profiles_selected"],1)
        self.assertEqual(out["planned_worker_peak"],1)
        self.assertEqual(out["selected_agents"][0]["agent_key"],"development")
        self.assertEqual(out["waves"][0]["task_keys"],["api"])

    def test_independent_non_conflicting_tasks_fan_out_within_concurrency(self):
        plan={"tasks":[
            {"task_key":"api-a","title":"API A","required_capabilities":["implementation"],"scope_keys":["src/a"],"depends_on":[]},
            {"task_key":"api-b","title":"API B","required_capabilities":["implementation"],"scope_keys":["src/b"],"depends_on":[]},
            {"task_key":"ui","title":"UI","required_capabilities":["ui"],"scope_keys":["apps/console"],"depends_on":[]},
        ]}
        out=build_execution_team_plan(plan,AGENTS)
        self.assertEqual(out["status"],"ready")
        self.assertEqual(out["profiles_selected"],2)
        self.assertEqual(out["planned_worker_peak"],3)
        self.assertEqual(set(out["waves"][0]["task_keys"]),{"api-a","api-b","ui"})
        dev=next(x for x in out["selected_agents"] if x["agent_key"]=="development")
        self.assertEqual(dev["workers_planned"],2)

    def test_context_paths_survive_into_task_assignment(self):
        plan={"tasks":[{
            "task_key":"debug",
            "title":"Debug remediation",
            "required_capabilities":["implementation"],
            "scope_keys":["src/app/debug"],
            "context_paths":["AGENTS.md","docs/codex/CURRENT_TASK.md","src/app/debug/page.tsx"],
            "depends_on":[],
        }]}
        out=build_execution_team_plan(plan,AGENTS)
        assignment=out["task_assignments"][0]
        self.assertEqual(
            assignment["context_paths"],
            ["AGENTS.md","docs/codex/CURRENT_TASK.md","src/app/debug/page.tsx"],
        )

    def test_scope_conflicts_serialize_even_without_dependency(self):
        plan={"tasks":[
            {"task_key":"a","title":"A","required_capabilities":["implementation"],"scope_keys":["src/auth"],"depends_on":[]},
            {"task_key":"b","title":"B","required_capabilities":["implementation"],"scope_keys":["src/auth/session"],"depends_on":[]},
        ]}
        out=build_execution_team_plan(plan,AGENTS)
        self.assertEqual(len(out["waves"]),2)
        self.assertEqual(out["planned_worker_peak"],1)

    def test_builder_dependencies_create_execution_waves(self):
        plan={"tasks":[
            {"task_key":"backend","title":"Backend","required_capabilities":["implementation"],"scope_keys":["src/api"],"depends_on":[]},
            {"task_key":"integration","title":"Integration","required_capabilities":["integration"],"scope_keys":["src/integration"],"depends_on":["backend"]},
        ]}
        out=build_execution_team_plan(plan,AGENTS)
        self.assertEqual(out["status"],"ready")
        self.assertEqual([x["task_keys"] for x in out["waves"]],[["backend"],["integration"]])

    def test_read_only_specialist_task_uses_dedicated_lane(self):
        plan={"tasks":[
            {"task_key":"backend","title":"Backend","required_capabilities":["implementation"],"scope_keys":["src/api"],"depends_on":[]},
            {"task_key":"tests","title":"Tests","required_capabilities":["tests"],"scope_keys":["tests"],"depends_on":["backend"]},
        ]}
        out=build_execution_team_plan(plan,AGENTS)
        self.assertEqual(out["status"],"ready")
        self.assertEqual(out["waves"][0]["task_keys"],["backend"])
        qa=next(x for x in out["selected_agents"] if x["agent_key"]=="qa")
        self.assertTrue(qa["execution_ready"])
        self.assertEqual(qa["execution_lane"],"specialist")
        self.assertEqual(qa["workers_planned"],1)
        self.assertEqual(out["blockers"],[])

    def test_impossible_single_owner_capability_mix_fails_closed(self):
        plan={"tasks":[{"task_key":"mixed","title":"Mixed","required_capabilities":["implementation","security_review"],"scope_keys":["src/auth"],"depends_on":[]}]}
        out=build_execution_team_plan(plan,AGENTS)
        self.assertEqual(out["status"],"blocked")
        self.assertEqual(out["blockers"][0]["code"],"no_single_agent_covers_task")
        self.assertEqual(out["planned_worker_peak"],0)

    def test_sensitive_risk_recommends_independent_security_lane_without_granting_write(self):
        plan={"tasks":[{"task_key":"auth","title":"Auth change","required_capabilities":["implementation"],"scope_keys":["src/auth"],"depends_on":[],"risk":{"expands_sensitive_access":True}}]}
        out=build_execution_team_plan(plan,AGENTS)
        advisory=next(x for x in out["advisory_specialist_lanes"] if x["role"]=="security")
        self.assertFalse(advisory["execution_ready"])
        self.assertIn("not represented as an explicit planned task",advisory["note"])
        self.assertEqual(out["selected_agents"][0]["agent_key"],"development")

    def test_specialist_reviews_become_post_candidate_advisory_lanes(self):
        plan={
            "tasks":[{
                "task_key":"api",
                "title":"Implement API",
                "required_capabilities":["implementation"],
                "scope_keys":["src/api"],
                "depends_on":[]
            }],
            "specialist_reviews":["security","qa","operations"]
        }
        out=build_execution_team_plan(plan,AGENTS)
        self.assertEqual(out["status"],"ready")
        self.assertEqual(out["waves"][0]["task_keys"],["api"])
        advisory={row["role"]:row for row in out["advisory_specialist_lanes"]}
        self.assertEqual(set(advisory),{"security","qa","operations"})
        self.assertTrue(all(row["execution_ready"] is False for row in advisory.values()))
        self.assertTrue(all("post-candidate" in row["reasons"][0] for row in advisory.values()))

    def test_structured_specialist_reviews_become_post_candidate_advisory_lanes(self):
        plan={
            "tasks":[{
                "task_key":"api",
                "title":"Implement API",
                "required_capabilities":["implementation"],
                "scope_keys":["src/api"],
                "depends_on":[]
            }],
            "specialist_reviews":[{
                "role":"security",
                "review_key":"debug_security_post_candidate_review",
                "timing":"after candidate",
                "required_evidence":["candidate revision"],
                "review_criteria":["confirm raw rows are not exposed"]
            }]
        }
        out=build_execution_team_plan(plan,AGENTS)
        self.assertEqual(out["status"],"ready")
        advisory=next(x for x in out["advisory_specialist_lanes"] if x["role"]=="security")
        self.assertIn("debug_security_post_candidate_review",advisory["reasons"][0])

    def test_unresolved_dependency_blocks_plan(self):
        plan={"tasks":[{"task_key":"ui","title":"UI","required_capabilities":["ui"],"scope_keys":["apps/console"],"depends_on":["missing"]}]}
        out=build_execution_team_plan(plan,AGENTS)
        self.assertEqual(out["status"],"blocked")
        self.assertTrue(any(x["code"]=="unresolved_dependency" for x in out["blockers"]))


    def test_dogfood_style_aliases_map_to_canonical_registry_without_widening_tools(self):
        plan={"tasks":[
            {"task_key":"DISCOVER_PROBE_CONTRACT","title":"DISCOVER_PROBE_CONTRACT","required_capabilities":["repository_analysis","architecture"],"scope_keys":["."],"depends_on":[],"preferred_agent_role":"repository_archaeologist"},
            {"task_key":"DEFINE_TELEMETRY_SCHEMA","title":"DEFINE_TELEMETRY_SCHEMA","required_capabilities":["implementation","database","supabase"],"scope_keys":["supabase"],"depends_on":["DISCOVER_PROBE_CONTRACT"],"preferred_agent_role":"backend_engineer"},
            {"task_key":"IMPLEMENT_PROBE_TELEMETRY_WRITER","title":"IMPLEMENT_PROBE_TELEMETRY_WRITER","required_capabilities":["implementation","backend","supabase"],"scope_keys":["src"],"depends_on":["DEFINE_TELEMETRY_SCHEMA"],"preferred_agent_role":"backend_engineer"},
            {"task_key":"ADD_TELEMETRY_TESTS","title":"ADD_TELEMETRY_TESTS","required_capabilities":["tests","implementation","database_testing"],"scope_keys":["tests"],"depends_on":["IMPLEMENT_PROBE_TELEMETRY_WRITER"],"preferred_agent_role":"test_engineer"},
            {"task_key":"REVIEW_TELEMETRY_SECURITY","title":"REVIEW_TELEMETRY_SECURITY","required_capabilities":["security_review","supabase","oidc"],"scope_keys":["supabase"],"depends_on":["IMPLEMENT_PROBE_TELEMETRY_WRITER"],"preferred_agent_role":"security_engineer"},
            {"task_key":"VALIDATE_CI_AND_MIGRATION","title":"VALIDATE_CI_AND_MIGRATION","required_capabilities":["ci","tests","supabase","release_engineering"],"scope_keys":[".github"],"depends_on":["ADD_TELEMETRY_TESTS","REVIEW_TELEMETRY_SECURITY"],"preferred_agent_role":"release_engineer"},
            {"task_key":"HUMAN_PRODUCTION_RELEASE_GATE","title":"HUMAN_PRODUCTION_RELEASE_GATE","required_capabilities":["human_approval","release_management"],"scope_keys":[".github"],"depends_on":["VALIDATE_CI_AND_MIGRATION"],"preferred_agent_role":"release_manager"},
        ]}
        out=build_execution_team_plan(plan,AGENTS)
        self.assertEqual(out["status"],"ready")
        by_key={row["task_key"]:row for row in out["task_assignments"]}
        self.assertEqual(by_key["DISCOVER_PROBE_CONTRACT"]["agent_key"],"development")
        self.assertEqual(by_key["DEFINE_TELEMETRY_SCHEMA"]["agent_key"],"development")
        self.assertEqual(by_key["IMPLEMENT_PROBE_TELEMETRY_WRITER"]["agent_key"],"development")
        self.assertEqual(by_key["ADD_TELEMETRY_TESTS"]["agent_key"],"development")
        self.assertEqual(by_key["REVIEW_TELEMETRY_SECURITY"]["agent_key"],"security")
        self.assertEqual(by_key["REVIEW_TELEMETRY_SECURITY"]["execution_lane"],"specialist")
        self.assertEqual(by_key["VALIDATE_CI_AND_MIGRATION"]["agent_key"],"operations")
        self.assertEqual(by_key["VALIDATE_CI_AND_MIGRATION"]["execution_lane"],"specialist")
        self.assertEqual(by_key["HUMAN_PRODUCTION_RELEASE_GATE"]["execution_lane"],"human_gate")
        self.assertIsNone(by_key["HUMAN_PRODUCTION_RELEASE_GATE"]["agent_key"])
        self.assertEqual(by_key["DEFINE_TELEMETRY_SCHEMA"]["source_preferred_agent_role"],"backend_engineer")
        self.assertIn("supabase",by_key["DEFINE_TELEMETRY_SCHEMA"]["source_required_capabilities"])
        self.assertTrue(all(row["agent_key"] in {"development","security","operations",None} for row in by_key.values()))

if __name__=="__main__":
    unittest.main()
