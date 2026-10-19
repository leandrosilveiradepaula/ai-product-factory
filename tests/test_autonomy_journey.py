from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from ai_product_factory.autonomy_journey import STAGES, evaluate_journey, no_start_report
from ai_product_factory.autonomy_journey_reader import SupabaseJourneyReader, candidate_contains_work_units
from ai_product_factory.github_loop import CIState

ROOT=Path(__file__).resolve().parents[1]
PID="00000000-0000-0000-0000-000000000001"
ROOT_RUN="00000000-0000-0000-0000-000000000002"
WORK_RUN="00000000-0000-0000-0000-000000000003"
RELEASE_RUN="00000000-0000-0000-0000-000000000004"
CS="00000000-0000-0000-0000-000000000005"
UNIT="00000000-0000-0000-0000-000000000006"
SHA="a"*40
WORK_SHA="b"*40
MERGE_SHA="c"*40
REPO="example/workload"


def scenario(*,preview_required=False,merged=False,operations=False):
    def ev(kind,run_id=ROOT_RUN,**payload):
        return {"project_id":PID,"run_id":run_id,"event_type":kind,"payload":payload}
    events=[
        ev("product.stage.persisted",stage="discovery"),
        ev("product.stage.persisted",stage="specification"),
        ev("product.stage.persisted",stage="planning"),
        ev("change_set.materialized",change_set_id=CS),
        ev("change_set.work_unit.dispatched",work_unit_id=UNIT),
        ev("delivery.evidence.recorded",RELEASE_RUN,evidence_type="qa",status="passed"),
        ev("delivery.evidence.recorded",RELEASE_RUN,evidence_type="security",status="passed"),
        ev("quality_gate.passed",RELEASE_RUN,candidate_commit=SHA),
        ev("delivery.evidence.recorded",RELEASE_RUN,evidence_type="github_ci",status="passed"),
        ev("release.awaiting_human_merge",RELEASE_RUN,head_sha=SHA,pr=17),
    ]
    deployments=[]
    if preview_required:
        events.extend((
            ev("delivery.evidence.recorded",RELEASE_RUN,evidence_type="preview",status="passed"),
            ev("delivery.evidence.recorded",RELEASE_RUN,evidence_type="browser_evidence",status="passed"),
            ev("preview.browser_evidence_recorded",RELEASE_RUN,status="success"),
        ))
        deployments=[{"run_id":RELEASE_RUN,"environment":"preview","status":"success"}]
    else:
        events.append(ev("release.preview_not_required",RELEASE_RUN,head_sha=SHA,pr=17))
    release_reports=[]
    if merged:
        events.append(ev("release.human_merge_observed",RELEASE_RUN,head_sha=SHA,pr=17,
                         merge_sha=MERGE_SHA))
        release_reports.append({"candidate_commit":SHA,"status":"released","run_id":RELEASE_RUN})
    if operations:
        events.append(ev("delivery.evidence.recorded",RELEASE_RUN,evidence_type="operations",
                         status="passed"))
    return dict(
        project={"id":PID,"project_key":"fresh-journey","repository":REPO},
        root_run_id=ROOT_RUN,
        start_command={"command":"start","actor_id":"operator","result":{"run_id":ROOT_RUN}},
        runs=[
            {"id":ROOT_RUN,"status":"completed"},
            {"id":WORK_RUN,"status":"completed"},
            {"id":RELEASE_RUN,"status":"completed" if merged else "awaiting_release"},
        ],
        events=events,
        change_sets=[{"id":CS,"status":"ci_pending","candidate_commit":SHA}],
        work_units=[{"id":UNIT,"change_set_id":CS,"run_id":WORK_RUN,
                     "status":"completed","output_commit":WORK_SHA}],
        create_pr_receipts=[{"run_id":RELEASE_RUN,"operation":"create_pr",
                             "metadata":{"head_sha":SHA,"pr":17}}],
        deployments=deployments,
        release_reports=release_reports,
        github={"repository":REPO,"number":17,"head_sha":SHA,"head_repository":REPO,
                "base_ref":"main","merged":merged,
                "merge_commit_sha":MERGE_SHA if merged else None,
                "work_unit_commit_verified":True,"ci_state":CIState.SUCCESS},
        preview_required=preview_required,
    )


