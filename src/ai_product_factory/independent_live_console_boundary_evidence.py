"""Independent, fail-closed review of bounded B2/B3 browser witnesses.

The witnesses prove only the exact dynamic checks performed by the protected
browser workflow.  They deliberately cannot certify signed-JWT validation,
tenant isolation, complete accessibility, backend error states, critical E2E,
or product readiness.
"""
from __future__ import annotations

from dataclasses import dataclass

from .independent_authenticated_console_evidence import AuthenticatedConsoleEvidence
from .independent_complete_console_evidence import REPO, SHA

B2_FILE = "block1-b2-live-boundary-witness.json"
B3_FILE = "block1-b3-console-state-witness.json"
B2_NAME = "block1-b2-live-boundary-"
B3_NAME = "block1-b3-ui-states-"
B2_ROUTES = (
    "/", "/projects", "/runs", "/projects/new", "/gates",
    "/runs/93fd8cdc-f000-4a01-978e-463798628e4e", "/queue", "/agents",
    "/orchestration", "/evals", "/deployments", "/usage", "/audit",
    "/configuration", "/admin/operators",
)


class LiveConsoleBoundaryEvidenceBlocked(RuntimeError):
    """Fixed internal codes only; never provider, browser, or user data."""


def _identity(payload: object, *, run_id: int, source_sha: str, schema: str,
              fields: frozenset[str]) -> dict:
    if not isinstance(payload, dict) or set(payload) != fields:
        raise LiveConsoleBoundaryEvidenceBlocked("live_witness_shape_invalid")
    if (payload.get("schema") != schema or type(payload.get("runId")) is not int
            or payload["runId"] != run_id or payload.get("sourceCommit") != source_sha
            or payload.get("targetCommit") != source_sha):
        raise LiveConsoleBoundaryEvidenceBlocked("live_witness_identity_invalid")
    return payload


B2_FIELDS = frozenset({
    "schema", "runId", "sourceCommit", "targetCommit", "checks", "scope",
    "authorizationBoundaryCertified", "crossTenantIsolationCertified",
    "signedJwtClaimsIndependentlyVerified", "visualAuditPassed",
    "credentialOrUserDataRetained", "productionWrites",
})
B3_FIELDS = frozenset({
    "schema", "runId", "sourceCommit", "targetCommit", "checks", "scope",
    "actualBackendStateCertified", "fullUserExperienceCertified",
    "independentCriterionCertified", "visualAuditPassed",
    "expected503ResourceConsoleErrors", "productionWrites", "paidCalls",
    "credentialOrUserDataRetained",
})


def validate_b2_witness(payload: object, *, run_id: int, source_sha: str) -> None:
    row = _identity(payload, run_id=run_id, source_sha=source_sha,
                    schema="factory-b2-live-console-witness-sanitized-v1", fields=B2_FIELDS)
    checks = row["checks"]
    if (not isinstance(checks, dict) or set(checks) != {
        "anonymousRoutes", "anonymousApiDenied", "operatorReadOnlyApiAllowed",
        "operatorAdminPageDenied", "invalidSessionRouteDenied", "invalidSessionApiDenied",
    } or checks["anonymousRoutes"] != [{"route": route, "denied": True} for route in B2_ROUTES]
            or any(checks[key] is not True for key in set(checks) - {"anonymousRoutes"})):
        raise LiveConsoleBoundaryEvidenceBlocked("live_b2_checks_invalid")
    for key in ("authorizationBoundaryCertified", "crossTenantIsolationCertified",
                "signedJwtClaimsIndependentlyVerified", "visualAuditPassed"):
        if row[key] is not False:
            raise LiveConsoleBoundaryEvidenceBlocked("live_b2_overclaim")
    if (row["credentialOrUserDataRetained"] is not False
            or row["productionWrites"] != 0):
        raise LiveConsoleBoundaryEvidenceBlocked("live_b2_safety_invalid")


