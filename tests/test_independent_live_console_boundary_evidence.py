from __future__ import annotations

import copy
import unittest
from pathlib import Path

from ai_product_factory.independent_authenticated_console_evidence import AuthenticatedConsoleEvidence
from ai_product_factory.independent_complete_console_evidence import VerifiedConsoleSurface
from ai_product_factory.independent_live_console_boundary_evidence import (
    B2_FILE, B2_NAME, B2_ROUTES, B3_FILE, B3_NAME, B3_LIVE_FILE, B3_LIVE_NAME,
    LiveConsoleBoundaryEvidenceBlocked, validate_b2_witness, validate_b3_witness,
    validate_b3_live_witness,
    verify_live_console_boundaries,
)

REPO="leandrosilveiradepaula/ai-product-factory"
SHA="a" * 40
RUN=412345
P="/repos/" + REPO


def b2():
    return {
        "schema":"factory-b2-live-console-witness-sanitized-v1", "runId":RUN,
        "sourceCommit":SHA, "targetCommit":SHA,
        "checks":{"anonymousRoutes":[{"route":x,"denied":True} for x in B2_ROUTES],
                  "anonymousApiDenied":True,"operatorReadOnlyApiAllowed":True,
                  "operatorAdminPageDenied":True,"invalidSessionRouteDenied":True,
                  "invalidSessionApiDenied":True},
        "scope":"authenticated_http_route_witness_only",
        "authorizationBoundaryCertified":False,"crossTenantIsolationCertified":False,
        "signedJwtClaimsIndependentlyVerified":False,"visualAuditPassed":False,
        "credentialOrUserDataRetained":False,"productionWrites":0,"paidCalls":0,
    }


def b3():
    return {
        "schema":"factory-b3-authenticated-ui-state-fixture-v1", "runId":RUN,
        "sourceCommit":SHA, "targetCommit":SHA,
        "checks":{"pending":True,"unavailable":True,"cleared":True,"malformed":True},
        "scope":"authenticated_browser_with_intercepted_get_responses_only",
        "actualBackendStateCertified":False,"fullUserExperienceCertified":False,
        "independentCriterionCertified":False,"visualAuditPassed":False,
        "expected503ResourceConsoleErrors":1,"productionWrites":0,"paidCalls":0,
        "credentialOrUserDataRetained":False,
    }


def b3_live():
    return {
        "schema":"factory-b3-live-console-state-observation-v1", "runId":RUN,
        "sourceCommit":SHA, "targetCommit":SHA, "endpoint":"/api/human-attention",
        "httpStatus":200, "state":"available", "countClass":"positive",
        "actualBackendStateObserved":True, "fullUserExperienceCertified":False,
        "independentCriterionCertified":False, "visualAuditPassed":False,
        "responseBodyRetained":False, "projectsRetained":False,
        "productionWrites":0, "paidCalls":0, "credentialOrUserDataRetained":False,
    }


def artifacts():
    def row(artifact_id,name):
        return {"id":artifact_id,"name":name,"expired":False,
                "workflow_run":{"id":RUN,"head_branch":"main","head_sha":SHA}}
    return {P + "/actions/runs/" + str(RUN) + "/artifacts?per_page=100":{
        "total_count":3,"artifacts":[row(11,B2_NAME+str(RUN)),row(12,B3_NAME+str(RUN)),
                                       row(13,B3_LIVE_NAME+str(RUN))]
    }}