class JourneyEvidenceTests(unittest.TestCase):
    def test_no_new_start_never_fakes_execution(self):
        report=no_start_report("fresh")
        self.assertEqual(report.status,"not_started")
        self.assertTrue(all(x.status=="not_reached" for x in report.stages))
        self.assertEqual(report.as_json()["paid_calls"],0)
        self.assertFalse(report.as_json()["product_ready"])

    def test_full_evidence_until_human_merge_boundary(self):
        report=evaluate_journey(**scenario())
        self.assertEqual(report.status,"awaiting_human_merge")
        self.assertEqual(report.highest_verified,"awaiting_release")
        self.assertEqual(report.pr_number,17)
        self.assertEqual(report.stages[STAGES.index("human_release_observed")].status,"not_reached")

    def test_observed_full_release_requires_human_merge_and_ops_evidence(self):
        report=evaluate_journey(**scenario(preview_required=True,merged=True,operations=True))
        self.assertEqual(report.status,"observed_complete")
        self.assertEqual(report.highest_verified,"operations")
        self.assertTrue(all(s.status=="verified" for s in report.stages))
        self.assertFalse(report.as_json()["product_ready"])

    def test_later_success_cannot_skip_missing_early_stage(self):
        d=scenario()
        d["events"]=[e for e in d["events"] if e["payload"].get("stage")!="specification"]
        result=evaluate_journey(**d)
        self.assertEqual(result.highest_verified,"discovery")
        self.assertEqual(result.stages[STAGES.index("implementation")].status,"not_reached")

    def test_unrelated_project_or_old_run_cannot_supply_discovery(self):
        for field,value in (("run_id","old-run"),("project_id","old-project")):
            d=scenario()
            for event in d["events"]:
                if event["payload"].get("stage")=="discovery": event[field]=value
            with self.subTest(field=field):
                self.assertEqual(evaluate_journey(**d).highest_verified,"manual_start")

    def test_candidate_requires_real_pr_and_verified_commit(self):
        for mutation in ({"work_unit_commit_verified":False},{"head_sha":"f"*40},
                         {"head_repository":"other/repo"},{"base_ref":"another"}):
            d=scenario()
            d["github"].update(mutation)
            with self.subTest(mutation=mutation):
                r=evaluate_journey(**d)
                self.assertEqual(r.stages[STAGES.index("implementation")].status,"not_reached")
                self.assertNotEqual(r.status,"observed_complete")

    def test_existing_project_requires_its_actual_nonproduction_target(self):
        d=scenario()
        d["project"]["project_kind"]="existing"
        d["project"]["manifest"]={
            "delivery_target":{"mode":"open_pr_candidate",
                               "branch":"preview/stable-candidate"}
        }
        for event in d["events"]:
            if event["event_type"]=="product.stage.persisted":
                if event["payload"]["stage"]=="discovery":
                    event["payload"]["stage"]="reconciliation"
                elif event["payload"]["stage"]=="specification":
                    event["payload"]["stage"]="gap_analysis"
        d["github"]["base_ref"]="preview/stable-candidate"
        self.assertEqual(evaluate_journey(**d).highest_verified,"awaiting_release")
        d["github"]["base_ref"]="main"
        report=evaluate_journey(**d)
        self.assertIn("github_pr_sha_or_repository_drift",report.blockers)
        self.assertEqual(report.status,"blocked")
        d["project"]["manifest"]={"delivery_target":{"mode":"unknown",
                                                       "branch":"preview/stable-candidate"}}
        self.assertIn("project_delivery_target_unverified",
                      evaluate_journey(**d).blockers)

    def test_preview_n_a_needs_durable_exact_sha_receipt(self):
        d=scenario()
        d["events"]=[e for e in d["events"]
                     if e["event_type"]!="release.preview_not_required"]
        r=evaluate_journey(**d)
        self.assertEqual(r.highest_verified,"github_ci")
        self.assertEqual(r.stages[STAGES.index("preview")].status,"not_reached")

    def test_preview_required_needs_actual_deployment(self):
        d=scenario(preview_required=True)
        d["deployments"]=[]
        self.assertEqual(evaluate_journey(**d).highest_verified,"github_ci")

    def test_missing_preview_policy_is_blocked(self):
        d=scenario()
        d["preview_required"]=None
        self.assertIn("preview_applicability_not_verified",evaluate_journey(**d).blockers)

    def test_merge_without_release_observer_is_not_finished(self):
        d=scenario(merged=True,operations=True)
        d["events"]=[e for e in d["events"]
                     if e["event_type"]!="release.human_merge_observed"]
        result=evaluate_journey(**d)
        self.assertEqual(result.highest_verified,"awaiting_release")
        self.assertEqual(result.status,"blocked")
        self.assertIn("merged_candidate_without_verified_release",result.blockers)

    def test_failed_worker_is_exposed_as_blocker(self):
        d=scenario()
        d["runs"][1]["status"]="failed"
        r=evaluate_journey(**d)
        self.assertEqual(r.status,"blocked")
        self.assertIn("descendant_run_failed_or_blocked",r.blockers)

    def test_wrong_start_or_conflicting_pr_receipts_fail_closed(self):
        for mutate in ({"command":"resume"},{"actor_id":""},{"result":{"run_id":"old"}}):
            d=scenario()
            d["start_command"].update(mutate)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):
                evaluate_journey(**d)
        d=scenario()
        d["create_pr_receipts"].append({"run_id":RELEASE_RUN,"operation":"create_pr",
                                        "metadata":{"head_sha":SHA,"pr":88}})
        with self.assertRaisesRegex(ValueError,"conflicting"):
            evaluate_journey(**d)

    def test_report_redacts_raw_payloads(self):
        d=scenario()
        d["events"][0]["payload"]["user_secret"]="sk-proj-must-never-log"
        d["project"]["manifest"]={"password":"sensitive"}
        summary=json.dumps(evaluate_journey(**d).as_json())
        self.assertNotIn("sk-proj",summary)
        self.assertNotIn("sensitive",summary)
        self.assertIn('"writes": 0',summary)


