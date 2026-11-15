"""Independent B3 real backend and UI state verification on the served Console.

No intercepted GET fixture, GitHub CI status, Preview READY or arbitrary manifest
can issue the states PASS. The original browser capture must be authenticated,
successful, current-source-verified, complete on all routes, and retain an
independent real-transport multi-state artifact under that same run identity.
"""
from __future__ import annotations

from dataclasses import dataclass

from .independent_authenticated_console_evidence import AuthenticatedConsoleEvidence
from .independent_complete_console_evidence import VerifiedConsoleSurface, REPO, SHA
from .independent_live_console_boundary_evidence import (
    VerifiedLiveConsoleBoundaries, LiveConsoleBoundaryEvidenceBlocked, _artifact,
)
from .product_readiness_certification import VerifiedCriterionEvidence

ARTIFACT_FILE="block1-b3-real-states-witness.json"
ARTIFACT_NAME="block1-b3-real-states-"
CHECKS=("success","empty","loading","denied","notFound","connectionError","recovered")
SOURCES={
    "success":"authenticated_first_party_overview",
    "empty":"authenticated_first_party_empty_human_decision_inbox",
    "loading":"real_network_throttled_next_route_fallback",
    "denied":"authenticated_first_party_role_denial",
    "notFound":"first_party_run_existence_api_404_plus_not_found_ui",
    "connectionError":"actual_chromium_transport_disconnection",
    "recovered":"first_party_route_retry_after_reconnection",
}
FIELDS=frozenset({
    "schema","runId","sourceCommit","targetCommit","checks","sources",
    "backendStatus","pendingHumanGateCount","mutatingRequests","interceptions","unexpectedPageErrors",
    "productionWrites","paidCalls","personalDataRetained","responsesFabricated",
    "backendOutageClaimed","fullUserExperienceCertified","independentCriterionCertified",
})


class B3RealStatesBlocked(RuntimeError):
    """Only stable technical failure codes may reach logs."""


def validate_real_states(payload: object, *, run_id: int, source_sha: str,
                         served_sha: str) -> None:
    if not isinstance(payload,dict) or set(payload)!=FIELDS:
        raise B3RealStatesBlocked("b3_real_states_shape_invalid")
    if (payload["schema"]!="factory-b3-authenticated-live-state-matrix-v1"
        or type(payload["runId"]) is not int or payload["runId"]!=run_id
        or payload["sourceCommit"]!=source_sha
        or payload["targetCommit"]!=served_sha
        or not isinstance(source_sha,str) or SHA.fullmatch(source_sha) is None
        or not isinstance(served_sha,str) or SHA.fullmatch(served_sha) is None):
        raise B3RealStatesBlocked("b3_real_states_source_mismatch")
    if (type(payload["checks"]) is not dict
        or set(payload["checks"])!=set(CHECKS)
        or any(payload["checks"][key] is not True for key in CHECKS)
        or payload["sources"]!=SOURCES):
        raise B3RealStatesBlocked("b3_real_states_coverage_not_live")
    if (type(payload["backendStatus"]) is not int or payload["backendStatus"]!=200
        or any(type(payload[key]) is not int or payload[key]!=0 for key in (
            "pendingHumanGateCount",
            "mutatingRequests","interceptions","unexpectedPageErrors",
            "productionWrites","paidCalls"))
        or any(payload[key] is not False for key in (
            "personalDataRetained","responsesFabricated","backendOutageClaimed",
            "independentCriterionCertified"))
        or payload["fullUserExperienceCertified"] is not True):
        raise B3RealStatesBlocked("b3_real_states_safety_or_overclaim")


@dataclass(frozen=True)
class VerifiedB3RealStates:
    repository: str
    assessed_commit: str
    run_id: int
    artifact_id: int
    served_sha: str
    source_sha: str

    def receipt(self)->dict:
        return {
            "schema":"factory-independent-b3-live-state-criterion-v1",
            "repository":self.repository,
            "assessed_commit":self.assessed_commit,
            "source_commit":self.source_sha,
            "served_console_commit":self.served_sha,
            "workflow_run_id":self.run_id,
            "artifact_id":self.artifact_id,
            "checks":list(CHECKS),
            "backend_outage_certified":False,
            "production_writes":0,
            "paid_calls":0,
        }

    def criterion(self)->VerifiedCriterionEvidence:
        return VerifiedCriterionEvidence(
            domain="product_experience",criterion="states",
            repository=self.repository,assessed_commit=self.assessed_commit,
            verification_state="observed",
            source="independent_exact_sha_authenticated_real_state_matrix",
            evidence=("https://github.com/"+self.repository+"/actions/runs/"
                      +str(self.run_id)+"#sha="+self.assessed_commit,),
            retained_receipt=self.receipt(),
        )


def verify_b3_real_states(*,repository:str,assessed_commit:str,
                          capture:AuthenticatedConsoleEvidence,
                          surface:VerifiedConsoleSurface,
                          live_boundaries:VerifiedLiveConsoleBoundaries,
                          github_get,artifact_reader)->VerifiedB3RealStates:
    if (not REPO.fullmatch(repository) or not SHA.fullmatch(assessed_commit)
        or type(capture) is not AuthenticatedConsoleEvidence
        or type(surface) is not VerifiedConsoleSurface
        or type(live_boundaries) is not VerifiedLiveConsoleBoundaries
        or any(x.repository!=repository or x.assessed_commit!=assessed_commit
               for x in (capture,surface,live_boundaries))
        or len({capture.workflow_run_id,surface.run_id,live_boundaries.run_id})!=1
        or live_boundaries.b3_live_artifact_id is None
        or live_boundaries.b3_artifact_id is None
        or not isinstance(surface.target_commit,str)
        or SHA.fullmatch(surface.target_commit) is None):
        raise B3RealStatesBlocked("b3_real_states_auth_capture_or_surface_missing")
    source_sha=capture.source_commit or assessed_commit
    if surface.source_commit not in (None,source_sha):
        raise B3RealStatesBlocked("b3_real_states_auth_source_changed")
    try:
        artifact_id=_artifact(
            github_get,repository=repository,run_id=capture.workflow_run_id,
            source_sha=source_sha,
            name=ARTIFACT_NAME+str(capture.workflow_run_id),
        )
    except LiveConsoleBoundaryEvidenceBlocked as exc:
        raise B3RealStatesBlocked("b3_real_states_artifact_provenance_missing") from exc
    payload=artifact_reader(repository=repository,artifact_id=artifact_id,
                            artifact_file=ARTIFACT_FILE)
    validate_real_states(payload,run_id=capture.workflow_run_id,
                         source_sha=source_sha,served_sha=surface.target_commit)
    return VerifiedB3RealStates(
        repository=repository,assessed_commit=assessed_commit,
        run_id=capture.workflow_run_id,artifact_id=artifact_id,
        served_sha=surface.target_commit,source_sha=source_sha,
    )
