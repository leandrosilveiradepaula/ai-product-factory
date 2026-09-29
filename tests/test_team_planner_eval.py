import unittest
from pathlib import Path

from ai_product_factory.agent_scheduler import AgentProfile
from ai_product_factory.team_planner_eval import evaluate_team_planner_cases,load_team_planner_cases


ROOT=Path(__file__).resolve().parents[1]


def profile(key,role,caps,tools=("github_read",),concurrency=1,budget=0.25):
    return AgentProfile(
        agent_key=key,role=role,capabilities=tuple(caps),allowed_tools=tuple(tools),
        model_policy={"preferred":"deterministic"},max_concurrency=concurrency,
        cost_budget_usd=budget,is_active=True,
    )


PROFILES=(
    profile("development","development",("implementation","migration_authoring","integration","debug"),("github_write","model_primary"),3,1.5),
    profile("ui","ui",("ui","ux","accessibility","figma","browser_evidence"),("github_write","browser","model_primary"),2,0.75),
    profile("security","security",("security_review","auth","rls","secrets","supply_chain"),("github_read","supabase","model_primary"),2,0.5),
    profile("qa","qa",("tests","evals","regression","quality_gate"),("github_read","github_actions","browser"),3,0.25),
    profile("operations","operations",("ci","deployments","quotas","costs","logs","health"),("github_actions","vercel_read"),2,0.25),
)


class TeamPlannerEvalTests(unittest.TestCase):
    def test_offline_corpus_passes_without_model_or_external_service(self):
        cases=load_team_planner_cases(ROOT/"evals/team_planner_cases.json")
        summary=evaluate_team_planner_cases(cases,PROFILES)
        self.assertEqual(summary.cases,10)
        self.assertTrue(summary.ok,[failure.__dict__ for failure in summary.failures])
        self.assertEqual(summary.passed,10)

    def test_overstaffing_is_reported(self):
        cases=({"key":"small","plan":{"tasks":[
            {"task_key":"a","title":"A","required_capabilities":["implementation"],"scope_keys":["src/a"],"depends_on":[]},
            {"task_key":"b","title":"B","required_capabilities":["implementation"],"scope_keys":["src/b"],"depends_on":[]}
        ]},"expected":{"required_roles":["development"],"forbidden_roles":[],"max_worker_peak":1,"status":"ready"}},)
        summary=evaluate_team_planner_cases(cases,PROFILES)
        self.assertFalse(summary.ok)
        self.assertEqual(summary.failures[0].code,"overstaffed_worker_peak")


if __name__=="__main__":
    unittest.main()
