"""Real Factory October E2E: authenticated Console Start, copied Work Unit bytes,
atomic candidate repair, CI, specialist review and observed human merge.

All adapters are read-only fakes; no model, production database or GitHub writes.
"""
from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ai_product_factory.autonomy_journey import evaluate_journey
from ai_product_factory.autonomy_journey_reader import SupabaseJourneyReader
from ai_product_factory.github_loop import CIState
from ai_product_factory.journey_candidate_provenance import (
    validate_reconciliation_receipt, verify_copied_work_units,
)

PID="00000000-0000-4000-8000-000000000001"
ROOT="00000000-0000-4000-8000-000000000002"
ROOT_TASK="00000000-0000-4000-8000-000000000003"
WORK="00000000-0000-4000-8000-000000000004"
WORK_TASK="00000000-0000-4000-8000-000000000005"
REL="00000000-0000-4000-8000-000000000006"
REL_TASK="00000000-0000-4000-8000-000000000007"
CS="00000000-0000-4000-8000-000000000008"
UNIT="00000000-0000-4000-8000-000000000009"
REQ="00000000-0000-4000-8000-000000000010"
ORIG="a"*40
FINAL="b"*40
MERGE="c"*40
WORK_SHA="d"*40
REPO="owner/factory-demo"
PATH="scripts/audit_autonomy_journey.py"
BRANCH="factory/change-set-demo"
WHEN="2026-10-20T03:07:16.859209+00:00"
NOW=datetime(2026,10,20,3,0,tzinfo=timezone.utc)


def receipt():
    return {
        "old_sha":ORIG, "new_sha":FINAL, "previous_commit":ORIG,
        "candidate_commit":FINAL, "pr_number":"17",
        "repository":REPO, "branch":BRANCH, "change_set_id":CS,
        "compare_status":"ahead", "ahead_by":"1",
        "changed_files":[PATH],
    }


