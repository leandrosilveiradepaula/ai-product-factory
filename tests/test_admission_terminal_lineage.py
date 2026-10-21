"""Regression for real CRM 19 Oct: completed root but superseded Change Set.

The official admission audit previously answered no_new_action for that
root while Journey verified only 5/12 stages. All tests are deterministic,
offline and never re-run model, CI, Preview or merge.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
import unittest

from ai_product_factory.admission_diagnostics import (
    SupabaseAdmissionReader, classify,
)
from ai_product_factory.admission_terminal_lineage import terminal_root_lineage

P="11111111-1111-4111-8111-111111111111"
T="22222222-2222-4222-8222-222222222222"
R="33333333-3333-4333-8333-333333333333"
CS="44444444-4444-4444-8444-444444444444"
WU="55555555-5555-4555-8555-555555555555"
OTHER="66666666-6666-4666-8666-666666666666"
COMMIT="a"*40


def run(status="completed",generation=4):
    return {"id":R,"task_id":T,"status":status,"metadata":{
        "source":"factory-console","execution_generation":generation},
        "execution_route":"direct","started_at":None}


def change_set(status="superseded",release=None,csid=CS,at="2026-10-19T17:45:00Z"):
    return {"id":csid,"project_id":P,"root_task_id":T,
        "status":status,"release_run_id":release,"created_at":at}


def unit(csid=CS,status="completed",commit=COMMIT):
    return {"id":WU,"change_set_id":csid,"status":status,"output_commit":commit}


def lineage(sets=None,units=None,root_run=None,epoch=6):
    return terminal_root_lineage(
        project_id=P,root_task_id=T,root_run=root_run or run(),
        current_generation=epoch,
        change_sets=[change_set()] if sets is None else sets,
        work_units=[unit()] if units is None else units,
    )


def admission(legacy=None):
    return classify(
        project={"id":P,"project_key":"crm-infodive","is_active":True,
                 "lifecycle_stage":"implementation"},
        control={"project_id":P,"state":"running","generation":6},
        commands=[],tasks=[{"id":T,"project_id":P,"status":"completed",
                             "parent_task_id":None}],
        runs=[run()],run_id=R,
        cost={"state":"available","reason":"within_budget"},
        planned=[],portfolio=[],terminal_lineage=legacy,
    )


class TerminalRootChangeSetTests(unittest.TestCase):
    def test_real_crm_superseded_work_unit_is_not_delivery(self):
        x=lineage()
        self.assertEqual(x["status"],"blocked")
        self.assertEqual(x["reason_code"],"root_change_set_superseded")
        self.assertEqual(x["next_step"],"review_obsolete_change_set_evidence")
        self.assertEqual(x["evidence"]["change_set_status"],"superseded")
        self.assertEqual(x["evidence"]["work_units_with_recorded_output_sha"],1)
        self.assertFalse(x["evidence"]["release_run_recorded"])
        self.assertTrue(x["evidence"]["execution_epoch_revoked"])
        self.assertFalse(x["evidence"]["delivery_verified"])
        out=admission(x)
        self.assertEqual(out["status"],"blocked")
        self.assertEqual(out["next_step"],"review_obsolete_change_set_evidence")
        self.assertEqual(out["reason_code"],"root_change_set_superseded")
        self.assertEqual(out["evidence"]["terminal_change_set"],x["evidence"])
        self.assertTrue(out["read_only"])
        self.assertNotIn(COMMIT,str(out))

    def test_greenfield_early_merge_cannot_claim_released(self):
        x=lineage(sets=[change_set("blocked",release=OTHER)],units=[])
        self.assertEqual(x["reason_code"],"root_change_set_blocked")
        self.assertEqual(x["next_step"],"review_blocked_change_set")
        self.assertTrue(x["evidence"]["release_run_recorded"])
        self.assertFalse(x["evidence"]["delivery_verified"])
        self.assertEqual(admission(x)["status"],"blocked")

    def test_active_same_epoch_vs_revoked_epoch(self):
        same=lineage(sets=[change_set("building")],epoch=4)
        old=lineage(sets=[change_set("building")],epoch=6)
        self.assertEqual(same["status"],"waiting")
        self.assertEqual(same["next_step"],"inspect_change_set_eligibility")
        self.assertEqual(old["status"],"blocked")
        self.assertEqual(old["reason_code"],"root_change_set_execution_epoch_revoked")
        self.assertEqual(old["next_step"],"review_new_human_continuation")

    def test_completed_change_set_does_not_infer_product_or_release(self):
        x=lineage(sets=[change_set("completed",release=OTHER)])
        self.assertEqual(x["status"],"waiting")
        self.assertEqual(x["next_step"],"verify_release_boundary")
        self.assertFalse(x["evidence"]["delivery_verified"])

    def test_old_root_is_never_implicitly_restarted(self):
        x=lineage(sets=[],units=[])
        self.assertIsNone(x)
        report=admission(x)
        self.assertEqual(report["reason_code"],"run_completed")
        self.assertEqual(report["next_step"],"no_new_action")

    def test_multiple_change_sets_select_latest_root_exactly(self):
        first=change_set("superseded",at="2026-10-10T00:00:00Z")
        latest=change_set("completed",csid=OTHER,release=R,at="2026-10-21T00:00:00Z")
        next_unit={**unit(csid=OTHER),"id":"77777777-7777-4777-8777-777777777777"}
        x=lineage(sets=[first,latest],units=[unit(),next_unit])
        self.assertEqual(x["evidence"]["change_set_id"],OTHER)
        self.assertEqual(x["evidence"]["historical_change_set_count"],1)
        self.assertEqual(x["evidence"]["work_unit_count"],1)
        self.assertEqual(x["next_step"],"verify_release_boundary")

    def test_exact_identity_and_cap_fail_closed_before_classification(self):
        valid=[change_set()]
        invalid=[
            ([{**valid[0],"project_id":OTHER}],[unit()]),
            ([{**valid[0],"root_task_id":OTHER}],[unit()]),
            ([{**valid[0],"status":"unknown"}],[unit()]),
            (valid+[valid[0]],[unit()]),
            (valid,[{**unit(),"change_set_id":OTHER}]),
            (valid,[{**unit(),"output_commit":"not-a-sha"}]),
            ([],[unit()]),
            (valid*31,[]),
        ]
        for sets,units in invalid:
            with self.subTest(sets=sets[:1],units=units[:1]):
                with self.assertRaises(RuntimeError):
                    lineage(sets=sets,units=units)
        with self.assertRaises(RuntimeError):
            lineage(root_run={**run(),"task_id":OTHER})

    def test_result_does_not_expose_untrusted_metadata(self):
        cs={**change_set(),"metadata":{"operator_secret":"test-confidential"}}
        wr={**unit(),"private_payload":"test-confidential"}
        x=lineage(sets=[cs],units=[wr])
        self.assertNotIn("test-confidential",str(x))
        self.assertEqual(
            set(x["evidence"]),
            {"change_set_id","change_set_status","historical_change_set_count",
             "work_unit_count","work_units_with_recorded_output_sha",
             "release_run_recorded","execution_epoch_revoked","delivery_verified"},
        )

    def test_invalid_injected_classifier_receipt_fails_closed(self):
        for forged in (
            {"status":"eligible","reason_code":"root_change_set_ready",
             "next_step":"dispatch","evidence":{"delivery_verified":True}},
            {"status":"blocked","reason_code":"root_change_set_blocked",
             "next_step":"review_blocked_change_set","evidence":{"delivery_verified":True}},
        ):
            with self.assertRaises(RuntimeError):
                admission(forged)

    def test_live_reader_only_reads_same_root_and_never_claims(self):
        accessed=[]
        def get(path):
            accessed.append(path)
            if path.startswith("factory_projects?"):
                return [{"id":P,"project_key":"crm-infodive",
                         "lifecycle_stage":"implementation","is_active":True,
                         "manifest":{}}]
            if path.startswith("factory_project_execution_controls?"):
                return [{"project_id":P,"state":"running","version":5,"generation":6}]
            if path.startswith("factory_project_execution_commands?"):
                return []
            if path.startswith("factory_tasks?"):
                return [{"id":T,"project_id":P,"status":"completed",
                         "parent_task_id":None}]
            if path.startswith("factory_runs?"):
                return [run()]
            if path.startswith("factory_change_sets?"):
                self.assertIn("root_task_id=eq."+T,path)
                self.assertIn("project_id=eq."+P,path)
                return [change_set()]
            if path.startswith("factory_change_set_work_units?"):
                self.assertIn("change_set_id=in.("+CS+")",path)
                return [unit()]
            if path.startswith("rpc/factory_peek_planned_work"):
                return []
            if path.startswith("rpc/factory_portfolio_candidates"):
                return []
            raise AssertionError("unexpected read: "+path)
        policy=SimpleNamespace(read=lambda:SimpleNamespace(
            budget_usd=Decimal("10"),reserve_usd=Decimal("0.5")))
        health=SimpleNamespace(read=lambda **kw:SimpleNamespace(
            known_cost=Decimal("0"),unknown_cost_events=0))
        reader=SupabaseAdmissionReader(get=get,policy_reader=policy,health_reader=health)
        report=reader.read(project_key="crm-infodive",run_id=R)
        self.assertEqual(report["reason_code"],"root_change_set_superseded")
        self.assertTrue(report["read_only"])
        self.assertFalse(any("claim" in x or "merge" in x or "dispatch_ci" in x
                             for x in accessed))

    def test_child_and_unscoped_diagnostics_skip_lineage_queries(self):
        accesses=[]
        def get(path):
            accesses.append(path)
            if path.startswith("factory_projects?"):
                return [{"id":P,"project_key":"crm-infodive",
                    "lifecycle_stage":"implementation","is_active":True,"manifest":{}}]
            if path.startswith("factory_project_execution_controls?"):
                return [{"project_id":P,"state":"running","version":5,"generation":6}]
            if path.startswith("factory_project_execution_commands?"):return []
            if path.startswith("factory_tasks?"):
                return [{"id":T,"project_id":P,"status":"completed",
                         "parent_task_id":OTHER}]
            if path.startswith("factory_runs?"):return [run()]
            if path.startswith("rpc/factory_peek_planned_work"):return []
            if path.startswith("rpc/factory_portfolio_candidates"):return []
            raise AssertionError("unexpected child lineage read: "+path)
        policy=SimpleNamespace(read=lambda:SimpleNamespace(
            budget_usd=Decimal("10"),reserve_usd=Decimal("0.5")))
        health=SimpleNamespace(read=lambda **kw:SimpleNamespace(
            known_cost=Decimal("0"),unknown_cost_events=0))
        reader=SupabaseAdmissionReader(get=get,policy_reader=policy,health_reader=health)
        self.assertEqual(reader.read(project_key="crm-infodive",run_id=R)["reason_code"],
                         "run_completed")
        self.assertFalse(any("factory_change_sets?" in x for x in accesses))


if __name__=="__main__":
    unittest.main()
