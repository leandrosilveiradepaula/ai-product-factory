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


def test_simple_task_uses_smallest_specialist_team():
    plan={"tasks":[{"task_key":"api","title":"Implement API","required_capabilities":["implementation"],"scope_keys":["src/api"],"depends_on":[]}]}
    out=build_execution_team_plan(plan,AGENTS)
    assert out["status"]=="ready"
    assert out["profiles_selected"]==1
    assert out["planned_worker_peak"]==1
    assert out["selected_agents"][0]["agent_key"]=="development"
    assert out["waves"][0]["task_keys"]==["api"]


def test_independent_non_conflicting_tasks_fan_out_within_concurrency():
    plan={"tasks":[
        {"task_key":"api-a","title":"API A","required_capabilities":["implementation"],"scope_keys":["src/a"],"depends_on":[]},
        {"task_key":"api-b","title":"API B","required_capabilities":["implementation"],"scope_keys":["src/b"],"depends_on":[]},
        {"task_key":"ui","title":"UI","required_capabilities":["ui"],"scope_keys":["apps/console"],"depends_on":[]},
    ]}
    out=build_execution_team_plan(plan,AGENTS)
    assert out["status"]=="ready"
    assert out["profiles_selected"]==2
    assert out["planned_worker_peak"]==3
    assert set(out["waves"][0]["task_keys"])=={"api-a","api-b","ui"}
    dev=next(x for x in out["selected_agents"] if x["agent_key"]=="development")
    assert dev["workers_planned"]==2


def test_scope_conflicts_serialize_even_without_dependency():
    plan={"tasks":[
        {"task_key":"a","title":"A","required_capabilities":["implementation"],"scope_keys":["src/auth"],"depends_on":[]},
        {"task_key":"b","title":"B","required_capabilities":["implementation"],"scope_keys":["src/auth/session"],"depends_on":[]},
    ]}
    out=build_execution_team_plan(plan,AGENTS)
    assert len(out["waves"])==2
    assert out["planned_worker_peak"]==1


def test_dependencies_create_execution_waves():
    plan={"tasks":[
        {"task_key":"backend","title":"Backend","required_capabilities":["implementation"],"scope_keys":["src/api"],"depends_on":[]},
        {"task_key":"tests","title":"Tests","required_capabilities":["tests"],"scope_keys":["tests"],"depends_on":["backend"]},
    ]}
    out=build_execution_team_plan(plan,AGENTS)
    assert [x["task_keys"] for x in out["waves"]]==[["backend"],["tests"]]
    assert {x["agent_key"] for x in out["selected_agents"]}=={"development","qa"}


def test_impossible_single_owner_capability_mix_fails_closed():
    plan={"tasks":[{"task_key":"mixed","title":"Mixed","required_capabilities":["implementation","security_review"],"scope_keys":["src/auth"],"depends_on":[]}]}
    out=build_execution_team_plan(plan,AGENTS)
    assert out["status"]=="blocked"
    assert out["blockers"][0]["code"]=="no_single_agent_covers_task"
    assert out["planned_worker_peak"]==0


def test_sensitive_risk_recommends_independent_security_lane_without_granting_write():
    plan={"tasks":[{"task_key":"auth","title":"Auth change","required_capabilities":["implementation"],"scope_keys":["src/auth"],"depends_on":[],"risk":{"expands_sensitive_access":True}}]}
    out=build_execution_team_plan(plan,AGENTS)
    advisory=next(x for x in out["advisory_specialist_lanes"] if x["role"]=="security")
    assert advisory["execution_ready"] is False
    assert "non-writing specialist lane" in advisory["note"]
    assert out["selected_agents"][0]["agent_key"]=="development"


def test_unresolved_dependency_blocks_plan():
    plan={"tasks":[{"task_key":"ui","title":"UI","required_capabilities":["ui"],"scope_keys":["apps/console"],"depends_on":["missing"]}]}
    out=build_execution_team_plan(plan,AGENTS)
    assert out["status"]=="blocked"
    assert any(x["code"]=="unresolved_dependency" for x in out["blockers"])
