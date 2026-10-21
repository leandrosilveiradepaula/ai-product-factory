"""Exact-PR advisory gate evidence, validating genuine Service Desk blockers.

The sources are simulated GET responses, not claimed remote success. This
contract ensures an external QA success can NEVER replace target-native CI,
Preview/browser verification, Control Plane policy, or human production merge.
"""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime

from ai_product_factory.candidate_gate_audit import (
    CandidateGateEvidenceError,observe_candidate_gates,
)

PROJECT="infodive-service-desk"
REPO="leandrosilveiradepaula/infodive-service-desk"
PID="70515123-ecbb-4f4b-a38f-75c54250af56"
SHA="c7b061c6f18961bd1fdfea51f59e2985bbe8247a"
PR=5
BRANCH="quality/tenant-rbac-constraints"


def fixtures(preview=None,with_block=True):
    cp={
        "project":[{
            "id":PID,"project_key":PROJECT,"repository":REPO,
            "is_active":True,"project_kind":"greenfield",
            "lifecycle_stage":"implementation","manifest":{"preview":preview}
        }],
        "control":[{"project_id":PID,"state":"running","generation":1}],
        "blocked":[{"id":"effc36be-212c-42f2-928b-97381b6d8a28",
                    "project_id":PID,"status":"blocked",
                    "root_task_id":"11111111-1111-4111-8111-111111111111",
                    "release_run_id":"22222222-2222-4222-8222-222222222222"}] if with_block else [],
    }
    gh={
        "repo":{"full_name":REPO,"default_branch":"main"},
        "pr":{"number":PR,"state":"open","merged":False,
              "draft":True,"changed_files":2,
              "head":{"sha":SHA,"ref":BRANCH,"repo":{"full_name":REPO}},
              "base":{"ref":"main","repo":{"full_name":REPO}}},
        "files":[{"filename":"src/web/main.tsx"},{"filename":"supabase/migrations/002.sql"}],
        "checks":{"total_count":2,"check_runs":[
            {"id":10,"name":"runner-preflight","head_sha":SHA,
             "status":"completed","conclusion":"failure","app":{"slug":"github-actions"}},
            {"id":11,"name":"verify","head_sha":SHA,
             "status":"completed","conclusion":"skipped","app":{"slug":"github-actions"}},
        ]},
        "runs":{"total_count":2,"workflow_runs":[
            {"id":55,"name":"Service Desk verification","head_sha":SHA,
             "event":"pull_request","status":"completed","conclusion":"failure",
             "head_branch":BRANCH,"path":".github/workflows/service-desk-ci.yml",
             "repository":{"full_name":REPO}},
            {"id":54,"name":"Service Desk verification","head_sha":SHA,
             "event":"push","status":"completed","conclusion":"failure",
             "head_branch":BRANCH,"path":".github/workflows/service-desk-ci.yml",
             "repository":{"full_name":REPO}},
        ]},
    }
    return cp,gh


def observer(cp,gh, *, key=PROJECT,number=PR,sha=SHA):
    paths=[]
    def cp_get(path):
        paths.append(("supabase","GET",path))
        if path.startswith("factory_projects?"):return cp["project"]
        if path.startswith("factory_project_execution_controls?"):return cp["control"]
        if path.startswith("factory_change_sets?"):return cp["blocked"]
        raise AssertionError(path)
    def github_get(path):
        paths.append(("github","GET",path))
        prefix="/repos/"+REPO
        lookup={
            prefix:gh["repo"],
            prefix+"/pulls/"+str(number):gh["pr"],
            prefix+"/pulls/"+str(number)+"/files?per_page=100":gh["files"],
            prefix+"/commits/"+sha+"/check-runs?per_page=100":gh["checks"],
            prefix+"/actions/runs?head_sha="+sha+"&per_page=100":gh["runs"],
        }
        if path not in lookup:raise AssertionError("Unexpected GitHub GET "+path)
        return lookup[path]
    report=observe_candidate_gates(
        project_key=key,pr_number=number,candidate_sha=sha,
        cp_get=cp_get,github_get=github_get,
    )
    return report,paths


def mark_ci_green(gh):
    for check in gh["checks"]["check_runs"]:
        check["conclusion"]="success"
    for run in gh["runs"]["workflow_runs"]:
        run["conclusion"]="success"


