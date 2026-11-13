"""Fail-closed independent signed JWT, RBAC, RLS and data isolation proof tests."""
from __future__ import annotations
import copy
import unittest
from pathlib import Path
from ai_product_factory.independent_authenticated_console_evidence import AuthenticatedConsoleEvidence
from ai_product_factory.independent_live_console_boundary_evidence import VerifiedLiveConsoleBoundaries
from ai_product_factory.independent_complete_console_evidence import VerifiedConsoleSurface
from ai_product_factory.independent_isolated_console_auth_evidence import IsolatedConsoleAuthEvidence
from ai_product_factory.independent_b2_signed_security_evidence import (
    FILE, PREFIX, REPO, TABLES, SCHEMA, SCOPE, B2SignedSecurityBlocked,
    validate_real_b2_receipt, verify_independent_signed_b2,
)
from ai_product_factory.product_readiness_certification import VerifiedCriterionEvidence
SHA="a"*40
RUN=43289096088
PG_RUN=43299824634
def receipt():
    return {
        "schema":SCHEMA,"runId":RUN,"sourceCommit":SHA,"targetCommit":SHA,"scope":SCOPE,
        "checks":{
            "providerSignedUserVerified":True,"providerActorBoundToEphemeralOperator":True,
            "forgedSignatureRejected":True,"forgedRoleRejected":True,"forgedSubjectRejected":True,
            "activeOperatorOwnRowOnly":True,"anonymousOperatorDirectoryDenied":True,
            "anonymousProjectDataDenied":True,"untrustedControlPlaneTablesDenied":len(TABLES),
        },
        "checkedTables":list(TABLES),
        "privilegedRpcDenialSource":"independent_exact_tree_isolated_postgres",
        "independentTenantModelClaimed":False,"productionWrites":0,
        "mutatingRequests":0,"paidCalls":0,"personalDataRetained":False,
    }
def artifact():
    return {"id":100,"name":PREFIX+str(RUN),"size_in_bytes":1200,"expired":False,
            "workflow_run":{"id":RUN,"head_sha":SHA,"head_branch":"main"}}
def sources():
    auth=AuthenticatedConsoleEvidence(REPO,SHA,RUN,11)
    live=VerifiedLiveConsoleBoundaries(REPO,SHA,RUN,12,None,None)
    pg=IsolatedConsoleAuthEvidence(REPO,SHA,PG_RUN,"b"*40)
    secrets=VerifiedCriterionEvidence(
        "security","secrets_dependencies",REPO,SHA,"executed",
        "independent signed secrets scanner",
        ("https://github.com/"+REPO+"/actions/runs/1#sha="+SHA,),
    )
    return auth,live,pg,secrets