def fixtures():
    start={
        "command":"console_continuation","actor_id":"factory-console",
        "request_id":REQ,"result":{"run_id":ROOT},
    }
    meta={"source":"factory-console","continuation_request_id":REQ}
    runs=[
        {"id":ROOT,"task_id":ROOT_TASK,"status":"completed","metadata":meta},
        {"id":WORK,"task_id":WORK_TASK,"status":"completed"},
        {"id":REL,"task_id":REL_TASK,"status":"merged"},
    ]
    def event(kind,run_id=ROOT,*,project_id=PID,task_id=ROOT_TASK,
              actor_type="system",actor_ref="worker",**payload):
        return {
            "id":str(len(events)+1).zfill(36),
            "project_id":project_id,"task_id":task_id,"run_id":run_id,
            "event_type":kind,"actor_type":actor_type,"actor_ref":actor_ref,
            "created_at":WHEN, "payload":payload,
        }
    events=[]
    events.append(event("project.continuation.requested",actor_type="human",
                       actor_ref="factory-console",request_id=REQ))
    events.append(event("project.reconciliation.enqueued",actor_ref="factory-console",
                       request_id=REQ,task_id=ROOT_TASK))
    # The RPC persists task_id in both the audit row AND the durable payload.
    # They must match; the reader correctly rejects a missing payload field.
    events[1]["payload"]["task_id"]=ROOT_TASK
    events.extend([
        event("product.stage.persisted",stage="reconciliation"),
        event("product.stage.persisted",stage="gap_analysis"),
        event("product.stage.persisted",stage="planning"),
        event("change_set.materialized",change_set_id=CS),
        event("change_set.work_unit.dispatched",WORK,task_id=WORK_TASK,
              work_unit_id=UNIT),
    ])
    for kind in ("qa","security","github_ci","operations"):
        events.append(event("delivery.evidence.recorded",REL,task_id=REL_TASK,
                            evidence_type=kind,status="passed",evidence_ref=FINAL))
    events.extend([
        event("quality_gate.passed",REL,project_id=None,task_id=REL_TASK,
              candidate_commit=FINAL),
        event("release.policy.decided",REL,task_id=REL_TASK,
              outcome="ready_for_human_release"),
        event("run.status.updated",REL,task_id=REL_TASK,
              status="awaiting_release",candidate_commit=FINAL),
        event("release.preview_not_required",REL,task_id=REL_TASK,project_id=None,
              head_sha=FINAL,pr=17),
        event("release.human_merge_observed",REL,task_id=REL_TASK,project_id=None,
              head_sha=FINAL,pr=17,merge_sha=MERGE),
        event("project.state.reconciled_after_release",REL,task_id=REL_TASK,
              merge_sha=MERGE,lifecycle_stage="operations"),
    ])
    for i,e in enumerate(events):
        e["id"]=f"00000000-0000-4000-8000-{i+100:012d}"
    project={"id":PID,"project_key":"factory-demo","repository":REPO,
             "project_kind":"platform","is_active":True,"manifest":{}}
    changes=[{"id":CS,"root_task_id":ROOT_TASK,"project_id":PID,"status":"completed",
              "source_commit":"e"*40,"candidate_commit":FINAL,
              "integration_branch":BRANCH,"created_at":WHEN,
              "metadata":{"integration_release_request":
                          {"candidate_commit":FINAL,"branch":BRANCH}}}]
    unit={"id":UNIT,"change_set_id":CS,"task_id":WORK_TASK,
          "status":"integrated","run_id":WORK,"output_commit":WORK_SHA,
          "changed_files":[PATH],"created_at":WHEN}
    original={"id":"00000000-0000-4000-8000-000000000020","run_id":REL,
              "operation":"create_pr",
              "metadata":{"head_sha":ORIG,"pr":17,"change_set_id":CS}}
    reconcile={"id":"00000000-0000-4000-8000-000000000021","run_id":REL,
               "operation":"reconcile_pr_candidate","metadata":receipt()}
    gh={"repository":REPO,"number":17,"head_sha":FINAL,"head_repository":REPO,
        "base_ref":"main","merged":True,"merge_commit_sha":MERGE,
        "ci_state":CIState.SUCCESS,"work_unit_commit_verified":True,
        "candidate_reconciliation_verified":True}
    report={"id":"00000000-0000-4000-8000-000000000022",
            "project_id":PID,"run_id":REL,"candidate_commit":FINAL,
            "status":"released","created_at":WHEN}
    evaluate=dict(
        project=project,root_run_id=ROOT,start_command=start,runs=runs,
        events=events,change_sets=changes,work_units=[unit],
        create_pr_receipts=[original],candidate_reconciliations=[reconcile],
        deployments=[],release_reports=[report],github=gh,
        preview_required=False,
    )
    tasks=[
        {"id":ROOT_TASK,"project_id":PID,"parent_task_id":None,
         "status":"completed","created_at":WHEN},
        {"id":WORK_TASK,"project_id":PID,"parent_task_id":ROOT_TASK,
         "status":"completed","created_at":WHEN},
        {"id":REL_TASK,"project_id":PID,"parent_task_id":ROOT_TASK,
         "status":"merged","created_at":WHEN},
    ]
    return evaluate,tasks


class FakeGitHub:
    def __init__(self):
        self.same=True
        self.ff=True
        self.actual_paths=[PATH]
        self.pr=SimpleNamespace(
            number=17,head_sha=FINAL,head_repository=REPO,
            base_ref="main",merged=True,merge_commit_sha=MERGE,
            head_ref=BRANCH,
        )
        self.reads=[]

    def compare_commits(self,old,new):
        if self.ff and old==ORIG and new==FINAL:
            return {"status":"ahead","ahead_by":1,"behind_by":0,
                    "files":self.actual_paths}
        return {"status":"diverged","ahead_by":1,"behind_by":1,
                "files":self.actual_paths}

    def commit_exists(self,sha):
        return sha==WORK_SHA

    def get_file_text(self,path,*,ref):
        self.reads.append((path,ref))
        if path!=PATH or ref not in (WORK_SHA,ORIG):
            raise RuntimeError("unknown scoped code")
        return "def real_implementation(): return 42" if self.same or ref==WORK_SHA else "different"

    def get_pull_request(self,number):
        if number!=17: raise RuntimeError("incorrect PR")
        return self.pr

    def get_pull_request_files(self,number):
        return (PATH,)

    def get_ci_state(self,number):
        return CIState.SUCCESS