class JourneyReaderContractTests(unittest.TestCase):
    def test_no_operator_start_does_not_contact_github_or_trigger_work(self):
        github=MagicMock()
        reader=SupabaseJourneyReader(url="https://example.supabase.co",
                                     secret_key="sb_secret_placeholder",
                                     github_factory=github)
        with patch.object(reader,"_one",return_value={
            "id":PID,"project_key":"fresh","repository":REPO,"is_active":True,
        }),patch.object(reader,"_get",return_value=[]) as get:
            result=reader.read(project_key="fresh",
                               since=datetime.now(timezone.utc)-timedelta(minutes=10))
        self.assertEqual(result.status,"not_started")
        get.assert_called_once()
        github.assert_not_called()

    def test_missing_server_credentials_blocks_without_fallback(self):
        with patch.dict("os.environ",{"SUPABASE_URL":"","SUPABASE_SECRET_KEY":"",
                                      "SUPABASE_SERVICE_ROLE_KEY":""},clear=False):
            with self.assertRaises(RuntimeError):
                SupabaseJourneyReader()

    def test_invalid_cutoff_or_project_is_rejected_before_network(self):
        reader=SupabaseJourneyReader(url="https://example.supabase.co",
                                     secret_key="sb_secret_placeholder")
        with patch.object(reader,"_one") as read:
            with self.assertRaises(ValueError):
                reader.read(project_key="Bad Name",since=datetime.now(timezone.utc))
            with self.assertRaises(ValueError):
                reader.read(project_key="good-name",
                            since=datetime.now(timezone.utc)+timedelta(days=1))
            read.assert_not_called()

    def test_all_postgrest_calls_are_get_and_partial_response_is_refused(self):
        reader=SupabaseJourneyReader(url="https://example.supabase.co",
                                     secret_key="sb_secret_placeholder")
        class Response:
            def __enter__(self): return self
            def __exit__(self,*a): return None
            def read(self,size): return b'[{},{}]'
        with patch("urllib.request.urlopen",return_value=Response()) as fetch:
            with self.assertRaisesRegex(RuntimeError,"incomplete"):
                reader._get("factory_projects?select=id",limit=2)
            request=fetch.call_args.args[0]
            self.assertEqual(request.get_method(),"GET")
            self.assertNotIn("sb_secret",request.full_url)

    def test_read_only_mode_uses_trusted_oidc_runner_without_worker_wake(self):
        import re
        workflow=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
        broker=(ROOT/"supabase/functions/factory-runtime-control-plane/index.ts").read_text()
        self.assertFalse((ROOT/".github/workflows/autonomy-journey-readonly.yml").exists())
        self.assertIn("run_journey_audit:",workflow)
        self.assertIn("journey-readonly:",workflow)
        self.assertIn("inputs.run_journey_audit != true",workflow)
        self.assertIn(
            "if: \${{ github.event_name == 'workflow_dispatch' && inputs.run_journey_audit == true }}",
            workflow,
        )
        self.assertIn("control-plane-oidc",workflow)
        self.assertIn("persist-credentials: false",workflow)
        self.assertIn("audit_autonomy_journey.py",workflow)
        self.assertIn("upload-artifact@",workflow)
        self.assertNotIn("autonomy-journey-readonly.yml",broker)
        self.assertIn(".github/workflows/autonomous-runner.yml@refs/heads/main",broker)
        audit=workflow.split("\n  journey-readonly:\n",1)[1]
        for forbidden in (
            "FACTORY_PRIMARY_MODEL_ENABLED","--mode product","--mode dispatch",
            "--mode direct","--mode change-set-integration","--mode preview",
            "merge_pull_request",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden,audit)
        # Every pre-existing worker or alert transitively needs the probe,
        # which is explicitly skipped for read-only audit dispatches.
        pieces=re.findall(
            r"(?ms)^  ([a-z][a-z0-9-]+):\n(.*?)(?=^  [a-z][a-z0-9-]+:\n|\Z)",
            workflow.split("\njobs:\n",1)[1],
        )
        jobs=dict(pieces)
        self.assertIn("schedule-probe",jobs)
        self.assertIn("journey-readonly",jobs)
        for name,body in jobs.items():
            if name in {"schedule-probe","journey-readonly"}:
                continue
            seen=set()
            def depends_on_probe(current):
                if current=="schedule-probe":
                    return True
                if current in seen:
                    return False
                seen.add(current)
                match=re.search(r"(?m)^    needs:\s*(.*)$",jobs[current])
                self.assertIsNotNone(match,f"{current} has no needs")
                dependencies=match.group(1).strip().strip("[]").split(",")
                return any(
                    d.strip() in jobs and depends_on_probe(d.strip())
                    for d in dependencies
                )
            with self.subTest(job=name):
                self.assertTrue(depends_on_probe(name),name)




