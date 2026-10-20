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
            "repository":{"full_name":REPO}},
        "/repos/"+REPO+"/git/commits/"+S:{"sha":S,"tree":{"sha":TREE}},
        "/repos/"+REPO+"/git/trees/"+TREE+"?recursive=1":{
            "sha":TREE,"truncated":False,"tree":paths},
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
        self.assertEqual(report["source_inventory"]["tracked_files"],7)
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
        self.assertIn('workflows: ["Control Plane OIDC preflight", "validate"]',yaml)
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
            self.assertNotIn("secret value",out.read_text())
            self.assertNotIn("secret value",stdout.getvalue())

if __name__=="__main__":
    unittest.main()