def validate_b3_witness(payload: object, *, run_id: int, source_sha: str) -> None:
    row = _identity(payload, run_id=run_id, source_sha=source_sha,
                    schema="factory-b3-authenticated-ui-state-fixture-v1", fields=B3_FIELDS)
    if (row["checks"] != {"pending": True, "unavailable": True, "cleared": True, "malformed": True}
            or row["scope"] != "authenticated_browser_with_intercepted_get_responses_only"
            or any(row[key] is not False for key in (
                "actualBackendStateCertified", "fullUserExperienceCertified",
                "independentCriterionCertified", "visualAuditPassed",
                "credentialOrUserDataRetained"))
            or type(row["expected503ResourceConsoleErrors"]) is not int
            or row["expected503ResourceConsoleErrors"] < 0
            or row["productionWrites"] != 0 or row["paidCalls"] != 0):
        raise LiveConsoleBoundaryEvidenceBlocked("live_b3_fixture_invalid")


def _artifact(github_get, *, repository: str, run_id: int, source_sha: str, name: str) -> int:
    rows = github_get("/repos/" + repository + "/actions/runs/" + str(run_id) + "/artifacts?per_page=100")
    artifacts = rows.get("artifacts") if isinstance(rows, dict) else None
    found = [row for row in artifacts or [] if isinstance(row, dict) and row.get("name") == name]
    if len(found) != 1:
        raise LiveConsoleBoundaryEvidenceBlocked("live_artifact_absent")
    row = found[0]
    provenance = row.get("workflow_run")
    if (type(row.get("id")) is not int or row["id"] < 1 or row.get("expired") is not False
            or not isinstance(provenance, dict) or provenance.get("id") != run_id
            or provenance.get("head_branch") != "main" or provenance.get("head_sha") != source_sha):
        raise LiveConsoleBoundaryEvidenceBlocked("live_artifact_provenance_invalid")
    return row["id"]


@dataclass(frozen=True)
class VerifiedLiveConsoleBoundaries:
    repository: str
    assessed_commit: str
    run_id: int
    b2_artifact_id: int
    b3_artifact_id: int | None

    def receipt(self) -> dict:
        return {
            "schema": "factory-block1-live-boundaries-proof-v1",
            "repository": self.repository, "assessed_commit": self.assessed_commit,
            "workflow_run_id": self.run_id, "b2_artifact_id": self.b2_artifact_id,
            "b3_fixture_artifact_id": self.b3_artifact_id,
            "b2_dynamic_negative_routes_verified": True,
            "b3_fixture_transitions_verified": self.b3_artifact_id is not None,
            "does_not_certify": ["authn_authz", "data_access_boundaries", "states",
                                "critical_e2e", "critical_journeys", "product_ready"],
            "writes": 0, "paid_calls": 0,
        }


def verify_live_console_boundaries(*, repository: str, assessed_commit: str,
                                   authenticated_capture: AuthenticatedConsoleEvidence,
                                   github_get, artifact_reader) -> VerifiedLiveConsoleBoundaries:
    if (not REPO.fullmatch(repository) or not SHA.fullmatch(assessed_commit)
            or not isinstance(authenticated_capture, AuthenticatedConsoleEvidence)
            or authenticated_capture.repository != repository
            or authenticated_capture.assessed_commit != assessed_commit
            or authenticated_capture.source_commit not in (None, assessed_commit)):
        raise LiveConsoleBoundaryEvidenceBlocked("live_capture_identity_invalid")
    run_id = authenticated_capture.workflow_run_id
    if type(run_id) is not int or run_id < 1:
        raise LiveConsoleBoundaryEvidenceBlocked("live_capture_run_invalid")
    b2_id = _artifact(github_get, repository=repository, run_id=run_id,
                      source_sha=assessed_commit, name=B2_NAME + str(run_id))
    validate_b2_witness(artifact_reader(repository=repository, artifact_id=b2_id, artifact_file=B2_FILE),
                        run_id=run_id, source_sha=assessed_commit)
    b3_id = None
    try:
        candidate = _artifact(github_get, repository=repository, run_id=run_id,
                              source_sha=assessed_commit, name=B3_NAME + str(run_id))
        validate_b3_witness(artifact_reader(repository=repository, artifact_id=candidate, artifact_file=B3_FILE),
                            run_id=run_id, source_sha=assessed_commit)
        b3_id = candidate
    except LiveConsoleBoundaryEvidenceBlocked:
        # B2 remains independently useful if B3 fixture output is unavailable.
        b3_id = None
    return VerifiedLiveConsoleBoundaries(repository, assessed_commit, run_id, b2_id, b3_id)