class RealControlPlaneCompatibilityTests(unittest.TestCase):
    """Regression fixtures derived from the actual October 19 audit schemas.

    Existing-project stages are reconciliation/gap_analysis/planning; release
    gate events have project_id=NULL, and console release observation omits PR.
    These tests prove the audit can recognize those formats without borrowing
    another run's evidence or faking a human merge.
    """

    def test_existing_project_reconciliation_gap_analysis_are_real_stages(self):
        d=scenario()
        d["project"]["project_kind"]="existing"
        d["project"]["manifest"]={
            "delivery_target":{"mode":"open_pr_candidate",
                               "branch":"preview/proven-candidate"}
        }
        d["github"]["base_ref"]="preview/proven-candidate"
        for e in d["events"]:
            if e["event_type"]=="product.stage.persisted":
                if e["payload"]["stage"]=="discovery":
                    e["payload"]["stage"]="reconciliation"
                elif e["payload"]["stage"]=="specification":
                    e["payload"]["stage"]="gap_analysis"
        verified=evaluate_journey(**d)
        self.assertEqual(verified.highest_verified,"awaiting_release")
        self.assertEqual(verified.status,"awaiting_human_merge")
        # Do not substitute a greenfield event for a missing CRM reconciliation.
        d["events"][0]["payload"]["stage"]="discovery"
        self.assertEqual(evaluate_journey(**d).highest_verified,"manual_start")
        d["events"][0]["payload"]["stage"]="reconciliation"
        d["events"][1]["payload"]["stage"]="specification"
        self.assertEqual(evaluate_journey(**d).highest_verified,"discovery")

    def test_null_project_release_receipts_require_same_run_pr_and_sha(self):
        d=scenario()
        for e in d["events"]:
            if e["event_type"] in (
                "release.preview_not_required","release.awaiting_human_merge"
            ):
                e["project_id"]=None
        report=evaluate_journey(**d)
        self.assertEqual(report.highest_verified,"awaiting_release")
        for field,value in (
            ("run_id",WORK_RUN),
            ("project_id","another-project"),
        ):
            invalid=scenario()
            for e in invalid["events"]:
                if e["event_type"]=="release.awaiting_human_merge":
                    e["project_id"]=None
                    e[field]=value
            with self.subTest(field=field):
                r=evaluate_journey(**invalid)
                self.assertEqual(r.highest_verified,"preview")
                self.assertNotEqual(r.status,"awaiting_human_merge")
        # Wrong candidate must not pass even when project_id is intentionally NULL.
        invalid=scenario()
        for e in invalid["events"]:
            if e["event_type"]=="release.preview_not_required":
                e["project_id"]=None
                e["payload"]["head_sha"]="f"*40
        self.assertEqual(evaluate_journey(**invalid).highest_verified,"github_ci")

    def test_console_merge_requires_matching_second_audit_and_report(self):
        d=scenario(merged=True,operations=True)
        d["events"]=[
            e for e in d["events"]
            if e["event_type"]!="release.human_merge_observed"
        ]
        observer={
            "project_id":PID,"run_id":RELEASE_RUN,
            "event_type":"release.human_merge_observed",
            "payload":{"source":"console_human_merge",
                       "candidate_commit":SHA,"merge_sha":MERGE_SHA},
        }
        receipt={
            "project_id":PID,"run_id":RELEASE_RUN,
            "event_type":"human_release.console_merge_succeeded",
            "payload":{"repository":REPO,"pr_number":17,
                       "candidate_commit":SHA,"merge_sha":MERGE_SHA},
        }
        d["events"].extend((observer,receipt))
        self.assertEqual(evaluate_journey(**d).status,"observed_complete")
        d["events"].remove(receipt)
        report=evaluate_journey(**d)
        self.assertEqual(report.status,"blocked")
        self.assertEqual(report.highest_verified,"awaiting_release")
        self.assertIn("merged_candidate_without_verified_release",report.blockers)
        d["events"].append(dict(receipt,payload=dict(receipt["payload"],pr_number=99)))
        self.assertEqual(evaluate_journey(**d).highest_verified,"awaiting_release")
        d["events"][-1]["payload"]["pr_number"]=17
        d["events"][-1]["run_id"]=WORK_RUN
        self.assertEqual(evaluate_journey(**d).highest_verified,"awaiting_release")

    def test_delivery_evidence_cannot_be_borrowed_from_sibling_run(self):
        for event_type in (
            "delivery.evidence.recorded",
            "quality_gate.passed",
            "release.awaiting_human_merge",
        ):
            d=scenario()
            event=next(e for e in d["events"] if e["event_type"]==event_type
                       and (event_type!="delivery.evidence.recorded"
                            or e["payload"]["evidence_type"]=="security"))
            event["run_id"]=WORK_RUN
            with self.subTest(event_type=event_type):
                report=evaluate_journey(**d)
                self.assertNotEqual(report.highest_verified,"awaiting_release")
                self.assertNotEqual(report.status,"awaiting_human_merge")

    def test_future_evidence_does_not_implicitly_complete_missing_middle(self):
        d=scenario()
        d["events"]=[
            e for e in d["events"]
            if e["event_type"]!="release.preview_not_required"
        ]
        report=evaluate_journey(**d)
        self.assertEqual(report.highest_verified,"github_ci")
        self.assertEqual(report.status,"in_progress")

    def test_candidate_work_unit_commits_must_be_ancestors_not_just_existing(self):
        github=MagicMock()
        github.commit_exists.return_value=True
        github.compare_commits.return_value={
            "status":"ahead","ahead_by":2,"behind_by":0,"files":[]
        }
        self.assertTrue(candidate_contains_work_units(github,SHA,{WORK_SHA}))
        github.compare_commits.assert_called_once_with(WORK_SHA,SHA)
        for invalid in (
            {"status":"diverged","ahead_by":2,"behind_by":1},
            {"status":"behind","ahead_by":0,"behind_by":2},
            {"status":"ahead","ahead_by":2,"behind_by":1},
            {"status":"ahead","ahead_by":True,"behind_by":0},
        ):
            github.compare_commits.return_value=invalid
            with self.subTest(result=invalid):
                self.assertFalse(candidate_contains_work_units(github,SHA,{WORK_SHA}))
        github.commit_exists.return_value=False
        self.assertFalse(candidate_contains_work_units(github,SHA,{WORK_SHA}))
        github.commit_exists.return_value=True
        github.compare_commits.reset_mock()
        self.assertTrue(candidate_contains_work_units(github,SHA,{SHA}))
        github.compare_commits.assert_not_called()
        for commits in (set(),{"bad"}, {str(i).zfill(40) for i in range(31)}):
            with self.subTest(size=len(commits)):
                with self.assertRaises(ValueError):
                    candidate_contains_work_units(github,SHA,commits)


    def test_reader_rejects_untrusted_null_project_event_without_github(self):
        reader=SupabaseJourneyReader(
            url="https://example.supabase.co",secret_key="sb_secret_placeholder",
            github_factory=MagicMock(),
        )
        task_id="00000000-0000-0000-0000-000000000007"
        started_at="2026-10-19T21:00:00+00:00"
        def one(table,query):
            if table=="factory_projects":
                return {"id":PID,"project_key":"fresh-journey",
                        "repository":REPO,"is_active":True,"project_kind":"existing"}
            if table=="factory_runs":
                return {"id":ROOT_RUN,"task_id":task_id,"status":"completed"}
            if table=="factory_tasks":
                return {"id":task_id,"project_id":PID,"parent_task_id":None,
                        "created_at":started_at,"status":"completed"}
            raise AssertionError(table)
        def get(path,*,limit):
            if path.startswith("factory_project_execution_commands?"):
                return [{"project_id":PID,"command":"start","actor_id":"operator",
                         "result":{"run_id":ROOT_RUN},"created_at":started_at}]
            if path.startswith("factory_tasks?"):
                return [{"id":task_id,"project_id":PID,"parent_task_id":None,
                         "created_at":started_at}]
            if path.startswith(("factory_change_sets?","factory_audit_events?",
                                "factory_release_reports?")):
                return []
            raise AssertionError(path)
        def many(table,*,cols,fk,ids,extra="",limit=301):
            if table=="factory_runs":
                return [{"id":ROOT_RUN,"task_id":task_id,"status":"completed"}]
            if table=="factory_audit_events":
                return [{"id":1,"run_id":ROOT_RUN,"project_id":None,
                         "event_type":"run.status.updated","payload":{}}]
            return []
        with patch.object(reader,"_one",side_effect=one),\
             patch.object(reader,"_get",side_effect=get),\
             patch.object(reader,"_many_ids",side_effect=many),\
             self.assertRaisesRegex(RuntimeError,"untrusted globally scoped"):
            reader.read(project_key="fresh-journey",
                        since=datetime(2026,10,19,20,0,tzinfo=timezone.utc))
        reader.github_factory.assert_not_called()

    def test_global_release_reader_rejects_other_project_and_unlisted_events(self):
        reader=SupabaseJourneyReader(
            url="https://example.supabase.co",secret_key="sb_secret_placeholder",
        )
        mocked={
            "id":1,"run_id":RELEASE_RUN,"project_id":None,
            "event_type":"release.awaiting_human_merge","payload":{"pr":17,"head_sha":SHA},
        }
        with patch.object(reader,"_get",return_value=[mocked]) as call:
            rows=reader._many_ids(
                "factory_audit_events",
                cols="id,project_id,task_id,run_id,event_type,payload,created_at",
                fk="run_id",ids={RELEASE_RUN},
                extra=("project_id=is.null&event_type=in.("
                       "release.awaiting_human_merge,release.preview_not_required,"
                       "release.human_merge_observed)"),
                limit=201,
            )
        self.assertEqual(rows,[mocked])
        self.assertIn("project_id=is.null",call.call_args.args[0])
        self.assertIn("run_id=in.(",call.call_args.args[0])


if __name__=="__main__":
    unittest.main()