class CandidateGateTests(unittest.TestCase):
    def test_real_service_desk_candidate_is_still_release_blocked(self):
        cp,gh=fixtures()
        report,calls=observer(cp,gh)
        self.assertEqual(report["native_ci"]["status"],"blocked")
        self.assertEqual(report["native_ci"]["latest_pr_workflow_state"],"failure")
        self.assertEqual(report["native_ci"]["failed_checks"],1)
        self.assertEqual(report["native_ci"]["skipped_checks"],1)
        self.assertFalse(report["native_ci"]["external_qa_substituted"])
        self.assertEqual(report["preview"]["status"],"policy_missing")
        self.assertEqual(report["historical_blocked_change_sets"],1)
        self.assertIn("native_ci_not_verified",report["reason_codes"])
        self.assertIn("preview_policy_unconfigured",report["reason_codes"])
        self.assertIn("historical_blocked_change_set_review",report["reason_codes"])
        self.assertIn("human_production_merge_pending",report["reason_codes"])
        self.assertTrue(report["pr_draft"])
        self.assertFalse(report["ready_for_production"])
        self.assertFalse(report["product_ready"])
        self.assertEqual((report["writes"],report["paid_calls"]),(0,0))
        self.assertTrue(all(method=="GET" for _,method,_ in calls))
        self.assertTrue(any("&project_id=eq."+PID in path
                            for _,_,path in calls if path.startswith("factory_change_sets?")))
        self.assertNotIn("b135b920043b4eeac87db9aba597af9142a33b53",str(report))

    def test_native_green_and_explicit_no_preview_still_require_merge(self):
        cp,gh=fixtures(preview={"required":False,"reason":"no deployable surface"},with_block=False)
        mark_ci_green(gh)
        report,_=observer(cp,gh)
        self.assertEqual(report["native_ci"]["status"],"verified")
        self.assertEqual(report["preview"]["status"],"not_applicable_by_explicit_policy_or_changed_paths")
        self.assertEqual(report["reason_codes"],["human_production_merge_pending"])
        self.assertFalse(report["ready_for_production"])
        self.assertFalse(report["release"]["authorized"])

    def test_preview_applicable_by_real_source_path_not_type_guess(self):
        cp,gh=fixtures(preview={"provider":"vercel","required_paths":["src/web/**"]})
        mark_ci_green(gh)
        report,_=observer(cp,gh)
        self.assertTrue(report["preview"]["required"])
        self.assertEqual(report["preview"]["matched_path_count"],1)
        self.assertEqual(report["preview"]["status"],"browser_evidence_not_verified")
        self.assertIn("preview_browser_evidence_not_verified",report["reason_codes"])

    def test_explicit_scoped_no_preview_on_other_codepath(self):
        cp,gh=fixtures(preview={"provider":"vercel","required_paths":["apps/console/**"]})
        gh["files"]=[{"filename":"src/ai_product_factory/safe_worker.py"}]
        gh["pr"]["changed_files"]=1
        report,_=observer(cp,gh)
        self.assertFalse(report["preview"]["required"])
        self.assertEqual(report["preview"]["status"],"not_applicable_by_explicit_policy_or_changed_paths")
        self.assertNotIn("preview_browser_evidence_not_verified",report["reason_codes"])

    def test_missing_preview_policy_never_defaults_to_no_preview(self):
        cp,gh=fixtures(preview=None)
        mark_ci_green(gh)
        report,_=observer(cp,gh)
        self.assertTrue(report["preview"]["required"])
        self.assertIn("preview_policy_unconfigured",report["reason_codes"])

    def test_unjustified_preview_n_a_fails_closed(self):
        cp,gh=fixtures(preview={"required":False})
        report,_=observer(cp,gh)
        self.assertEqual(report["preview"]["status"],"policy_not_justified")
        self.assertIn("preview_policy_unconfigured",report["reason_codes"])

    def test_paused_or_draft_project_cannot_be_authorized(self):
        for state,generation in (("paused",4),("draft",0),("stopped",3)):
            with self.subTest(state=state):
                cp,gh=fixtures(with_block=False)
                cp["control"][0].update(state=state,generation=generation)
                mark_ci_green(gh)
                r,_=observer(cp,gh)
                self.assertIn("project_not_running",r["reason_codes"])
                self.assertFalse(r["ready_for_production"])

    def test_head_sha_must_match_actual_open_pr(self):
        alterations=[
            ("head drift",lambda p:p["head"].update(sha="f"*40)),
            ("closed PR",lambda p:p.update(state="closed")),
            ("merged",lambda p:p.update(merged=True)),
            ("wrong base",lambda p:p["base"].update(ref="not-main")),
            ("fork",lambda p:p["head"]["repo"].update(full_name="unknown/fork")),
            ("other base repo",lambda p:p["base"]["repo"].update(full_name="unknown/repo")),
            ("wrong number",lambda p:p.update(number=4)),
        ]
        for name,change in alterations:
            with self.subTest(case=name):
                cp,gh=fixtures()
                change(gh["pr"])
                with self.assertRaises(CandidateGateEvidenceError):
                    observer(cp,gh)

    def test_project_identity_and_control_fail_closed(self):
        mutations=[
            lambda cp:cp["project"][0].update(repository="other/repo"),
            lambda cp:cp["project"][0].update(is_active=False),
            lambda cp:cp["project"][0].update(project_key="another-key"),
            lambda cp:cp["control"][0].update(project_id="00000000-0000-4000-8000-000000000000"),
            lambda cp:cp["control"][0].update(generation=-1),
            lambda cp:cp["project"].append(dict(cp["project"][0])),
        ]
        for change in mutations:
            cp,gh=fixtures()
            change(cp)
            with self.assertRaises(CandidateGateEvidenceError):
                observer(cp,gh)

    def test_no_checks_and_only_push_are_not_a_ci_green(self):
        cp,gh=fixtures()
        gh["checks"]={"total_count":0,"check_runs":[]}
        gh["runs"]["workflow_runs"]=[gh["runs"]["workflow_runs"][1]]
        gh["runs"]["total_count"]=1
        gh["runs"]["workflow_runs"][0]["conclusion"]="success"
        r,_=observer(cp,gh)
        self.assertEqual(r["native_ci"]["status"],"blocked")
        self.assertFalse(r["native_ci"]["native_pr_workflow_verified"])

    def test_duplicate_check_names_latest_only_not_stale_failed_retry(self):
        cp,gh=fixtures()
        mark_ci_green(gh)
        gh["checks"]["check_runs"].append({
            "id":1,"name":"verify","head_sha":SHA,"status":"completed",
            "conclusion":"failure","app":{"slug":"github-actions"}
        })
        gh["checks"]["total_count"]=3
        r,_=observer(cp,gh)
        self.assertEqual(r["native_ci"]["status"],"verified")
        self.assertEqual(r["native_ci"]["failed_checks"],0)
        self.assertEqual(r["native_ci"]["latest_checks"],2)

    def test_latest_failed_pr_run_blocks_older_success(self):
        cp,gh=fixtures()
        mark_ci_green(gh)
        gh["runs"]["workflow_runs"].append({
            **gh["runs"]["workflow_runs"][0], "id":75,"conclusion":"failure"
        })
        gh["runs"]["total_count"]=3
        r,_=observer(cp,gh)
        self.assertEqual(r["native_ci"]["status"],"blocked")

    def test_ci_skipped_is_never_success(self):
        cp,gh=fixtures()
        mark_ci_green(gh)
        gh["checks"]["check_runs"][1]["conclusion"]="skipped"
        r,_=observer(cp,gh)
        self.assertEqual(r["native_ci"]["status"],"blocked")

    def test_check_source_identity_must_be_exact(self):
        cp,gh=fixtures()
        for mutation in (
            lambda r:r.update(head_sha="a"*40),
            lambda r:r.update(id=True),
            lambda r:r.update(app={"slug":None}),
            lambda r:r.update(name="<script>"),
        ):
            local=copy.deepcopy(gh)
            mutation(local["checks"]["check_runs"][0])
            with self.assertRaises(CandidateGateEvidenceError):
                observer(cp,local)

    def test_native_gh_workflow_provenance_must_match_repo_and_branch(self):
        cp,gh=fixtures()
        for mutate in (
            lambda r:r.update(head_sha="b"*40),
            lambda r:r.update(event="issue_comment"),
            lambda r:r.update(head_branch="other"),
            lambda r:r.update(repository={"full_name":"wrong/repo"}),
            lambda r:r.update(path=".github/other.yml"),
        ):
            local=copy.deepcopy(gh)
            mutate(local["runs"]["workflow_runs"][0])
            with self.assertRaises(CandidateGateEvidenceError):
                observer(cp,local)

    def test_unbounded_page_refuses_to_certify(self):
        cp,gh=fixtures()
        gh["checks"]["total_count"]=101
        with self.assertRaises(CandidateGateEvidenceError):
            observer(cp,gh)
        cp,gh=fixtures()
        gh["pr"]["changed_files"]=101
        with self.assertRaises(CandidateGateEvidenceError):
            observer(cp,gh)
        cp,gh=fixtures()
        cp["blocked"]=cp["blocked"]*26
        with self.assertRaises(CandidateGateEvidenceError):
            observer(cp,gh)

    def test_missing_or_cross_project_change_set_does_not_authorize(self):
        cp,gh=fixtures()
        cp["blocked"][0]["project_id"]="99999999-9999-4999-8999-999999999999"
        with self.assertRaises(CandidateGateEvidenceError):
            observer(cp,gh)
        cp,gh=fixtures()
        cp["control"]=[]
        with self.assertRaises(CandidateGateEvidenceError):
            observer(cp,gh)

    def test_changed_file_traversal_or_duplicates_fails_closed(self):
        cp,gh=fixtures()
        for invalid in ("../secret","/abs/path","a\nb","src/../bad"):
            gh["files"][0]["filename"]=invalid
            with self.subTest(invalid=invalid),self.assertRaises(CandidateGateEvidenceError):
                observer(cp,gh)
        cp,gh=fixtures()
        gh["files"][1]["filename"]=gh["files"][0]["filename"]
        with self.assertRaises(CandidateGateEvidenceError):
            observer(cp,gh)


