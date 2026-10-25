"""Regression: real multi-wave CI repair and preview-only integration are not production.

All fixtures are isolated, GET-only stand-ins. No model, GitHub writes,
production database, deployment or new project is used by these tests.
"""
from __future__ import annotations

import copy
import unittest
from unittest.mock import Mock, patch

from ai_product_factory.autonomy_journey import evaluate_journey
from ai_product_factory.autonomy_journey_reader import SupabaseJourneyReader, GLOBAL_RELEASE_EVENTS
from ai_product_factory.github_loop import CIState
from ai_product_factory.journey_candidate_provenance import (
    verify_copied_work_unit_waves,
)

PID="00000000-0000-4000-8000-000000000001"
ROOT="00000000-0000-4000-8000-000000000002"
WORK="00000000-0000-4000-8000-000000000003"
DELIVERY="00000000-0000-4000-8000-000000000004"
CS="00000000-0000-4000-8000-000000000005"
CANDIDATE="a"*40
MERGE="b"*40
BRANCH="factory/change-set-000"
BASE="preview/hardening-release-candidate"
REPO="owner/crm-real"
URL="https://crm-real-preview.vercel.app"
REF="vercel-status-verified-123"
SNAP="00000000-0000-4000-8000-000000000006"


def fixture():
    def event(name,run=DELIVERY,**payload):
        return {
            "event_type":name,"project_id":PID,"run_id":run,
            "actor_ref":"worker","payload":payload,
        }
    events=[
        event("product.stage.persisted",ROOT,stage=stage)
        for stage in ("reconciliation","gap_analysis","planning")
    ]
    events.extend((
        event("change_set.materialized",ROOT,change_set_id=CS),
        event("change_set.work_unit.dispatched",WORK,work_unit_id="unit-1"),
    ))
    for kind in ("qa","security","github_ci","operations"):
        events.append(event("delivery.evidence.recorded",
                            evidence_type=kind,status="passed",evidence_ref=CANDIDATE))
    events.extend((
        event("quality_gate.passed",candidate_commit=CANDIDATE),
        event("preview.browser_evidence_recorded",status="success",preview_url=URL),
        event("release.policy.decided",outcome="ready_for_human_release"),
        event("run.status.updated",status="awaiting_release",candidate_commit=CANDIDATE),
        event("release.awaiting_human_merge",pr=197,head_sha=CANDIDATE,
              deployment_ref=REF,preview_url=URL),
    ))
    for kind in ("preview","browser_evidence"):
        events.append(event("delivery.evidence.recorded",evidence_type=kind,
                            status="passed",evidence_ref=REF))
    receipt=event(
        "change_set.nonproduction_merge.observed",
        merged=True,repository=REPO,pr_number="197",head_sha=CANDIDATE,
        candidate_commit=CANDIDATE,head_ref=BRANCH,base_ref=BASE,
        merge_sha=MERGE,production_released=False,
        production_release_completed=False,
    )
    receipt["actor_ref"]="nonproduction-release-observer"
    events.append(receipt)
    return {
        "project":{"id":PID,"project_key":"crm-real","project_kind":"existing",
                   "repository":REPO,
                   "manifest":{"delivery_target":{"mode":"open_pr_candidate",
                                                   "branch":BASE}}},
        "root_run_id":ROOT,
        "start_command":{"command":"start","actor_id":"authorized-operator",
                         "result":{"run_id":ROOT}},
        "runs":[
            {"id":ROOT,"status":"completed"},
            {"id":WORK,"status":"completed"},
            {"id":DELIVERY,"status":"integrated"},
        ],
        "events":events,
        "change_sets":[{
            "id":CS,"project_id":PID,"root_task_id":ROOT,
            "status":"completed","candidate_commit":CANDIDATE,
        }],
        "work_units":[{
            "id":"unit-1","change_set_id":CS,"run_id":WORK,"status":"integrated",
            "output_commit":"c"*40,"changed_files":["src/feature.py"],
        }],
        "create_pr_receipts":[{
            "run_id":DELIVERY,"operation":"create_pr",
            "metadata":{"head_sha":CANDIDATE,"pr":197,"change_set_id":CS},
        }],
        "candidate_reconciliations":[],
        "deployments":[{
            "run_id":DELIVERY,"environment":"preview","status":"success",
            "metadata":{"provider":"vercel-github","candidate_commit":CANDIDATE,
                        "preview_url":URL},
        }],
        "release_reports":[],
        "github":{
            "repository":REPO,"number":197,"head_sha":CANDIDATE,
            "head_repository":REPO,"base_ref":BASE,
            "merged":True,"merge_commit_sha":MERGE,
            "ci_state":CIState.SUCCESS,"work_unit_commit_verified":True,
            "candidate_reconciliation_verified":True,
            "nonproduction_integration_verified":True,
        },
        "preview_required":True,
    }


