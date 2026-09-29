import unittest

from ai_product_factory.definition_of_done import compile_definition_of_done,evaluate_definition_of_done
from ai_product_factory.traceability import build_requirement_trace


class TraceabilityAndDoDTests(unittest.TestCase):
    def test_requirement_keys_are_stable_for_same_task_and_outcome(self):
        plan={"tasks":[{
            "task_key":"auth","title":"Auth reset",
            "acceptance_criteria":["User receives a reset link","Expired token is rejected"],
            "required_capabilities":["implementation"],"scope_keys":["src/auth"],"depends_on":[],
        }]}
        first=build_requirement_trace(plan)
        second=build_requirement_trace(plan)
        self.assertEqual(first.requirements,second.requirements)
        self.assertEqual(first.count,2)
        self.assertTrue(all(x["requirement_key"].startswith("REQ-") for x in first.requirements))
        self.assertEqual(first.requirements[0]["task_key"],"auth")
        self.assertTrue(first.requirements[0]["task_external_key"].startswith("plan-"))

    def test_explicit_requirement_key_is_preserved(self):
        plan={"tasks":[{
            "task_key":"api","title":"API",
            "acceptance_criteria":[{"requirement_key":"REQ-BUSINESS-17","statement":"Response contains customer id"}],
        }]}
        trace=build_requirement_trace(plan)
        self.assertEqual(trace.requirements[0]["requirement_key"],"REQ-BUSINESS-17")

    def test_empty_or_invalid_criteria_are_not_invented(self):
        trace=build_requirement_trace({"tasks":[{"task_key":"x","title":"X","acceptance_criteria":[{},None,""]}]})
        self.assertEqual(trace.count,0)

    def test_auth_implementation_dod_requires_ci_qa_security_preview_and_human_release(self):
        plan={"tasks":[{
            "task_key":"auth","title":"Auth","acceptance_criteria":["works"],
            "required_capabilities":["implementation","auth"],"scope_keys":["src/auth"],"depends_on":[],
        }]}
        dod=compile_definition_of_done(engineering_plan=plan,manifest={},requirement_count=1)
        keys={x.key for x in dod.checks}
        self.assertTrue({"requirements_traceable","github_ci","qa","security_review","preview","browser_evidence","human_release"}.issubset(keys))
        release=next(x for x in dod.checks if x.key=="human_release")
        self.assertTrue(release.human_only)

    def test_explicit_non_preview_project_does_not_require_preview_evidence(self):
        plan={"tasks":[{
            "task_key":"backend","title":"Backend","acceptance_criteria":["works"],
            "required_capabilities":["implementation"],"scope_keys":["src/core"],"depends_on":[],
        }]}
        dod=compile_definition_of_done(
            engineering_plan=plan,
            manifest={"preview":{"required":False,"reason":"backend only"}},
            requirement_count=1,
        )
        keys={x.key for x in dod.checks}
        self.assertNotIn("preview",keys)
        self.assertNotIn("browser_evidence",keys)

    def test_migration_and_api_checks_are_explicit_not_assumed_passed(self):
        plan={"tasks":[
            {"task_key":"db","title":"DB","acceptance_criteria":["schema applies"],"required_capabilities":["migration_authoring"],"scope_keys":["supabase/migrations"],"depends_on":[]},
            {"task_key":"api","title":"API","acceptance_criteria":["contract stable"],"required_capabilities":["implementation"],"scope_keys":["src/api"],"depends_on":["db"]},
        ]}
        dod=compile_definition_of_done(engineering_plan=plan,manifest={},requirement_count=2)
        keys={x.key for x in dod.checks}
        self.assertTrue({"migration_validation","rollback_analysis","api_contract"}.issubset(keys))
        state=evaluate_definition_of_done(definition=dod,evidence_types={"requirements_traceable","github_ci","qa"})
        self.assertFalse(state["ready"])
        self.assertIn("migration_validation",state["missing"])
        self.assertIn("human_release",state["missing"])


if __name__=="__main__":
    unittest.main()
