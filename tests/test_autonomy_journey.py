from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from ai_product_factory.autonomy_journey import STAGES, evaluate_journey, no_start_report
from ai_product_factory.autonomy_journey_reader import SupabaseJourneyReader
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

    def test_workflow_is_opt_in_no_model_or_auto_merge(self):
        workflow=(ROOT/".github/workflows/autonomy-journey-readonly.yml").read_text()
        self.assertIn("workflow_dispatch:",workflow)
        self.assertNotIn("\n  schedule:",workflow)
        self.assertIn("control-plane-oidc",workflow)
        self.assertIn("persist-credentials: false",workflow)
        self.assertIn("audit_autonomy_journey.py",workflow)
        self.assertIn("upload-artifact@",workflow)
        self.assertNotIn("FACTORY_PRIMARY_MODEL_ENABLED",workflow)
        self.assertNotIn("merge_pull_request",workflow)
        self.assertNotIn("--mode product",workflow)


if __name__=="__main__":
    unittest.main()
