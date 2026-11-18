"""No-model, fail-closed Platform planning recovery admission tests."""
import unittest
from ai_product_factory.supabase_runtime_queue import (
    _verified_platform_empty_plan_checkpoint,
    _assert_changed_platform_source_for_empty_plan,
)
OLD = "a"*40
NEW = "b"*40

def source():
    return {"error":"planning has no actionable tasks or decisions","source":"factory-console",
        "stage_evidence":{"reconciliation":{"status":"completed"},
        "gap_analysis":{"status":"completed"},"planning":{"status":"failed",
        "output":{"reason_code":"planning_non_actionable","assessed_commit":OLD,
          "observed_model_response":True,"tasks_count":0,"decisions_count":0,
          "implementation_completed":False,"requires_scope_reconciliation":True}}}}

def context():
    return {"_verified_resume_origin":{"source_failure":"planning_non_actionable","source_commit":OLD},
        "current_state_facts":{"live_candidate":{
            "sha":NEW,"main_sha":NEW,
            "source_evidence":{"assessed_commit":NEW,"issue_reference":1506,
                               "status":"bounded_source_inspected"},
            "source_admission":{"assessed_commit":NEW,"code_inspected":True}
        }}}

class PlatformEmptyPlanTests(unittest.TestCase):
    def test_typed_receipt_and_changed_source_permitted_without_paid_call(self):
        self.assertTrue(_verified_platform_empty_plan_checkpoint(source(),{
            "source_failure":"planning_non_actionable","source_commit":OLD}))
        _assert_changed_platform_source_for_empty_plan(context())

    def test_typed_receipt_mutants_fail_closed(self):
        for key,value in (("error","other"),("source","github-owner")):
            m=source();m[key]=value
            self.assertFalse(_verified_platform_empty_plan_checkpoint(m,{
                "source_failure":"planning_non_actionable","source_commit":OLD}))
        for key,value in (("reason_code","other"),("assessed_commit",NEW),
                          ("observed_model_response","true"),("tasks_count",True),
                          ("tasks_count",1),("decisions_count",2),
                          ("implementation_completed",True),
                          ("requires_scope_reconciliation",False)):
            m=source();m["stage_evidence"]["planning"]["output"][key]=value
            self.assertFalse(_verified_platform_empty_plan_checkpoint(m,{
                "source_failure":"planning_non_actionable","source_commit":OLD}))
        m=source();m["stage_evidence"]["reconciliation"]["status"]="failed"
        self.assertFalse(_verified_platform_empty_plan_checkpoint(m,{
            "source_failure":"planning_non_actionable","source_commit":OLD}))
        self.assertFalse(_verified_platform_empty_plan_checkpoint(source(),{}))

    def test_same_sha_or_unverified_source_denied(self):
        for kind in ("same_sha","missing_issue","uninspected","wrong_main"):
            ctx=context();live=ctx["current_state_facts"]["live_candidate"]
            if kind=="same_sha":live["sha"]=OLD;live["main_sha"]=OLD
            if kind=="missing_issue":live["source_evidence"]["issue_reference"]=None
            if kind=="uninspected":live["source_admission"]["code_inspected"]=False
            if kind=="wrong_main":live["main_sha"]=OLD
            with self.subTest(kind=kind),self.assertRaises(PermissionError):
                _assert_changed_platform_source_for_empty_plan(ctx)

    def test_legacy_budget_path_not_subject_to_new_guard(self):
        _assert_changed_platform_source_for_empty_plan({
            "_verified_resume_origin":{"source_failure":"budget_reservation"}})

if __name__=="__main__":
    unittest.main()