class OwnerCommandTests(unittest.TestCase):
    def event(self,body="/factory-candidate-gates infodive-service-desk pr=5 sha="+SHA):
        return {
            "repository":{"full_name":"leandrosilveiradepaula/ai-product-factory"},
            "issue":{"number":713},
            "comment":{"author_association":"OWNER","body":body},
        }

    def test_exact_owner_command_can_only_select_existing_target(self):
        from scripts.audit_candidate_gates import validate_event
        self.assertEqual(
            validate_event(self.event(),repository="leandrosilveiradepaula/ai-product-factory"),
            (PROJECT,PR,SHA),
        )

    def test_non_owner_other_issue_fork_and_unsafe_shell_inputs_fail(self):
        from scripts.audit_candidate_gates import validate_event
        changes=[
            lambda e:e["comment"].update(author_association="MEMBER"),
            lambda e:e["issue"].update(number=714),
            lambda e:e["issue"].update(pull_request={}),
            lambda e:e["repository"].update(full_name="other/repo"),
            lambda e:e["comment"].update(body="/factory-candidate-gates a pr=5 sha="+SHA+"\nexit 0"),
            lambda e:e["comment"].update(body="/factory-candidate-gates a pr=5 sha=main"),
            lambda e:e["comment"].update(body="/factory-candidate-gates a pr=5 sha="+SHA+"; echo"),
        ]
        for change in changes:
            e=self.event()
            change(e)
            with self.assertRaises(ValueError):
                validate_event(e,repository="leandrosilveiradepaula/ai-product-factory")

    def test_rejected_event_has_bounded_credential_free_failure_receipt(self):
        from scripts.audit_candidate_gates import main
        with tempfile.TemporaryDirectory() as tmp:
            ev=Path(tmp)/"event.json"
            receipt=Path(tmp)/"result.json"
            ev.write_text(json.dumps(self.event("/factory-candidate-gates bad pr=8 sha=missing")))
            with patch.dict("os.environ",{"GITHUB_REPOSITORY":"leandrosilveiradepaula/ai-product-factory"},clear=True):
                with patch("sys.stdout",new_callable=io.StringIO) as captured:
                    result=main(["--event-path",str(ev),"--output",str(receipt)])
            self.assertEqual(result,2)
            self.assertTrue(receipt.exists())
            evidence=json.loads(receipt.read_text())
            self.assertEqual(evidence["reason_code"],"unverifiable_live_evidence")
            self.assertFalse(evidence["product_ready"])
            self.assertFalse(evidence["ready_for_production"])
            self.assertNotIn("sk-",captured.getvalue())

    def test_workflow_only_owner_read_only_on_original_main(self):
        workflow=(Path(__file__).resolve().parents[1]/
                  ".github/workflows/autonomous-runner.yml").read_text()
        job=workflow.split("\n  candidate-gates-readonly:\n",1)[1].split("\n  codex-route-preflight:\n",1)[0]
        for invariant in (
            "github.event_name == 'issue_comment'",
            "github.event.action == 'created'",
            "github.event.issue.number == 713",
            "github.event.comment.author_association == 'OWNER'",
            "github.event.issue.pull_request",
            "/factory-candidate-gates ",
            "persist-credentials: false",
            "id-token: write",
            "contents: read",
            "checks: read",
            "pull-requests: read",
            "Validate exact owner comment before protected OIDC",
            "scripts/audit_candidate_gates.py",
            "uses: ./.github/actions/control-plane-oidc",
            "upload-artifact",
            "retention-days: 7",
        ):
            with self.subTest(field=invariant):
                self.assertIn(invariant,job)
        validate_index=job.index("Validate exact owner comment before protected OIDC")
        oidc_index=job.index("uses: ./.github/actions/control-plane-oidc")
        self.assertLess(validate_index,oidc_index)
        for forbidden in (
            "permissions:\n      contents: write",
            "issues: write","actions: write",
            "OPENAI_API_KEY", "VERCEL_TOKEN",
            "workflow_dispatch:","gh pr merge","pull_request_target:",
            "--mode dispatch","--mode product", "--mode codex",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden,job)
        self.assertEqual(job.count("FACTORY_GITHUB_TOKEN"),2)


if __name__=="__main__":
    unittest.main()