class PreviewIntegrationEvidenceTests(unittest.TestCase):
    def test_preview_integration_is_typed_and_not_production(self):
        report=evaluate_journey(**fixture())
        self.assertEqual(report.status,"integrated_nonproduction")
        self.assertEqual(report.highest_verified,"awaiting_release")
        self.assertTrue(report.nonproduction_integrated)
        self.assertEqual(report.nonproduction_merge_sha,MERGE)
        self.assertEqual(report.stages[-2].status,"not_reached")
        self.assertEqual(report.stages[-1].status,"not_reached")
        self.assertFalse(report.as_json()["product_ready"])
        self.assertEqual(report.as_json()["writes"],0)

    def test_legacy_null_project_browser_is_valid_only_with_exact_run_url_and_deployment(self):
        # Control Plane historically writes this browser receipt with
        # project_id=NULL; its run_id and URL are still exact and immutable.
        d=fixture()
        browser=next(row for row in d["events"]
                     if row["event_type"]=="preview.browser_evidence_recorded")
        browser["project_id"]=None
        self.assertEqual(evaluate_journey(**d).status,"integrated_nonproduction")
        for change in (
            lambda row:row.update(run_id=ROOT),
            lambda row:row["payload"].update(preview_url="https://wrong.vercel.app"),
            lambda row:row["payload"].update(status="failed"),
        ):
            bad=copy.deepcopy(d)
            row=next(e for e in bad["events"]
                     if e["event_type"]=="preview.browser_evidence_recorded")
            change(row)
            with self.subTest(change=repr(change)):
                r=evaluate_journey(**bad)
                self.assertNotEqual(r.status,"integrated_nonproduction")
                self.assertFalse(r.nonproduction_integrated)

    def test_browser_not_scoped_to_run_never_certifies_other_project(self):
        d=fixture()
        row=next(e for e in d["events"]
                 if e["event_type"]=="preview.browser_evidence_recorded")
        row["project_id"]=None
        row["run_id"]="00000000-0000-4000-8000-000000000099"
        self.assertEqual(evaluate_journey(**d).highest_verified,"github_ci")

    def test_preview_status_must_bind_provider_receipts_to_exact_candidate(self):
        for mutation in (
            lambda d:d["deployments"][0]["metadata"].update(candidate_commit="f"*40),
            lambda d:d["deployments"][0]["metadata"].update(preview_url="https://other.vercel.app"),
            lambda d:d["deployments"][0]["metadata"].update(provider="other"),
            lambda d:d["events"].__setitem__(
                -1,{**d["events"][-1],"run_id":ROOT}),
            lambda d:d["events"].__setitem__(
                -2,{**d["events"][-2],
                    "payload":{**d["events"][-2]["payload"],"evidence_ref":"unknown"}}),
            lambda d:d["events"].__setitem__(
                next(i for i,e in enumerate(d["events"])
                     if e["event_type"]=="preview.browser_evidence_recorded"),
                event_with_wrong_preview(d)),
        ):
            d=fixture()
            mutation(d)
            with self.subTest(case=repr(mutation)):
                result=evaluate_journey(**d)
                self.assertNotEqual(result.status,"integrated_nonproduction")
                self.assertFalse(result.nonproduction_integrated)

    def test_no_unverified_merge_can_complete_preview_or_release(self):
        def remove_observer(d):
            d["events"]=[e for e in d["events"]
                         if e["event_type"]!="change_set.nonproduction_merge.observed"]
        for modify in (
            remove_observer,
            lambda d:d["github"].update(nonproduction_integration_verified=False),
            lambda d:d["github"].update(merge_commit_sha="f"*40),
            lambda d:d["change_sets"][0].update(status="preview_ready"),
            lambda d:d["runs"][-1].update(status="awaiting_release"),
            lambda d:d["events"].append(copy.deepcopy(d["events"][-1])),
            lambda d:d["events"][-1]["payload"].update(production_released=True),
        ):
            d=fixture()
            modify(d)
            with self.subTest(change=repr(modify)):
                report=evaluate_journey(**d)
                self.assertNotEqual(report.status,"integrated_nonproduction")
                self.assertNotEqual(report.status,"observed_complete")
                self.assertFalse(report.nonproduction_integrated)

    def test_preview_base_never_accepts_forged_production_report(self):
        d=fixture()
        d["release_reports"]=[{
            "project_id":PID,"run_id":DELIVERY,"status":"released",
            "candidate_commit":CANDIDATE,
        }]
        report=evaluate_journey(**d)
        self.assertEqual(report.status,"blocked")
        self.assertIn("preview_integration_conflicts_with_production_release_report",
                      report.blockers)
        self.assertNotEqual(report.highest_verified,"operations")