class B2SignedSourcesTests(unittest.TestCase):
    def verify(self,*,value=None,meta=None,src=None,surface=None):
        au,lv,pg,secret=src or sources()
        row=receipt() if value is None else value
        art=artifact() if meta is None else meta
        return verify_independent_signed_b2(
            repository=REPO,assessed_commit=SHA,
            authenticated_capture=au,live_routes=lv,isolated_pg=pg,
            secrets_proof=secret,
            surface=surface or VerifiedConsoleSurface(REPO,SHA,RUN,SHA,13,source_commit=SHA),
            github_get=lambda _:{"total_count":1,"artifacts":[art]},
            artifact_reader=lambda repository,artifact_id,artifact_file:
              row if artifact_id==100 and artifact_file==FILE else self.fail("unexpected source"),
        )
    def test_both_b2_claims_are_strictly_scoped_to_one_real_organization(self):
        proof=self.verify()
        self.assertTrue(proof.receipt()["single_organization_portfolio_scope"])
        self.assertFalse(proof.receipt()["independent_multi_tenant_operator_partition_claimed"])
        self.assertEqual(proof.receipt()["writes"],0)
        for name in ("authn_authz","data_access_boundaries"):
            c=proof.criterion(name)
            self.assertIs(type(c),VerifiedCriterionEvidence)
            self.assertEqual((c.domain,c.criterion,c.verification_state),
                             ("security",name,"executed"))
            self.assertEqual(len(c.evidence),2)
            self.assertTrue(all(SHA in link for link in c.evidence))
            self.assertEqual(c.retained_receipt["criterion"],name)
        with self.assertRaises(B2SignedSecurityBlocked):
            proof.criterion("critical_e2e")
    def test_receipt_tampering_missing_checks_and_overclaims_fail_closed(self):
        for key,value in (
            ("sourceCommit","b"*40),("targetCommit","b"*40),("runId",RUN+1),
            ("scope","full_multi_tenant_certification"),("checkedTables",[]),
            ("independentTenantModelClaimed",True),("productionWrites",1),
            ("mutatingRequests",1),("paidCalls",1),("personalDataRetained",True),
            ("token","private-not-for-evidence"),
        ):
            with self.subTest(key=key),self.assertRaises(B2SignedSecurityBlocked):
                validate_real_b2_receipt({**receipt(),key:value},run_id=RUN,source_sha=SHA)
        for name,value in [
            ("providerSignedUserVerified",False),("forgedSignatureRejected",False),
            ("forgedRoleRejected",False),("forgedSubjectRejected",False),
            ("activeOperatorOwnRowOnly",False),
            ("anonymousOperatorDirectoryDenied",False),
            ("untrustedControlPlaneTablesDenied",len(TABLES)-1),
        ]:
            row=receipt();row["checks"][name]=value
            with self.subTest(check=name),self.assertRaises(B2SignedSecurityBlocked):
                validate_real_b2_receipt(row,run_id=RUN,source_sha=SHA)
    def test_bad_artifacts_and_source_identity_fail_closed(self):
        for key,value in (
            ("expired",True),("id",0),("size_in_bytes",2),
            ("workflow_run",{"id":RUN+1,"head_sha":SHA,"head_branch":"main"}),
        ):
            with self.subTest(key=key),self.assertRaises(B2SignedSecurityBlocked):
                self.verify(meta={**artifact(),key:value})
        au,lv,pg,secret=sources()
        wrong=VerifiedLiveConsoleBoundaries(REPO,SHA,RUN+1,12,None,None)
        with self.assertRaises(B2SignedSecurityBlocked):
            self.verify(src=(au,wrong,pg,secret))
        wrongPg=IsolatedConsoleAuthEvidence(REPO,"c"*40,PG_RUN,"b"*40)
        with self.assertRaises(B2SignedSecurityBlocked):
            self.verify(src=(au,lv,wrongPg,secret))
    def test_served_ancestor_sha_requires_full_source_verified_surface(self):
        old = "b" * 40
        trusted = VerifiedConsoleSurface(REPO,SHA,RUN,old,99,source_commit=SHA)
        value = {**receipt(),"targetCommit":old}
        proof = self.verify(value=value,surface=trusted)
        self.assertEqual(proof.criterion("authn_authz").criterion,"authn_authz")
        with self.assertRaises(B2SignedSecurityBlocked):
            self.verify(value=value) # no verified served SHA
        with self.assertRaises(B2SignedSecurityBlocked):
            self.verify(surface=trusted) # artifact source reports wrong target SHA

    def test_signed_provider_receipt_reuses_only_immutable_original_source(self):
        # Both stages reverify the *same* signed Auth/denial receipt. The
        # assessment SHA changes, but the capture and browser bytes do not.
        current = "d" * 40
        capture = AuthenticatedConsoleEvidence(REPO,current,RUN,11,source_commit=SHA)
        live = VerifiedLiveConsoleBoundaries(REPO,current,RUN,12,None,None)
        isolated = IsolatedConsoleAuthEvidence(REPO,current,PG_RUN,"b"*40)
        security = VerifiedCriterionEvidence(
            "security","secrets_dependencies",REPO,current,"executed",
            "independent current SHA secrets verification",
            ("https://github.com/"+REPO+"/actions/runs/1#sha="+current,),
        )
        original_surface = VerifiedConsoleSurface(
            REPO,current,RUN,SHA,13,source_commit=SHA)
        def verify(surface=original_surface,metadata=None,payload=None):
            return verify_independent_signed_b2(
                repository=REPO,assessed_commit=current,
                authenticated_capture=capture,live_routes=live,
                isolated_pg=isolated,secrets_proof=security,surface=surface,
                github_get=lambda _:{"total_count":1,"artifacts":[
                    artifact() if metadata is None else metadata]},
                artifact_reader=lambda **_:receipt() if payload is None else payload,
            )
        passed=verify()
        self.assertEqual(passed.criterion("authn_authz").assessed_commit,current)
        self.assertEqual(passed.criterion("data_access_boundaries").assessed_commit,current)
        self.assertEqual(passed.receipt()["workflow_run_id"],RUN)
        with self.assertRaises(B2SignedSecurityBlocked):
            verify(surface=VerifiedConsoleSurface(REPO,current,RUN,SHA,13,source_commit=current))
        with self.assertRaises(B2SignedSecurityBlocked):
            verify(metadata={**artifact(),"workflow_run":{
                "id":RUN,"head_sha":current,"head_branch":"main"}})
        with self.assertRaises(B2SignedSecurityBlocked):
            verify(payload={**receipt(),"sourceCommit":current})
        with self.assertRaises(B2SignedSecurityBlocked):
            verify(payload={**receipt(),"checks":{
                **receipt()["checks"],"forgedSignatureRejected":False}})

    def test_missing_source_cannot_promote_partial_to_pass(self):
        au,lv,pg,secret=sources()
        p=verify_independent_signed_b2(
            repository=REPO,assessed_commit=SHA,authenticated_capture=au,
            live_routes=lv,isolated_pg=pg,secrets_proof=secret,
            surface=VerifiedConsoleSurface(REPO,SHA,RUN,SHA,13,source_commit=SHA),
            github_get=lambda _:{"total_count":0,"artifacts":[]},
            artifact_reader=lambda **_:self.fail("missing must not fetch"),
        )
        self.assertIsNone(p)
    def test_runner_verifier_and_capture_are_bound_together(self):
        root=Path(__file__).resolve().parents[1]
        build=(root/"scripts/build_readiness_evidence_manifest.py").read_text()
        persist=(root/"scripts/certify_product_readiness.py").read_text()
        runner=(root/".github/workflows/autonomous-runner.yml").read_text()
        workflow=(root/".github/workflows/authenticated-visual-evidence.yml").read_text()
        capture=(root/"scripts/capture_authenticated_console.mjs").read_text()
        producer=(root/"scripts/verify_block1_b2_live_supabase.mjs").read_text()
        self.assertIn("verify_independent_signed_b2(",build)
        self.assertIn("verify_independent_signed_b2(",persist)
        self.assertIn("B2 independent receipt changed before persistence",persist)
        self.assertEqual(runner.count("--verify-independent-b2-security"),2)
        self.assertIn("block1-b2-supabase-security-"+"$"+"{{ github.run_id }}",workflow)
        self.assertIn("verifyLiveSupabaseBoundaries(",capture)
        self.assertIn("forgedSignatureRejected:true",producer)
        self.assertIn("independentTenantModelClaimed:false",producer)
        self.assertIn("mutatingRequests:0",producer)
if __name__=="__main__":
    unittest.main()