class ReleaseLineageContracts(unittest.TestCase):
    def test_complete_real_continuation_is_observed_not_assumed(self):
        d,_=fixtures()
        r=evaluate_journey(**d)
        self.assertEqual(r.status,"observed_complete")
        self.assertEqual(r.highest_verified,"operations")
        self.assertEqual(len(r.stages),12)
        self.assertTrue(all(x.status=="verified" for x in r.stages))
        payload=r.as_json()
        self.assertFalse(payload["product_ready"])
        self.assertEqual(payload["paid_calls"],0)
        self.assertEqual(payload["writes"],0)

    def test_absent_or_forged_operator_continuation_fails_closed(self):
        d,_=fixtures()
        for modification in ("no_human","no_queue","bad_actor",
                             "unrelated_project","unrelated_run","wrong_request"):
            with self.subTest(modification=modification):
                x=copy.deepcopy(d)
                if modification=="no_human": x["events"].pop(0)
                if modification=="no_queue": x["events"].pop(1)
                if modification=="bad_actor": x["events"][0]["actor_type"]="system"
                if modification=="unrelated_project": x["events"][0]["project_id"]="bad"
                if modification=="unrelated_run": x["events"][0]["run_id"]="bad"
                if modification=="wrong_request":
                    x["runs"][0]["metadata"]["continuation_request_id"]="bad"
                with self.assertRaises(ValueError):
                    evaluate_journey(**x)

    def test_candidate_repair_requires_identity_and_exact_verification(self):
        d,_=fixtures()
        for mutation in ("wrong_pr","wrong_run","wrong_repo",
                         "wrong_source","no_github_evidence","unreconciled"):
            x=copy.deepcopy(d)
            if mutation=="wrong_pr":
                x["candidate_reconciliations"][0]["metadata"]["pr_number"]="19"
            if mutation=="wrong_run":
                x["candidate_reconciliations"][0]["run_id"]="wrong-run"
            if mutation=="wrong_repo":
                x["candidate_reconciliations"][0]["metadata"]["repository"]="evil/other"
            if mutation=="wrong_source":
                x["candidate_reconciliations"][0]["metadata"]["previous_commit"]="f"*40
            if mutation=="no_github_evidence":
                x["github"]["candidate_reconciliation_verified"]=False
            if mutation=="unreconciled":
                x["candidate_reconciliations"]=[]
            with self.subTest(mutation=mutation):
                if mutation=="unreconciled":
                    r=evaluate_journey(**x)
                    self.assertEqual(r.status,"blocked")
                    self.assertIn("candidate_receipt_drift",r.blockers)
                else:
                    with self.assertRaises(ValueError):
                        evaluate_journey(**x)

    def test_missing_human_release_gate_or_operations_is_never_complete(self):
        d,_=fixtures()
        for stage in ("release.policy.decided","run.status.updated",
                      "release.human_merge_observed",
                      "project.state.reconciled_after_release"):
            x=copy.deepcopy(d)
            x["events"]=[e for e in x["events"] if e["event_type"]!=stage]
            with self.subTest(stage=stage):
                r=evaluate_journey(**x)
                self.assertNotEqual(r.status,"observed_complete")
                self.assertNotEqual(r.highest_verified,"operations")

    def test_integrated_work_unit_bytes_must_match_first_candidate(self):
        gh=FakeGitHub()
        good=[fixtures()[0]["work_units"][0]]
        self.assertTrue(verify_copied_work_units(
            gh,original_candidate=ORIG,final_candidate=FINAL,units=good))
        self.assertEqual(gh.reads,[(PATH,WORK_SHA),(PATH,ORIG)])
        gh.same=False
        self.assertFalse(verify_copied_work_units(
            gh,original_candidate=ORIG,final_candidate=FINAL,units=good))
        gh.same=True
        gh.ff=False
        self.assertFalse(verify_copied_work_units(
            gh,original_candidate=ORIG,final_candidate=FINAL,units=good))
        gh.ff=True
        for invalid in ([{**good[0],"changed_files":["../secret"]}],
                        [{**good[0],"output_commit":"e"*40}],
                        [{**good[0],"changed_files":[]}]):
            self.assertFalse(verify_copied_work_units(
                gh,original_candidate=ORIG,final_candidate=FINAL,units=invalid))

    def test_atomic_reconciliation_receipt_must_match_actual_ancestry_and_paths(self):
        gh=FakeGitHub()
        self.assertTrue(validate_reconciliation_receipt(
            gh,receipt=receipt(),old_sha=ORIG,candidate_sha=FINAL,
            pr_number=17,repository=REPO,change_set_id=CS,branch=BRANCH))
        gh.actual_paths=["src/unrelated.py"]
        self.assertFalse(validate_reconciliation_receipt(
            gh,receipt=receipt(),old_sha=ORIG,candidate_sha=FINAL,
            pr_number=17,repository=REPO,change_set_id=CS,branch=BRANCH))
        gh.actual_paths=[PATH]
        for key,value in (("branch","main"),("ahead_by","0"),
                          ("repository","evil/repo"),("changed_files",["secrets.txt"])):
            with self.subTest(key=key):
                entry=receipt()
                entry[key]=value
                self.assertFalse(validate_reconciliation_receipt(
                    gh,receipt=entry,old_sha=ORIG,candidate_sha=FINAL,
                    pr_number=17,repository=REPO,change_set_id=CS,branch=BRANCH))


