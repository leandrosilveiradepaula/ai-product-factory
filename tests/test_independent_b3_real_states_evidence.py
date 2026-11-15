"""Adversarial B3 real-state provenance tests; fixtures are NOT live proof."""
import copy
from pathlib import Path
import unittest

from ai_product_factory.independent_authenticated_console_evidence import AuthenticatedConsoleEvidence
from ai_product_factory.independent_complete_console_evidence import VerifiedConsoleSurface
from ai_product_factory.independent_live_console_boundary_evidence import VerifiedLiveConsoleBoundaries
from ai_product_factory.independent_b3_real_states_evidence import (
    B3RealStatesBlocked,CHECKS,SOURCES,validate_real_states,verify_b3_real_states,
)

REPO="leandrosilveiradepaula/ai-product-factory"
SHA="a"*40
SERVED="b"*40
RUN=42345678901


def payload():
    return {
        "schema":"factory-b3-authenticated-live-state-matrix-v1",
        "runId":RUN,"sourceCommit":SHA,"targetCommit":SERVED,
        "checks":dict.fromkeys(CHECKS,True),
        "sources":dict(SOURCES),
        "backendStatus":200,"pendingHumanGateCount":0,"mutatingRequests":0,
        "interceptions":0,"unexpectedPageErrors":0,
        "productionWrites":0,"paidCalls":0,
        "personalDataRetained":False,"responsesFabricated":False,
        "backendOutageClaimed":False,"fullUserExperienceCertified":True,
        "independentCriterionCertified":False,
    }


def sources():
    return (
        AuthenticatedConsoleEvidence(REPO,SHA,RUN,None),
        VerifiedConsoleSurface(REPO,SHA,RUN,SERVED,11,source_commit=SHA),
        VerifiedLiveConsoleBoundaries(REPO,SHA,RUN,12,13,14),
    )


def execute(p=None,*,capture=None,surface=None,live=None,artifact=None):
    c,s,l=sources()
    if capture is not None:c=capture
    if surface is not None:s=surface
    if live is not None:l=live
    if artifact is None:
        artifact={"artifacts":[{
            "id":65,"name":"block1-b3-real-states-"+str(RUN),
            "expired":False,"workflow_run":{
                "id":RUN,"head_branch":"main","head_sha":SHA
            },
        }]}
    def github_get(path):
        if path!="/repos/"+REPO+"/actions/runs/"+str(RUN)+"/artifacts?per_page=100":
            raise AssertionError("untrusted GitHub path")
        return artifact
    def artifact_reader(**kwargs):
        if (kwargs.get("repository")!=REPO or kwargs.get("artifact_id")!=65
            or kwargs.get("artifact_file")!="block1-b3-real-states-witness.json"):
            raise AssertionError("wrong artifact identity")
        return p if p is not None else payload()
    return verify_b3_real_states(
        repository=REPO,assessed_commit=SHA,
        capture=c,surface=s,live_boundaries=l,
        github_get=github_get,artifact_reader=artifact_reader,
    )


class B3RealStateTests(unittest.TestCase):
    def test_complete_b3_proof_is_bound_to_authenticated_surface_and_live_boundary(self):
        result=execute()
        self.assertEqual(result.artifact_id,65)
        self.assertEqual(result.served_sha,SERVED)
        self.assertEqual(result.criterion().domain,"product_experience")
        self.assertEqual(result.criterion().criterion,"states")
        self.assertEqual(result.criterion().verification_state,"observed")
        self.assertEqual(result.criterion().evidence,
             ("https://github.com/"+REPO+"/actions/runs/"+str(RUN)+"#sha="+SHA,))
        self.assertEqual(result.receipt()["backend_outage_certified"],False)
        self.assertEqual(result.receipt()["checks"],list(CHECKS))

    def test_fixture_or_partial_state_matrix_cannot_be_certified(self):
        for mutation in (
            lambda p:p["checks"].update(empty=False),
            lambda p:p["checks"].pop("recovered"),
            lambda p:p["checks"].update(forged=True),
            lambda p:p["sources"].update(empty="intercepted_backend_get_fixture"),
            lambda p:p.update(schema="factory-b3-authenticated-ui-state-fixture-v1"),
            lambda p:p.update(backendStatus=503),
            lambda p:p.update(pendingHumanGateCount=1),
            lambda p:p.update(pendingHumanGateCount=-1),
            lambda p:p.update(pendingHumanGateCount=True),
            lambda p:p.update(pendingHumanGateCount="0"),
            lambda p:p.pop("pendingHumanGateCount"),
            lambda p:p.update(responsesFabricated=True),
            lambda p:p.update(interceptions=1),
            lambda p:p.update(mutatingRequests=1),
            lambda p:p.update(unexpectedPageErrors=1),
            lambda p:p.update(backendOutageClaimed=True),
            lambda p:p.update(independentCriterionCertified=True),
            lambda p:p.update(fullUserExperienceCertified=False),
            lambda p:p.update(personalDataRetained=True),
            lambda p:p.update(productionWrites=1),
            lambda p:p.update(paidCalls=1),
            lambda p:p.update(token="leaked"),
            lambda p:p.update(sourceCommit="c"*40),
            lambda p:p.update(targetCommit="d"*40),
            lambda p:p.update(runId=RUN+1),
        ):
            with self.subTest(mutation=mutation):
                item=payload()
                mutation(item)
                with self.assertRaises(B3RealStatesBlocked):
                    validate_real_states(item,run_id=RUN,source_sha=SHA,served_sha=SERVED)

    def test_the_browser_producer_schema_matches_independent_verifier(self):
        # Contracts must agree on the real artifact, not just separate fixtures.
        producer=(Path(__file__).resolve().parents[1]
                  /"scripts/verify_block1_b3_real_console_state_matrix.mjs").read_text()
        self.assertIn('empty:"authenticated_first_party_empty_human_decision_inbox"',producer)
        self.assertIn("backendStatus,pendingHumanGateCount,mutatingRequests",producer)
        self.assertIn("pendingHumanGateCount!==0",producer)
        self.assertEqual(payload()["sources"]["empty"],
                         "authenticated_first_party_empty_human_decision_inbox")
        self.assertEqual(payload()["pendingHumanGateCount"],0)
        validate_real_states(payload(),run_id=RUN,source_sha=SHA,served_sha=SERVED)

    def test_current_sha_and_artifact_provenance_are_mandatory(self):
        bad_artifact={"artifacts":[{
            "id":65,"name":"block1-b3-real-states-"+str(RUN),
            "expired":False,
            "workflow_run":{"id":RUN,"head_branch":"main","head_sha":"f"*40},
        }]}
        with self.assertRaises(B3RealStatesBlocked):
            execute(artifact=bad_artifact)

    def test_no_source_weakening_when_auth_surface_or_b3_live_missing(self):
        c,s,l=sources()
        variants=[
            dict(capture=AuthenticatedConsoleEvidence(REPO,SHA,RUN+1,None)),
            dict(surface=VerifiedConsoleSurface(REPO,SHA,RUN+1,SERVED,11,source_commit=SHA)),
            dict(live=VerifiedLiveConsoleBoundaries(REPO,SHA,RUN,12,None,14)),
            dict(live=VerifiedLiveConsoleBoundaries(REPO,SHA,RUN,12,13,None)),
            dict(surface=VerifiedConsoleSurface(REPO,SHA,RUN,SERVED,11,source_commit="d"*40)),
        ]
        for v in variants:
            with self.subTest(variant=v),self.assertRaises(B3RealStatesBlocked):
                execute(**v)


if __name__=="__main__":
    unittest.main()
