"""Executable fail-closed, model-free global readiness observer contracts."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ai_product_factory.global_readiness_evidence import (
    GlobalReadinessEvidenceError, observe_current_product,
)
from ai_product_factory.product_readiness import (
    REQUIRED_DOMAINS, REQUIRED_COVERAGE_BY_DOMAIN, ALLOWED_VERIFICATION_STATES,
)

P="11111111-1111-4111-8111-111111111111"
R="22222222-2222-4222-8222-222222222222"
T="33333333-3333-4333-8333-333333333333"
S="a"*40
TREE="b"*40
REPO="example/factory"
RUN=141
VERCEL_URL = "https://vercel.com/leandros-projects-102e32ab/ai-product-factory-console/AbC1234567890defGHJkL"


def complete_eval():
    return {"id":"44444444-4444-4444-8444-444444444444",
            "run_id":R,"status":"passed","baseline_ref":S,
            "result":{"ready":True,"status":"passed","assessed_commit":S,
                      "assessment_ref":"independent-audit-"+S,
                      "blockers":[],
                      "domains":{k:{"status":"passed",
                          "evidence":["independent/"+k+"/"+S],
                          "coverage":list(REQUIRED_COVERAGE_BY_DOMAIN[k]),
                          "verification_state":sorted(ALLOWED_VERIFICATION_STATES[k])[0]}
                          for k in REQUIRED_DOMAINS}}}


def baseline_eval():
    return {"id":"55555555-5555-4555-8555-555555555555","run_id":R,
            "status":"passed","baseline_ref":S,
            "result":{"assessed_commit":S,"verification_state":"executed",
                      "blockers":[],"coverage":["repository_inventory",
                      "inherited_debt","critical_journeys"],
                      "evidence":["sha-exact-baseline-"+S]}}


def fixture(*,kind="platform",evaluations=None,baseline=None):
    paths=[
        {"path":"src/core.py","type":"blob","mode":"100644"},
        {"path":"tests/test_core.py","type":"blob","mode":"100644"},
        {"path":".github/workflows/validate.yml","type":"blob","mode":"100644"},
        {"path":"docs/OPERATIONS.md","type":"blob","mode":"100644"},
        {"path":"docs/PRODUCT_READINESS.md","type":"blob","mode":"100644"},
        {"path":"PROJECT_PLAN.md","type":"blob","mode":"100644"},
        {"path":"apps/console/src/app/page.tsx","type":"blob","mode":"100644"},
    ]
    gh={
        "/repos/"+REPO:{"full_name":REPO,"default_branch":"main"},
        "/repos/"+REPO+"/git/ref/heads/main":{"object":{"sha":S}},
        "/repos/"+REPO+"/actions/runs/"+str(RUN):{
            "id":RUN,"name":"validate","event":"push","head_branch":"main",
            "head_sha":S,"conclusion":"success","status":"completed",
            "path":".github/workflows/validate.yml","run_attempt":1,
            "repository":{"full_name":REPO}},
        "/repos/"+REPO+"/actions/runs?head_sha="+S+"&event=push&per_page=100":{
            "total_count":1,"workflow_runs":[
                {"id":RUN,"name":"validate","event":"push","head_branch":"main",
                 "head_sha":S,"path":".github/workflows/validate.yml",
                 "run_attempt":1,"conclusion":"success","status":"completed",
                 "repository":{"full_name":REPO}},
            ],
        },
        "/repos/"+REPO+"/commits/"+S+"/status":{"sha":S,"statuses":[]},
        "/repos/"+REPO+"/git/commits/"+S:{"sha":S,"tree":{"sha":TREE}},
        "/repos/"+REPO+"/git/trees/"+TREE+"?recursive=1":{
            "sha":TREE,"truncated":False,"tree":paths},
        "/repos/"+REPO+"/actions/runs/"+str(RUN)+"/jobs?per_page=100":{
            "total_count":2,"jobs":[
                {"id":31,"run_id":RUN,"head_sha":S,"name":"test",
                 "status":"completed","conclusion":"success"},
                {"id":32,"run_id":RUN,"head_sha":S,"name":"factory-acceptance",
                 "status":"completed","conclusion":"success"},
            ],
        },
        "/repos/"+REPO+"/commits/"+S+"/check-runs?per_page=100":{
            "total_count":2,"check_runs":[
                {"head_sha":S,"status":"completed","conclusion":"success","name":"test"},
                {"head_sha":S,"status":"completed","conclusion":"success","name":"factory-acceptance"},
            ]},
    }
    cp={
        "factory_projects": [{"id":P,"project_key":"factory","repository":REPO,
                              "project_kind":kind,"lifecycle_stage":"operations","is_active":True}],
        "factory_evaluations.product_readiness": evaluations or [],
        "factory_evaluations.existing_project_baseline": baseline or [],
        "factory_runs":[{"id":R,"task_id":T}],
        "factory_tasks":[{"id":T,"project_id":P}],
    }
    def github_get(path):
        if path not in gh:
            raise AssertionError("Unexpected Github read "+path)
        return gh[path]
    def cp_get(path):
        if path.startswith("factory_projects?"): return cp["factory_projects"]
        if path.startswith("factory_evaluations?"):
            if "eval_type=eq.existing_project_baseline" in path:
                return cp["factory_evaluations.existing_project_baseline"]
            return cp["factory_evaluations.product_readiness"]
        if path.startswith("factory_runs?"): return cp["factory_runs"]
        if path.startswith("factory_tasks?"): return cp["factory_tasks"]
        raise AssertionError("Unexpected Control Plane read "+path)
    return gh,cp,github_get,cp_get


class GlobalReadinessTests(unittest.TestCase):
    def audit(self,**kwargs):
        return observe_current_product(repository=REPO,sha=S,
               validation_run_id=RUN,**kwargs)

    def test_realistic_no_evaluation_is_six_unverified_domains_not_ready(self):
        gh,cp,gg,cg=fixture()
        report=self.audit(github_get=gg,cp_get=cg)
        self.assertEqual(report["global_readiness"]["status"],"not_assessed")
        self.assertFalse(report["global_readiness"]["product_ready"])
        self.assertEqual(report["global_readiness"]["missing_or_unverified_domains"],list(REQUIRED_DOMAINS))
        self.assertEqual(len(report["work_proposals"]),6)
        self.assertTrue(all(not x["start_authorized"] and not x["paid_calls_authorized"]
                            and x["work_type"]=="independent_verification" for x in report["work_proposals"]))
        self.assertEqual(report["ci_evidence"]["checks_observed"],2)
        self.assertEqual(report["ci_evidence"]["validation_jobs"]["verification_state"],"executed_same_SHA")
        self.assertEqual(report["source_inventory"]["tracked_files"],7)
        self.assertEqual(report["current_sha_operational_evidence"]["authenticated_console"]["status"],"not_observed")
        self.assertEqual(report["current_sha_operational_evidence"]["production_deployment"]["status"],"not_reported")
        self.assertTrue(report["source_inventory"]["documents_present"]["operations"])
        self.assertEqual((report["writes"],report["paid_calls"]),(0,0))

    def test_complete_independently_durable_eval_can_pass_only_current_head(self):
        gh,cp,gg,cg=fixture(evaluations=[complete_eval()])
        report=self.audit(github_get=gg,cp_get=cg)
        self.assertTrue(report["global_readiness"]["product_ready"])
        self.assertEqual(report["global_readiness"]["missing_or_unverified_domains"],[])
        self.assertEqual(report["work_proposals"],[])
        self.assertEqual(report["global_readiness"]["scope"],"entire_product_at_exact_current_head")

    def test_self_reported_ready_is_rejected_if_durable_evaluation_failed(self):
        row=complete_eval();row["status"]="failed"
        _,_,gg,cg=fixture(evaluations=[row])
        x=self.audit(github_get=gg,cp_get=cg)
        self.assertFalse(x["global_readiness"]["product_ready"])
        self.assertEqual(len(x["work_proposals"]),6)

    def test_partial_domain_coverage_fails_closed(self):
        row=complete_eval()
        row["result"]["domains"]["security"]["coverage"]=["authn_authz"]
        _,_,gg,cg=fixture(evaluations=[row])
        x=self.audit(github_get=gg,cp_get=cg)
        self.assertFalse(x["global_readiness"]["product_ready"])
        self.assertEqual(x["global_readiness"]["missing_or_unverified_domains"],list(REQUIRED_DOMAINS))

    def test_existing_project_requires_independent_exact_sha_baseline(self):
        _,_,gg,cg=fixture(kind="existing",evaluations=[complete_eval()])
        report=self.audit(github_get=gg,cp_get=cg)
        self.assertFalse(report["global_readiness"]["product_ready"])
        self.assertEqual(report["work_proposals"][-1]["domain"],"existing_project_baseline")
        _,_,gg,cg=fixture(kind="existing",evaluations=[complete_eval()],baseline=[baseline_eval()])
        self.assertTrue(self.audit(github_get=gg,cp_get=cg)["global_readiness"]["product_ready"])

    def test_comment_event_flood_cannot_stall_exact_sha_ci_and_readiness(self):
        # Real main can receive hundreds of issue_comment/schedule events
        # without producing a new commit. They must not count as CI evidence.
        gh,cp,gg,cg=fixture()
        old_uri="/repos/"+REPO+"/actions/runs?head_sha="+S+"&per_page=100"
        gh[old_uri]={"total_count":302,"workflow_runs":[
            {"id":1000+i,"event":"issue_comment","name":"Factory autonomous runner",
             "head_sha":S,"repository":{"full_name":REPO}}
            for i in range(100)
        ]}
        calls=[]
        def read(path):
            calls.append(path)
            return gg(path)
        report=self.audit(github_get=read,cp_get=cg)
        self.assertFalse(report["global_readiness"]["product_ready"])
        self.assertEqual(report["ci_evidence"]["validation_jobs"]["validated_run_id"],RUN)
        self.assertNotIn(old_uri,calls)
        self.assertIn("/repos/"+REPO+"/actions/runs?head_sha="+S+
                      "&event=push&per_page=100",calls)
        self.assertEqual((report["writes"],report["paid_calls"]),(0,0))

    def test_trusted_validate_path_cannot_be_impersonated_by_name(self):
        gh,cp,gg,cg=fixture()
        gh["/repos/"+REPO+"/actions/runs/"+str(RUN)]["path"]=".github/workflows/unsafe.yml"
        with self.assertRaisesRegex(GlobalReadinessEvidenceError,"validation workflow"):
            self.audit(github_get=gg,cp_get=cg)
        from ai_product_factory.global_readiness_evidence import find_current_validation_run
        gh,cp,gg,cg=fixture()
        uri="/repos/"+REPO+"/actions/runs?head_sha="+S+"&event=push&per_page=100"
        gh[uri]["workflow_runs"][0]["path"]=".github/workflows/unsafe.yml"
        with self.assertRaisesRegex(GlobalReadinessEvidenceError,"validate run"):
            find_current_validation_run(repository=REPO,sha=S,branch="main",github_get=gg)

    def test_push_only_inventory_fails_closed_if_filtered_api_is_not_honest(self):
        uri="/repos/"+REPO+"/actions/runs?head_sha="+S+"&event=push&per_page=100"
        for label,mutate in (
            ("non-push result",lambda obj:obj["workflow_runs"][0].update(event="issue_comment")),
            ("wrong SHA",lambda obj:obj["workflow_runs"][0].update(head_sha="f"*40)),
            ("wrong repository",lambda obj:obj["workflow_runs"][0]["repository"].update(full_name="other/repo")),
            ("incomplete count",lambda obj:obj.update(total_count=2)),
            ("overfull true push history",lambda obj:obj.update(total_count=101)),
        ):
            with self.subTest(label=label):
                gh,cp,gg,cg=fixture()
                mutate(gh[uri])
                with self.assertRaises(GlobalReadinessEvidenceError):
                    self.audit(github_get=gg,cp_get=cg)

    def test_project_identity_and_remote_sha_are_authoritative(self):
        tests=[
            ("head drift", lambda gh,cp:gh["/repos/"+REPO+"/git/ref/heads/main"]["object"].update(sha="c"*40)),
            ("wrong repo", lambda gh,cp:cp["factory_projects"][0].update(repository="other/repo")),
            ("duplicate project", lambda gh,cp:cp["factory_projects"].append(dict(cp["factory_projects"][0]))),
            ("wrong validation head",lambda gh,cp:gh["/repos/"+REPO+"/actions/runs/"+str(RUN)].update(head_sha="d"*40)),
            ("failed validation",lambda gh,cp:gh["/repos/"+REPO+"/actions/runs/"+str(RUN)].update(conclusion="failure")),
            ("PR validation only",lambda gh,cp:gh["/repos/"+REPO+"/actions/runs/"+str(RUN)].update(event="pull_request")),
            ("truncated inventory",lambda gh,cp:gh["/repos/"+REPO+"/git/trees/"+TREE+"?recursive=1"].update(truncated=True)),
            ("symlink",lambda gh,cp:gh["/repos/"+REPO+"/git/trees/"+TREE+"?recursive=1"]["tree"].append({"type":"blob","mode":"120000","path":"secret"})),
            ("incomplete checks",lambda gh,cp:gh["/repos/"+REPO+"/commits/"+S+"/check-runs?per_page=100"].update(total_count=200)),
            ("ambiguous same-SHA runs",lambda gh,cp:gh["/repos/"+REPO+"/actions/runs?head_sha="+S+"&event=push&per_page=100"].update(total_count=200)),
            ("wrong workflow run SHA",lambda gh,cp:gh["/repos/"+REPO+"/actions/runs?head_sha="+S+"&event=push&per_page=100"]["workflow_runs"][0].update(head_sha="f"*40)),
            ("untrusted Vercel status SHA",lambda gh,cp:gh["/repos/"+REPO+"/commits/"+S+"/status"].update(sha="f"*40)),

            ("incomplete run jobs",lambda gh,cp:gh["/repos/"+REPO+"/actions/runs/"+str(RUN)+"/jobs?per_page=100"].update(total_count=200)),
            ("failed required validate job",lambda gh,cp:gh["/repos/"+REPO+"/actions/runs/"+str(RUN)+"/jobs?per_page=100"]["jobs"][0].update(conclusion="failure")),
            ("unrelated validation job",lambda gh,cp:gh["/repos/"+REPO+"/actions/runs/"+str(RUN)+"/jobs?per_page=100"]["jobs"][0].update(name="invented-success")),
            ("cross SHA validate job",lambda gh,cp:gh["/repos/"+REPO+"/actions/runs/"+str(RUN)+"/jobs?per_page=100"]["jobs"][0].update(head_sha="f"*40)),

        ]
        for label,change in tests:
            with self.subTest(label=label):
                gh,cp,gg,cg=fixture()
                change(gh,cp)
                with self.assertRaises(GlobalReadinessEvidenceError):
                    self.audit(github_get=gg,cp_get=cg)

    def test_cross_project_or_duplicated_assessments_cannot_pass(self):
        gh,cp,gg,cg=fixture(evaluations=[complete_eval()])
        cp["factory_tasks"][0]["project_id"]="99999999-9999-4999-8999-999999999999"
        with self.assertRaises(GlobalReadinessEvidenceError):
            self.audit(github_get=gg,cp_get=cg)
        gh,cp,gg,cg=fixture(evaluations=[complete_eval(),complete_eval()])
        with self.assertRaises(GlobalReadinessEvidenceError):
            self.audit(github_get=gg,cp_get=cg)

    def test_validation_params_and_repo_traversal_are_rejected(self):
        _,_,gg,cg=fixture()
        for repo,sha,run in (
            ("../bad",S,RUN),(REPO,"main",RUN),(REPO,S,True),
            (REPO,S,0),(REPO+"/x",S,RUN),
        ):
            with self.subTest(repo=repo,sha=sha,run=run),self.assertRaises(ValueError):
                observe_current_product(repository=repo,sha=sha,
                                        validation_run_id=run,
                                        github_get=gg,cp_get=cg)

    def test_workflow_is_only_successful_main_push_with_no_paid_worker(self):
        root=Path(__file__).resolve().parents[1]
        yaml=(root/".github/workflows/autonomous-runner.yml").read_text()
        broker=(root/"supabase/functions/factory-runtime-control-plane/index.ts").read_text()
        self.assertFalse((root/".github/workflows/global-product-readiness.yml").exists())
        self.assertIn('workflows: ["Control Plane OIDC preflight", "validate", "Authenticated Console visual evidence"]',yaml)
        self.assertIn('const TRUSTED_BACKUP_WORKFLOW_REF = "leandrosilveiradepaula/ai-product-factory/.github/workflows/autonomous-runner.yml@refs/heads/main"',broker)
        self.assertIn('const GENERIC_PROXY_WORKFLOW_REFS = new Set([',broker)
        self.assertNotIn('"leandrosilveiradepaula/ai-product-factory/.github/workflows/global-product-readiness.yml@refs/heads/main"',broker)
        probe=yaml.split("\n  schedule-probe:",1)[1].split("\n  github-access-preflight:",1)[0]
        self.assertIn("github.event.workflow_run.event == 'schedule'",probe)
        self.assertIn("steps.backup_wake.outputs.wake == 'true'",probe)
        self.assertNotIn('global-readiness-post-ci',probe)
        job=yaml.split("\n  global-readiness-post-ci:",1)[1]
        for term in (
            "github.event_name == 'workflow_run'",
            "github.event.workflow_run.name == 'validate'",
            "github.event.workflow_run.name == 'Authenticated Console visual evidence'",
            "github.event.workflow_run.conclusion == 'failure'",
            "github.event.workflow_run.event == 'push'",
            "github.event.workflow_run.conclusion == 'success'",
            "github.event.workflow_run.status == 'completed'",
            "github.event.workflow_run.head_branch == 'main'",
            "github.event.workflow_run.repository.full_name == github.repository",
            "github.event.workflow_run.head_sha",
            "    environment: openai-api",
            "      contents: read","      actions: read","      checks: read",
            "      id-token: write","GITHUB_TOKEN: ${{ github.token }}",
            "persist-credentials: false",
            "uses: ./.github/actions/control-plane-oidc",
            "audit_global_readiness.py","retention-days: 7",
        ):
            with self.subTest(term=term):self.assertIn(term,job)
        for forbidden in ("FACTORY_GITHUB_TOKEN","OPENAI_API_KEY",
                          "schedule:","workflow_dispatch:","merge_pull_request",
                          "contents: write","pull-requests: write",
                          "--mode product","--mode dispatch",
                          "factory_claim_next_run","FACTORY_PRIMARY_MODEL_ENABLED"):
            self.assertNotIn(forbidden,job)

    def test_script_rejects_forged_event_and_does_not_echo_exceptions(self):
        path=Path(__file__).resolve().parents[1]/"scripts/audit_global_readiness.py"
        spec=importlib.util.spec_from_file_location("audit_global_test",path)
        assert spec and spec.loader
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        event={"repository":{"full_name":REPO,"default_branch":"main"},
               "workflow_run":{"id":RUN,"head_sha":S,"name":"validate",
                               "event":"push","status":"completed",
                               "head_branch":"main","conclusion":"success"}}
        self.assertEqual(mod.validate_event(event,REPO),(S,RUN))
        with self.assertRaises(ValueError):
            mod.validate_event({**event,"workflow_run":{**event["workflow_run"],"event":"pull_request"}},REPO)
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"event.json"
            out=Path(tmp)/"audit.json"
            source.write_text(json.dumps(event))
            stdout=io.StringIO()
            with patch.dict(os.environ,{"GITHUB_REPOSITORY":REPO},clear=True), \
                 patch.object(mod,"resolve_github_token",return_value="secret"), \
                 patch.object(mod,"SupabaseAdmissionReader",side_effect=RuntimeError("secret value in error")), \
                 contextlib.redirect_stdout(stdout):
                status=mod.main(["--event-path",str(source),"--output",str(out)])
            self.assertEqual(status,2)
            self.assertFalse(json.loads(out.read_text())["product_ready"])
            self.assertEqual(json.loads(out.read_text())["reason_code"],
                             "control_plane_oidc_unavailable")
            self.assertEqual(json.loads(out.read_text())["error_class"],"RuntimeError")
            self.assertNotIn("secret value",out.read_text())
            self.assertNotIn("secret value",stdout.getvalue())


class GlobalPostVisualReceiptTests(unittest.TestCase):
    def visual(self,*,conclusion="success",status="completed",with_artifact=True):
        from ai_product_factory.global_readiness_evidence import (
            _authenticated_visual_receipt, find_current_validation_run,
        )
        gh,cp,gg,cg=fixture()
        visual=142
        row={"id":visual,"name":"Authenticated Console visual evidence",
             "event":"push","head_branch":"main","head_sha":S,"status":status,
             "conclusion":conclusion if status=="completed" else None,
             "run_attempt":1,"path":".github/workflows/authenticated-visual-evidence.yml",
             "repository":{"full_name":REPO}}
        uri="/repos/"+REPO+"/actions/runs?head_sha="+S+"&event=push&per_page=100"
        gh[uri]["workflow_runs"].append(row)
        gh[uri]["total_count"] += 1
        gh["/repos/"+REPO+"/actions/runs/"+str(visual)+"/jobs?per_page=100"]={
            "total_count":1,"jobs":[{"id":33,"run_id":visual,"head_sha":S,
                                   "name":"capture","status":"completed","conclusion":"success"}],
        }
        gh["/repos/"+REPO+"/actions/runs/"+str(visual)+"/artifacts?per_page=100"]={
            "total_count":int(with_artifact),
            "artifacts":[{"id":1212,"name":"authenticated-console-"+str(visual),
                          "expired":False,"size_in_bytes":5200,
                          "workflow_run":{"id":visual,"head_sha":S,"head_branch":"main"}}] if with_artifact else [],
        }
        gh["/repos/"+REPO+"/commits/"+S+"/status"]["statuses"]=[
            {"context":"Vercel","state":"success","target_url":VERCEL_URL}]
        return gh,cp,gg,cg,visual

    def test_completed_visual_and_deployment_are_executed_signals_not_full_readiness(self):
        gh,cp,gg,cg,visual=self.visual()
        report=observe_current_product(repository=REPO,sha=S,validation_run_id=RUN,
                                       github_get=gg,cp_get=cg,
                                       visual_trigger_run_id=visual)
        evidence=report["current_sha_operational_evidence"]
        self.assertEqual(evidence["ci"]["status"],"verified")
        self.assertEqual(evidence["authenticated_console"]["status"],"verified")
        self.assertEqual(evidence["authenticated_console"]["workflow_run_id"],visual)
        self.assertEqual(evidence["authenticated_console"]["artifact_id"],1212)
        self.assertEqual(evidence["production_deployment"]["status"],"provider_reported_ready")
        self.assertEqual(evidence["production_deployment"]["project_identity"],"pinned_team_and_project")
        self.assertFalse(report["global_readiness"]["product_ready"])
        self.assertEqual(report["global_readiness"]["missing_or_unverified_domains"],list(REQUIRED_DOMAINS))
        experience=next(x for x in report["work_proposals"] if x["domain"]=="product_experience")
        self.assertEqual(experience["observed_evidence"],["authenticated_console_browser"])
        self.assertIn("remaining",experience["next_step"].replace("full_product","remaining_full_product"))
        self.assertTrue(all(not x["start_authorized"] and not x["paid_calls_authorized"]
                            for x in report["work_proposals"]))
        self.assertEqual((report["writes"],report["paid_calls"]),(0,0))

    def test_visual_before_completion_remains_pending_not_verified(self):
        gh,cp,gg,cg,visual=self.visual(status="in_progress")
        report=observe_current_product(repository=REPO,sha=S,validation_run_id=RUN,
                                       github_get=gg,cp_get=cg)
        self.assertEqual(report["current_sha_operational_evidence"]["authenticated_console"]["status"],"pending")
        with self.assertRaises(GlobalReadinessEvidenceError):
            observe_current_product(repository=REPO,sha=S,validation_run_id=RUN,
                                    github_get=gg,cp_get=cg,visual_trigger_run_id=visual)

    def test_failed_visual_never_promotes_a_recorded_product_pass(self):
        gh,cp,gg,cg,visual=self.visual(conclusion="failure")
        cp["factory_evaluations.product_readiness"]=[complete_eval()]
        report=observe_current_product(repository=REPO,sha=S,validation_run_id=RUN,
                                       github_get=gg,cp_get=cg,
                                       visual_trigger_run_id=visual)
        self.assertEqual(report["current_sha_operational_evidence"]["authenticated_console"]["status"],"failed")
        self.assertFalse(report["global_readiness"]["product_ready"])
        self.assertEqual(len(report["work_proposals"]),6)

    def test_pending_deployment_downgrades_durable_readiness(self):
        gh,cp,gg,cg,visual=self.visual()
        gh["/repos/"+REPO+"/commits/"+S+"/status"]["statuses"][0]["state"]="pending"
        cp["factory_evaluations.product_readiness"]=[complete_eval()]
        report=observe_current_product(repository=REPO,sha=S,validation_run_id=RUN,
                                       github_get=gg,cp_get=cg)
        self.assertEqual(report["current_sha_operational_evidence"]["production_deployment"]["status"],"pending")
        self.assertFalse(report["global_readiness"]["product_ready"])
        self.assertEqual(report["global_readiness"]["status"],"not_ready")

    def test_unowned_vercel_context_never_becomes_operational_evidence(self):
        cases=(
            ("other team",VERCEL_URL.replace("leandros-projects-102e32ab","attacker-team")),
            ("other project",VERCEL_URL.replace("ai-product-factory-console","other-app")),
            ("lookalike hostname",VERCEL_URL.replace("vercel.com","vercel.com.evil.test")),
            ("untrusted endpoint","https://other-app.vercel.app/api/health"),
            ("http",VERCEL_URL.replace("https:","http:")),
            ("port",VERCEL_URL.replace("vercel.com","vercel.com:443")),
            ("username",VERCEL_URL.replace("https://","https://user@")),
            ("query",VERCEL_URL+"?secret=fake"),
            ("fragment",VERCEL_URL+"#browser"),
            ("trailing slash",VERCEL_URL+"/"),
            ("wrong deployment id","https://vercel.com/leandros-projects-102e32ab/ai-product-factory-console/short"),
        )
        for label,url in cases:
            with self.subTest(label=label):
                gh,cp,gg,cg,visual=self.visual()
                gh["/repos/"+REPO+"/commits/"+S+"/status"]["statuses"][0]["target_url"]=url
                cp["factory_evaluations.product_readiness"]=[complete_eval()]
                with self.assertRaisesRegex(GlobalReadinessEvidenceError,"outside owned Console project"):
                    observe_current_product(repository=REPO,sha=S,validation_run_id=RUN,
                                            github_get=gg,cp_get=cg)
        gh,cp,gg,cg,visual=self.visual()
        del gh["/repos/"+REPO+"/commits/"+S+"/status"]["statuses"][0]["target_url"]
        with self.assertRaises(GlobalReadinessEvidenceError):
            observe_current_product(repository=REPO,sha=S,validation_run_id=RUN,
                                    github_get=gg,cp_get=cg)

    def test_vercel_project_identity_matches_authenticated_browser_guard(self):
        guard=(Path(__file__).resolve().parents[1]/"scripts/console_visual_origin.mjs").read_text()
        self.assertIn('CONSOLE_PROJECT="ai-product-factory-console"',guard)
        self.assertIn('CONSOLE_TEAM="leandros-projects-102e32ab"',guard)
        self.assertIn("const DEPLOYMENT_ID=/^[A-Za-z0-9]{20,40}$/",guard)

    def test_provider_failure_overrides_old_global_pass_on_same_sha(self):
        gh,cp,gg,cg,visual=self.visual()
        gh["/repos/"+REPO+"/commits/"+S+"/status"]["statuses"][0]["state"]="failure"
        cp["factory_evaluations.product_readiness"]=[complete_eval()]
        report=observe_current_product(repository=REPO,sha=S,validation_run_id=RUN,
                                       github_get=gg,cp_get=cg)
        self.assertEqual(report["current_sha_operational_evidence"]["production_deployment"]["status"],"failed")
        self.assertFalse(report["global_readiness"]["product_ready"])

    def test_visual_identity_artifact_and_job_guards_fail_closed(self):
        altered=[
            ("rerun replay",lambda gh,n:gh["/repos/"+REPO+"/actions/runs?head_sha="+S+"&event=push&per_page=100"]["workflow_runs"][1].update(run_attempt=2)),
            ("unexpected workflow",lambda gh,n:gh["/repos/"+REPO+"/actions/runs?head_sha="+S+"&event=push&per_page=100"]["workflow_runs"][1].update(path="evil.yml")),
            ("wrong event",lambda gh,n:gh["/repos/"+REPO+"/actions/runs?head_sha="+S+"&event=push&per_page=100"]["workflow_runs"][1].update(event="pull_request")),
            ("failed capture job",lambda gh,n:gh["/repos/"+REPO+"/actions/runs/"+str(n)+"/jobs?per_page=100"]["jobs"][0].update(conclusion="failure")),
            ("wrong capture SHA",lambda gh,n:gh["/repos/"+REPO+"/actions/runs/"+str(n)+"/jobs?per_page=100"]["jobs"][0].update(head_sha="f"*40)),
            ("expired evidence",lambda gh,n:gh["/repos/"+REPO+"/actions/runs/"+str(n)+"/artifacts?per_page=100"]["artifacts"][0].update(expired=True)),
            ("empty encrypted evidence",lambda gh,n:gh["/repos/"+REPO+"/actions/runs/"+str(n)+"/artifacts?per_page=100"]["artifacts"][0].update(size_in_bytes=0)),
            ("wrong artifact SHA",lambda gh,n:gh["/repos/"+REPO+"/actions/runs/"+str(n)+"/artifacts?per_page=100"]["artifacts"][0]["workflow_run"].update(head_sha="f"*40)),
            ("missing artifact",lambda gh,n:gh["/repos/"+REPO+"/actions/runs/"+str(n)+"/artifacts?per_page=100"].update(total_count=0,artifacts=[])),
        ]
        for name,modify in altered:
            with self.subTest(name=name):
                gh,cp,gg,cg,visual=self.visual()
                modify(gh,visual)
                with self.assertRaises(GlobalReadinessEvidenceError):
                    observe_current_product(repository=REPO,sha=S,validation_run_id=RUN,
                                            github_get=gg,cp_get=cg,
                                            visual_trigger_run_id=visual)

    def test_exact_validation_selection_for_visual_cannot_use_visual_run_as_ci(self):
        from ai_product_factory.global_readiness_evidence import find_current_validation_run
        gh,cp,gg,cg,visual=self.visual()
        self.assertEqual(find_current_validation_run(repository=REPO,sha=S,
                                                     branch="main",github_get=gg),RUN)
        k="/repos/"+REPO+"/actions/runs?head_sha="+S+"&event=push&per_page=100"
        gh[k]["workflow_runs"][0].update(conclusion="failure")
        with self.assertRaises(GlobalReadinessEvidenceError):
            find_current_validation_run(repository=REPO,sha=S,branch="main",github_get=gg)
        gh[k]["workflow_runs"][0].update(conclusion="success")
        gh[k]["workflow_runs"].append(dict(gh[k]["workflow_runs"][0],id=888))
        gh[k]["total_count"] += 1
        with self.assertRaises(GlobalReadinessEvidenceError):
            find_current_validation_run(repository=REPO,sha=S,branch="main",github_get=gg)

    def test_visual_event_accepts_only_main_push_same_repo_without_dispatch(self):
        path=Path(__file__).resolve().parents[1]/"scripts/audit_global_readiness.py"
        spec=importlib.util.spec_from_file_location("global_post_visual_test",path)
        assert spec and spec.loader
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        event={"repository":{"full_name":REPO,"default_branch":"main"},
               "workflow_run":{"id":142,"head_sha":S,"name":"Authenticated Console visual evidence",
                               "event":"push","status":"completed","head_branch":"main",
                               "conclusion":"success"}}
        self.assertEqual(mod.resolve_observer_event(event,REPO),(S,142,"visual"))
        self.assertEqual(mod.resolve_observer_event({**event,"workflow_run":{**event["workflow_run"],"conclusion":"failure"}},REPO),(S,142,"visual"))
        for update in ({"event":"workflow_dispatch"},{"head_branch":"preview/pr-1"},
                       {"head_sha":"main"},{"status":"in_progress"},
                       {"name":"untrusted visual"},{"id":True}):
            with self.subTest(update=update),self.assertRaises(ValueError):
                mod.resolve_observer_event({**event,"workflow_run":{**event["workflow_run"],**update}},REPO)
        with self.assertRaises(ValueError):
            mod.resolve_observer_event({**event,"repository":{"full_name":"untrusted/repo","default_branch":"main"}},REPO)


if __name__=="__main__":
    unittest.main()