class RealReaderFromAuthorizedConsoleFixtures(unittest.TestCase):
    def make_reader(self,*,authorized=True,correct_content=True):
        d,tasks=fixtures()
        gh=FakeGitHub()
        gh.same=correct_content
        root_run={
            **d["runs"][0], "candidate_commit":None,"created_at":WHEN,
        }
        runs=[
            {**r, "created_at":WHEN, "candidate_commit":None,
             "source_commit":None,"branch_name":None}
            for r in d["runs"]
        ]
        events=d["events"]
        def fetch(path,*,limit):
            if path.startswith("factory_projects?"):
                return [d["project"]]
            if path.startswith("factory_project_execution_commands?"):
                return []
            if path.startswith("factory_audit_events?") and "event_type=in.(project.continuation.requested," in path:
                return events[:2] if authorized else [events[0]]
            if path.startswith("factory_runs?") and "id=eq." in path:
                return [root_run]
            if path.startswith("factory_tasks?") and "id=eq." in path:
                return [tasks[0]]
            if path.startswith("factory_tasks?"):
                return tasks
            if path.startswith("factory_runs?"):
                # Mimic PostgREST's exact task_id=in.(...) filtering.
                # The reader correctly rejects any row from another lineage.
                if "task_id=in.(" in path:
                    task_ids=set(path.split("task_id=in.(",1)[1].split(")",1)[0].split(","))
                    return [row for row in runs if row["task_id"] in task_ids]
                return runs
            if path.startswith("factory_change_sets?"):
                return d["change_sets"]
            if path.startswith("factory_change_set_work_units?"):
                return d["work_units"]
            if path.startswith("factory_audit_events?") and "project_id=is.null" in path:
                return [e for e in events if e.get("project_id") is None]
            if path.startswith("factory_audit_events?"):
                return [e for e in events if e.get("project_id")==PID]
            if path.startswith("factory_tool_usage?") and "operation=eq.create_pr" in path:
                return d["create_pr_receipts"]
            if path.startswith("factory_tool_usage?") and "operation=eq.reconcile_pr_candidate" in path:
                return d["candidate_reconciliations"]
            if path.startswith("factory_deployments?"):
                return []
            if path.startswith("factory_release_reports?"):
                return d["release_reports"]
            raise AssertionError("unrecognized read surface: "+path)
        reader=SupabaseJourneyReader(url="https://example.supabase.co",
                                     secret_key="sb_secret_test",
                                     github_factory=lambda *,repository: gh)
        reader._get=Mock(side_effect=fetch)
        return reader,gh

    def test_real_reader_reconstructs_authorized_continuation_plus_copied_code(self):
        reader,gh=self.make_reader()
        with patch("ai_product_factory.autonomy_journey_reader.evaluate_preview_applicability",
                   return_value=SimpleNamespace(required=False)):
            result=reader.read(project_key="factory-demo",since=NOW,run_id=ROOT)
        self.assertEqual(result.status,"observed_complete")
        self.assertEqual(result.pr_number,17)
        self.assertEqual(result.candidate_sha,FINAL)
        self.assertTrue(gh.reads)
        self.assertFalse(any("password" in str(x) for x in result.as_json().values()))

    def test_unpaired_console_queue_event_is_not_a_human_start(self):
        reader,gh=self.make_reader(authorized=False)
        with self.assertRaisesRegex(RuntimeError,"no verified explicit Start"):
            reader.read(project_key="factory-demo",since=NOW,run_id=ROOT)
        self.assertFalse(gh.reads)

    def test_changed_work_unit_source_cannot_be_counted_as_implementation(self):
        reader,gh=self.make_reader(correct_content=False)
        with patch("ai_product_factory.autonomy_journey_reader.evaluate_preview_applicability",
                   return_value=SimpleNamespace(required=False)):
            result=reader.read(project_key="factory-demo",since=NOW,run_id=ROOT)
        self.assertNotEqual(result.status,"observed_complete")
        self.assertEqual(result.stages[5].status,"not_reached")


if __name__=="__main__":
    unittest.main()
