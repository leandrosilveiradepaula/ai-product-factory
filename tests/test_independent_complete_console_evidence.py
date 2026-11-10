"""Fail-closed proof for complete B3 surface and responsive browser evidence."""
from __future__ import annotations

import copy
import io
import json
import unittest
import zipfile
from unittest.mock import patch

from ai_product_factory.independent_authenticated_console_evidence import AuthenticatedConsoleEvidence
from ai_product_factory.independent_complete_console_evidence import (
    ARTIFACT_FILE, FIELDS, NAMES, ConsoleFullSurfaceEvidenceBlocked,
    read_verified_artifact_json, validate_surface_witness,
    verify_complete_console_surface,
)

REPO="leandrosilveiradepaula/ai-product-factory"
SHA="a"*40
SERV="b"*40
RUN=884433
P="/repos/"+REPO


def witness():
    return {
        "schema":"factory-b3-completed-surface-witness-v1",
        "runId":RUN, "sourceCommit":SHA, "targetCommit":SERV,
        "desktopRoutes":len(NAMES), "mobileRoutes":len(NAMES),
        "accessibleRoutes":len(NAMES), "routeNames":list(NAMES),
        "mobileDetailVerified":True, "keyboardSkipVerified":True,
        "browserErrors":0, "pageErrors":0, "failedResources":0,
        "productionWrites":0, "paidCalls":0,
        "fullStatesCertified":False,
        "fullAccessibilityCertified":False, "criticalE2eCertified":False,
    }


def fixture():
    artifact={
        "id":22, "name":"block1-b3-full-surface-"+str(RUN),
        "expired":False, "size_in_bytes":1300,
        "workflow_run":{"id":RUN,"head_sha":SHA,"head_branch":"main"},
    }
    git={
        P+"/actions/runs/"+str(RUN)+"/artifacts?per_page=100":{
            "total_count":2,
            "artifacts":[
                {"id":1,"name":"authenticated-console-"+str(RUN)},
                artifact,
            ],
        },
        P+"/compare/"+SERV+"..."+SHA:{
            "status":"ahead","behind_by":0,
            "base_commit":{"sha":SERV},
            "merge_base_commit":{"sha":SERV},
        },
    }
    tree={"truncated":False, "tree":[
        {"path":"apps/console/app/page.tsx",
         "mode":"100644","type":"blob","sha":"c"*40},
    ]}
    git[P+"/git/trees/"+SERV+"?recursive=1"]=tree
    git[P+"/git/trees/"+SHA+"?recursive=1"]=copy.deepcopy(tree)
    registry=[{
        "workflow_run_id":RUN,"source_commit":SHA,
        "artifact_name":"authenticated-console-"+str(RUN),
        "status":"captured",
    }]
    proof=AuthenticatedConsoleEvidence(
        repository=REPO,assessed_commit=SHA,workflow_run_id=RUN,artifact_id=1,
    )
    return git,registry,proof,artifact