def event_with_wrong_preview(d):
    found=next(e for e in d["events"]
               if e["event_type"]=="preview.browser_evidence_recorded")
    return {**found,"payload":{**found["payload"],"preview_url":"https://wrong.vercel.app"}}


class LegacyGlobalBrowserReadTests(unittest.TestCase):
    def test_only_exact_run_and_allowlisted_null_project_event_is_fetched(self):
        self.assertIn("preview.browser_evidence_recorded",GLOBAL_RELEASE_EVENTS)
        self.assertNotIn("delivery.evidence.recorded",GLOBAL_RELEASE_EVENTS)
        reader=SupabaseJourneyReader(
            url="https://example.supabase.co",secret_key="sb_secret_test",
        )
        event={
            "id":147,"run_id":DELIVERY,"project_id":None,
            "event_type":"preview.browser_evidence_recorded",
            "payload":{"status":"success","preview_url":URL},
        }
        with patch.object(reader,"_get",return_value=[event]) as getter:
            got=reader._many_ids(
                "factory_audit_events",
                cols="id,project_id,run_id,event_type,payload",
                fk="run_id",ids={DELIVERY},
                extra="project_id=is.null&event_type=in.("
                + ",".join(GLOBAL_RELEASE_EVENTS) + ")",
                limit=201,
            )
        self.assertEqual(got,[event])
        query=getter.call_args.args[0]
        self.assertIn("run_id=in.("+DELIVERY+")",query)
        self.assertIn("project_id=is.null",query)
        self.assertIn("preview.browser_evidence_recorded",query)
        with patch.object(reader,"_get",return_value=[
            {**event,"run_id":ROOT}
        ]):
            with self.assertRaisesRegex(RuntimeError,"cross-lineage"):
                reader._many_ids(
                    "factory_audit_events",
                    cols="id,project_id,run_id,event_type,payload",
                    fk="run_id",ids={DELIVERY},
                )


class MultiWaveCopyEvidenceTests(unittest.TestCase):
    def test_each_work_unit_matches_first_attested_wave_not_last(self):
        c1,c2="a"*40,"b"*40
        u1,u2="1"*40,"2"*40
        receipts=[
            {"id":10,"created_at":"2026-10-25T00:10:00Z",
             "metadata":{"head_sha":c1,"pr":197,"change_set_id":CS}},
            {"id":20,"created_at":"2026-10-25T00:20:00Z",
             "metadata":{"head_sha":c2,"pr":197,"change_set_id":CS}},
        ]
        units=[
            {"status":"integrated","output_commit":u1,
             "created_at":"2026-10-25T00:05:00Z","changed_files":["src/feature.py"]},
            {"status":"integrated","output_commit":u2,
             "created_at":"2026-10-25T00:15:00Z","changed_files":["src/feature.py"]},
        ]
        github=Mock()
        github.compare_commits.return_value={"status":"ahead","ahead_by":1,"behind_by":0}
        github.commit_exists.return_value=True
        content={u1:"old",c1:"old",u2:"new",c2:"new"}
        github.get_file_text.side_effect=lambda path,ref:content[ref]
        kwargs=dict(github=github,final_candidate=c2,units=units,
                    receipts=receipts,change_set_id=CS,pr_number=197)
        self.assertTrue(verify_copied_work_unit_waves(**kwargs))
        for change in (
            lambda x:x["receipts"][0]["metadata"].update(pr=198),
            lambda x:x["receipts"][1].update(created_at="2026-10-25T00:09:00Z"),
            lambda x:x["receipts"][1]["metadata"].update(head_sha=c1),
            lambda x:x["units"][1].update(created_at="2026-10-25T00:30:00Z"),
            lambda x:x["units"][0].update(changed_files=["../out-of-scope"]),
        ):
            attempt={"github":github,"final_candidate":c2,
                     "units":copy.deepcopy(units),"receipts":copy.deepcopy(receipts),
                     "change_set_id":CS,"pr_number":197}
            change(attempt)
            with self.subTest(change=repr(change)):
                self.assertFalse(verify_copied_work_unit_waves(**attempt))
        content[u2]="forged"
        self.assertFalse(verify_copied_work_unit_waves(**kwargs))