class LiveConsoleBoundaryEvidenceTests(unittest.TestCase):
    def test_validators_reject_overclaims_and_private_fields(self):
        validate_b2_witness(b2(),run_id=RUN,source_sha=SHA)
        validate_b3_witness(b3(),run_id=RUN,source_sha=SHA)
        validate_b3_live_witness(b3_live(),run_id=RUN,source_sha=SHA)
        for patch in (
            {"authorizationBoundaryCertified":True},
            {"crossTenantIsolationCertified":True},
            {"signedJwtClaimsIndependentlyVerified":True},
            {"productionWrites":1},
            {"paidCalls":1},
            {"scope":"full_production_security_certification"},
            {"operator_email":"private@example.invalid"},
        ):
            value={**b2(),**patch}
            with self.subTest(patch=patch), self.assertRaises(LiveConsoleBoundaryEvidenceBlocked):
                validate_b2_witness(value,run_id=RUN,source_sha=SHA)
        for patch in (
            {"actualBackendStateCertified":True}, {"paidCalls":1},
            {"checks":{"pending":True}}, {"token":"secret"},
        ):
            value={**b3(),**patch}
            with self.subTest(patch=patch), self.assertRaises(LiveConsoleBoundaryEvidenceBlocked):
                validate_b3_witness(value,run_id=RUN,source_sha=SHA)
        for patch in ({"projectsRetained":True},{"actualBackendStateObserved":False},
                      {"countClass":"unknown"},{"state":"unavailable"},{"token":"secret"}):
            value={**b3_live(),**patch}
            with self.subTest(patch=patch), self.assertRaises(LiveConsoleBoundaryEvidenceBlocked):
                validate_b3_live_witness(value,run_id=RUN,source_sha=SHA)

    def verify(self, github=None, reader=None):
        data=artifacts() if github is None else github
        payloads={11:b2(),12:b3(),13:b3_live()}
        return verify_live_console_boundaries(
            repository=REPO,assessed_commit=SHA,
            authenticated_capture=AuthenticatedConsoleEvidence(REPO,SHA,RUN,1),
            github_get=lambda path:data[path],
            artifact_reader=reader or (lambda repository,artifact_id,artifact_file: payloads[artifact_id]),
        )

    def test_exact_sha_artifacts_produce_bounded_receipt_only(self):
        result=self.verify()
        receipt=result.receipt()
        self.assertTrue(receipt["b2_dynamic_negative_routes_verified"])
        self.assertTrue(receipt["b3_fixture_transitions_verified"])
        self.assertTrue(receipt["b3_live_backend_state_observed"])
        self.assertEqual(receipt["does_not_certify"],[
            "authn_authz","data_access_boundaries","states","critical_e2e",
            "critical_journeys","product_ready"])
        self.assertEqual(receipt["writes"],0)

    def test_missing_optional_b3_does_not_destroy_valid_b2_proof(self):
        data=copy.deepcopy(artifacts())
        rows=data[P + "/actions/runs/" + str(RUN) + "/artifacts?per_page=100"]
        rows["artifacts"]=rows["artifacts"][:1]
        rows["total_count"]=1
        result=self.verify(github=data)
        self.assertIsNone(result.b3_artifact_id)
        self.assertIsNone(result.b3_live_artifact_id)

    def test_present_b3_artifact_must_be_valid_not_silently_downgraded(self):
        for mutate in ("invalid_payload", "expired", "duplicate", "source"):
            data=copy.deepcopy(artifacts())
            rows=data[P + "/actions/runs/" + str(RUN) + "/artifacts?per_page=100"]
            if mutate=="expired": rows["artifacts"][1]["expired"]=True
            elif mutate=="duplicate": rows["artifacts"].append(copy.deepcopy(rows["artifacts"][1])); rows["total_count"]+=1
            with self.subTest(mutate=mutate), self.assertRaises(LiveConsoleBoundaryEvidenceBlocked):
                self.verify(github=data,reader=lambda repository,artifact_id,artifact_file:
                            ({"bad":True} if mutate=="invalid_payload" and artifact_file==B3_FILE
                             else ({**b3(),"sourceCommit":"b"*40} if mutate=="source" and artifact_file==B3_FILE
                                   else (b2() if artifact_file==B2_FILE else (b3() if artifact_file==B3_FILE else b3_live())))))

    def test_b2_artifact_drift_or_expiry_blocks_all_boundary_proof(self):
        for mutate in ("expired","duplicate","source"):
            data=copy.deepcopy(artifacts())
            rows=data[P + "/actions/runs/" + str(RUN) + "/artifacts?per_page=100"]
            if mutate=="expired": rows["artifacts"][0]["expired"]=True
            elif mutate=="duplicate": rows["artifacts"].append(copy.deepcopy(rows["artifacts"][0])); rows["total_count"]+=1
            with self.subTest(mutate=mutate), self.assertRaises(LiveConsoleBoundaryEvidenceBlocked):
                self.verify(github=data,reader=lambda repository,artifact_id,artifact_file:
                            {**b2(),"sourceCommit":"b"*40} if mutate=="source" and artifact_file==B2_FILE else (b2() if artifact_file==B2_FILE else (b3() if artifact_file==B3_FILE else b3_live())))

    def test_ancestor_served_console_needs_independently_verified_identical_tree(self):
        served = "b" * 40
        payloads = {
            11:{**b2(),"targetCommit":served},
            12:{**b3(),"targetCommit":served},
            13:{**b3_live(),"targetCommit":served},
        }
        trusted = VerifiedConsoleSurface(REPO,SHA,RUN,served,88,source_commit=SHA)
        authenticated = AuthenticatedConsoleEvidence(REPO,SHA,RUN,1)
        git = artifacts()
        def verify(surface=None):
            return verify_live_console_boundaries(
                repository=REPO,assessed_commit=SHA,
                authenticated_capture=authenticated,github_get=lambda path:git[path],
                artifact_reader=lambda repository,artifact_id,artifact_file:payloads[artifact_id],
                surface=surface,
            )
        with self.assertRaises(LiveConsoleBoundaryEvidenceBlocked):
            verify()  # an arbitrary targetCommit cannot be trusted
        proof = verify(trusted)
        self.assertTrue(proof.receipt()["b2_dynamic_negative_routes_verified"])
        foreign = VerifiedConsoleSurface(REPO,"c"*40,RUN,served,88,source_commit=SHA)
        with self.assertRaises(LiveConsoleBoundaryEvidenceBlocked):
            verify(foreign)
        payloads[11]["targetCommit"] = SHA
        with self.assertRaises(LiveConsoleBoundaryEvidenceBlocked):
            verify(trusted)

    def test_unchanged_console_code_only_merge_reverifies_original_capture(self):
        # New assessed SHA, but the original browser B2/B3 proof belongs to
        # the verified captured source. Only a reverified full Console surface
        # and an authenticated source-bound capture permit provenance reuse.
        current = "d" * 40
        auth = AuthenticatedConsoleEvidence(REPO,current,RUN,1,source_commit=SHA)
        surface = VerifiedConsoleSurface(REPO,current,RUN,SHA,88,source_commit=SHA)
        payloads = {11:b2(),12:b3(),13:b3_live()}
        data = artifacts()
        def verify(auth_capture=auth, proven_surface=surface, rows=data):
            return verify_live_console_boundaries(
                repository=REPO,assessed_commit=current,
                authenticated_capture=auth_capture, surface=proven_surface,
                github_get=lambda path: rows[path],
                artifact_reader=lambda repository,artifact_id,artifact_file:payloads[artifact_id],
            )
        proof=verify()
        self.assertEqual((proof.assessed_commit,proof.run_id),(current,RUN))
        self.assertTrue(proof.receipt()["b2_dynamic_negative_routes_verified"])
        self.assertTrue(proof.receipt()["b3_fixture_transitions_verified"])
        self.assertTrue(proof.receipt()["b3_live_backend_state_observed"])
        with self.assertRaises(LiveConsoleBoundaryEvidenceBlocked):
            verify(proven_surface=None)  # source/served ancestry not proved
        with self.assertRaises(LiveConsoleBoundaryEvidenceBlocked):
            verify(proven_surface=VerifiedConsoleSurface(
                REPO,current,RUN,SHA,88,source_commit="c"*40))
        with self.assertRaises(LiveConsoleBoundaryEvidenceBlocked):
            verify(auth_capture=AuthenticatedConsoleEvidence(
                REPO,current,RUN,1,source_commit="c"*40))
        drift=copy.deepcopy(data)
        drift[P+"/actions/runs/"+str(RUN)+"/artifacts?per_page=100"]["artifacts"][0]["workflow_run"]["head_sha"]=current
        with self.assertRaises(LiveConsoleBoundaryEvidenceBlocked):
            verify(rows=drift)
        payloads[11]["targetCommit"]=current
        with self.assertRaises(LiveConsoleBoundaryEvidenceBlocked):
            verify()

    def test_pipeline_revalidates_only_a_fresh_authenticated_capture(self):
        root=Path(__file__).resolve().parents[1]
        workflow=(root/".github/workflows/autonomous-runner.yml").read_text()
        certifier=(root/"scripts/certify_product_readiness.py").read_text()
        builder=(root/"scripts/build_readiness_evidence_manifest.py").read_text()
        visual=(root/".github/workflows/authenticated-visual-evidence.yml").read_text()
        self.assertIn('boundary_args=(--verify-live-console-boundaries --verify-independent-b2-security)',workflow)
        self.assertIn('"${visual_args[@]}" "${boundary_args[@]}"',workflow)
        self.assertIn("live Console boundary receipt changed before persistence",certifier)
        self.assertIn("live Console boundaries require exact verified capture",certifier)
        self.assertIn("b3_live_artifact_id is not None",builder)
        self.assertIn("b3_live_artifact_id is not None",certifier)
        self.assertIn("block1-b3-live-state-${{ github.run_id }}",visual)


if __name__ == "__main__":
    unittest.main()