class CompleteConsoleEvidenceTests(unittest.TestCase):
    def verify(self,git=None,registry=None,proof=None,payload=None):
        default_git,default_registry,default_proof,_=fixture()
        data=default_git if git is None else git
        rows=default_registry if registry is None else registry
        auth=default_proof if proof is None else proof
        return verify_complete_console_surface(
            repository=REPO,assessed_commit=SHA,authenticated_capture=auth,
            github_get=lambda p:data[p],
            control_plane_get=lambda p:rows,
            artifact_reader=lambda repository,artifact_id:payload if payload is not None else witness(),
        )

    def test_complete_receipt_approves_only_surface_inventory_and_responsive(self):
        result=self.verify()
        self.assertEqual(result.receipt()["certifies"],["surface_inventory","responsive"])
        for criterion in ("surface_inventory","responsive"):
            v=result.criterion(criterion)
            self.assertEqual(v.criterion,criterion)
            self.assertEqual(v.repository,REPO)
            self.assertEqual(v.assessed_commit,SHA)
            self.assertIn(SHA,v.evidence[0])
            self.assertEqual(v.retained_receipt["criterion"],criterion)
            self.assertEqual(v.retained_receipt["writes"],0)
        for criterion in ("states","accessibility","authn_authz","critical_e2e"):
            with self.subTest(criterion=criterion),self.assertRaises(ConsoleFullSurfaceEvidenceBlocked):
                result.criterion(criterion)

    def test_no_undocumented_field_can_leak_operator_or_trigger_pass(self):
        base=witness()
        self.assertEqual(set(base),FIELDS)
        for key,value in (
            ("operator_email","private@example.invalid"),
            ("token","secret"),
            ("fullStatesCertified",True),
            ("fullAccessibilityCertified",True),
            ("productionWrites",1),
            ("browserErrors",1),
            ("failedResources",1),
            ("mobileDetailVerified",False),
            ("desktopRoutes",len(NAMES)-1),
            ("routeNames",list(reversed(NAMES))),
            ("sourceCommit","d"*40),
            ("runId",RUN+1),
        ):
            x=copy.deepcopy(base);x[key]=value
            with self.subTest(key=key),self.assertRaises(ConsoleFullSurfaceEvidenceBlocked):
                validate_surface_witness(x,run_id=RUN,source_sha=SHA)

    def test_unchanged_console_reuses_complete_pinned_capture_across_new_main_sha(self):
        data,registry,proof,_=fixture()
        data=copy.deepcopy(data)
        data[P+"/actions/runs/"+str(RUN)+"/artifacts?per_page=100"]["artifacts"][1]["workflow_run"]["head_sha"]=SERV
        registry=[{**registry[0],"source_commit":SERV}]
        proof=AuthenticatedConsoleEvidence(REPO,SHA,RUN,1,source_commit=SERV)
        payload={**witness(),"sourceCommit":SERV,"targetCommit":SERV}
        result=self.verify(data,registry,proof,payload)
        self.assertEqual(result.assessed_commit,SHA)
        self.assertEqual(result.receipt()["certifies"],["surface_inventory","responsive"])
        for change in ("source_mismatch","tree_drift","no_ancestry","wrong_registry"):
            candidate=copy.deepcopy(data)
            rows=copy.deepcopy(registry)
            evidence=copy.deepcopy(payload)
            if change=="source_mismatch":evidence["sourceCommit"]=SHA
            elif change=="tree_drift":candidate[P+"/git/trees/"+SHA+"?recursive=1"]["tree"][0]["sha"]="d"*40
            elif change=="no_ancestry":candidate[P+"/compare/"+SERV+"..."+SHA]["merge_base_commit"]["sha"]="d"*40
            else:rows[0]["source_commit"]=SHA
            with self.subTest(change=change),self.assertRaises(ConsoleFullSurfaceEvidenceBlocked):
                self.verify(candidate,rows,proof,evidence)

    def test_failed_capture_registry_or_artifact_never_promotes(self):
        data,rows,auth,artifact=fixture()
        cases=[]
        for change in ("expired","unowned","other_sha","duplicate","missing"):
            g=copy.deepcopy(data)
            records=g[P+"/actions/runs/"+str(RUN)+"/artifacts?per_page=100"]
            if change=="expired":records["artifacts"][1]["expired"]=True
            elif change=="unowned":records["artifacts"][1]["workflow_run"]["head_branch"]="evil"
            elif change=="other_sha":records["artifacts"][1]["workflow_run"]["head_sha"]="e"*40
            elif change=="duplicate":
                records["artifacts"].append(copy.deepcopy(records["artifacts"][1]))
                records["total_count"]=3
            else:
                records["artifacts"].pop();records["total_count"]=1
            cases.append((change,g,rows,auth))
        cases.append(("uncaptured",data,[{**rows[0],"status":"expired"}],auth))
        cases.append(("no_original_artifact",data,rows,
                      AuthenticatedConsoleEvidence(REPO,SHA,RUN,None)))
        for label,g,r,p in cases:
            with self.subTest(label=label),self.assertRaises(ConsoleFullSurfaceEvidenceBlocked):
                self.verify(g,r,p)

    def test_console_drift_and_ancestry_are_fatal(self):
        data,rows,auth,_=fixture()
        g=copy.deepcopy(data)
        g[P+"/git/trees/"+SHA+"?recursive=1"]["tree"][0]["sha"]="f"*40
        with self.assertRaises(ConsoleFullSurfaceEvidenceBlocked):
            self.verify(g,rows,auth)
        g=copy.deepcopy(data)
        g[P+"/compare/"+SERV+"..."+SHA]["merge_base_commit"]["sha"]="d"*40
        with self.assertRaises(ConsoleFullSurfaceEvidenceBlocked):
            self.verify(g,rows,auth)

    def test_artifact_request_never_forwards_bearer_to_redirect_url(self):
        import urllib.error
        import urllib.request

        good="https://capture.blob.core.windows.net/archive?sig=fake"
        class FakeOpener:
            def open(self,request,timeout):
                self_request.append(request)
                raise urllib.error.HTTPError(request.full_url,302,"redirect",{"Location":good},None)
        self_request=[]
        def fake_second(request,timeout):
            self_request.append(request)
            archive=io.BytesIO()
            with zipfile.ZipFile(archive,"w") as z:
                z.writestr(ARTIFACT_FILE,json.dumps(witness()))
            return io.BytesIO(archive.getvalue())

        with patch("ai_product_factory.independent_complete_console_evidence.urllib.request.build_opener",return_value=FakeOpener()), \
             patch("ai_product_factory.independent_complete_console_evidence.urllib.request.urlopen",side_effect=fake_second):
            result=read_verified_artifact_json(
                repository=REPO,artifact_id=22,token="synthetic-token-never-to-redirect",
            )
        self.assertEqual(result,witness())
        self.assertEqual(len(self_request),2)
        self.assertIn("Bearer",self_request[0].get_header("Authorization"))
        self.assertIsNone(self_request[1].get_header("Authorization"))
        self.assertTrue(self_request[1].full_url.startswith("https://capture.blob.core.windows.net/"))

    def test_unsafe_signed_redirect_fails_before_request(self):
        import urllib.error
        class FakeOpener:
            def open(self,request,timeout):
                raise urllib.error.HTTPError(request.full_url,302,"redirect",
                    {"Location":"https://attacker.example.com/artifact.zip"},None)
        with patch("ai_product_factory.independent_complete_console_evidence.urllib.request.build_opener",return_value=FakeOpener()),\
             patch("ai_product_factory.independent_complete_console_evidence.urllib.request.urlopen",side_effect=AssertionError("untrusted host contacted")):
            with self.assertRaises(ConsoleFullSurfaceEvidenceBlocked):
                read_verified_artifact_json(repository=REPO,artifact_id=22,token="synthetic")

    def test_capture_proof_is_after_actual_browser_gate_and_before_success(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        capture=(root/"scripts/capture_authenticated_console.mjs").read_text()
        workflow=(root/".github/workflows/authenticated-visual-evidence.yml").read_text()
        self.assertLess(capture.index("if (consoleErrors.length || pageErrors.length || badResponses.length)"),
                        capture.index('block1-b3-completed-surface-witness.json'))
        self.assertIn('requiresIndependentAuthenticatedArtifactReview:true',
                      (root/"scripts/console_surface_coverage_contract.mjs").read_text())
        self.assertIn("if: steps.capture_console.outcome == 'success'",workflow)
        self.assertIn("Finalize registry and remove ephemeral operator",workflow)
        self.assertNotIn('on:\n  push:\n    branches: [main]\n    paths:\n      - "scripts/"',workflow)


if __name__=="__main__":
    unittest.main()