class NonproductionSnapshotReaderTests(unittest.TestCase):
    def setUp(self):
        self.reader=SupabaseJourneyReader(
            url="https://example.supabase.co",secret_key="sb_secret_test",
        )
        self.observation={
            "event_type":"change_set.nonproduction_merge.observed",
            "project_id":PID,"run_id":DELIVERY,
            "actor_ref":"nonproduction-release-observer",
            "payload":{
                "repository":REPO,"pr_number":"197",
                "candidate_commit":CANDIDATE,"head_sha":CANDIDATE,
                "head_ref":BRANCH,"base_ref":BASE,"merge_sha":MERGE,
                "observed_base_tip":MERGE,"production_main_sha":"d"*40,
                "merged":True,"vercel_state":"success",
                "merge_is_ancestor":True,"production_released":False,
                "production_release_completed":False,"environment":"preview",
                "postmerge_browser_snapshot_id":SNAP,
                "postmerge_preview_url":URL,"verifier_run_id":"123456",
            },
        }
        self.snapshot={
            "id":SNAP,"project_id":PID,"observed_stage":"verification",
            "gaps":[],"constraints":{"production_merge_authorized":False},
            "source_status":{"browser_visual_validation":"success",
                             "vercel_preview":"resolved"},
            "evidence":{
                "candidate_commit":MERGE,"target_repository":REPO,
                "preview":{"provider":"vercel","status":"browser_verified",
                           "url":URL,"browser_verifier_run_id":123456},
            },
        }
        self.github=Mock()
        self.github.get_branch_sha.side_effect=lambda branch: (
            MERGE if branch==BASE else "d"*40
        )
        self.github.compare_commits.return_value={
            "status":"behind","behind_by":3,"ahead_by":0,
        }

    def check(self):
        with patch.object(self.reader,"_one",return_value=self.snapshot):
            return self.reader._verified_nonproduction_integration(
                github=self.github,repository=REPO,project_id=PID,
                events=[self.observation],release_run_id=DELIVERY,
                candidate_sha=CANDIDATE,pr_number=197,
                head_ref=BRANCH,base_ref=BASE,merge_sha=MERGE,
            )

    def test_exact_postmerge_snapshot_and_ref(self):
        self.assertTrue(self.check())

    def test_cross_project_and_unverified_browser_rejected(self):
        for mutation in (
            lambda: self.snapshot.update(project_id=ROOT),
            lambda: self.snapshot["evidence"].update(candidate_commit=CANDIDATE),
            lambda: self.snapshot["evidence"]["preview"].update(status="browser_failed"),
            lambda: self.snapshot["evidence"]["preview"].update(browser_verifier_run_id=1),
            lambda: self.observation["payload"].update(production_released=True),
            lambda: self.observation["payload"].update(pr_number="198"),
            lambda: self.observation.update(run_id=ROOT),
            lambda: self.snapshot.update(gaps=[{"reason":"missing"}]),
        ):
            saved=(copy.deepcopy(self.snapshot),copy.deepcopy(self.observation))
            mutation()
            with self.subTest(change=repr(mutation)):
                self.assertFalse(self.check())
            self.snapshot,self.observation=saved

    def test_production_ref_equal_to_merge_denies_preview_only(self):
        self.github.get_branch_sha.side_effect=lambda branch:MERGE
        self.assertFalse(self.check())


if __name__=="__main__":
    unittest.main()
