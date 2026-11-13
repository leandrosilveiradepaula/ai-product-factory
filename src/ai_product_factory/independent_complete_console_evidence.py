"""Independent fail-closed attestations for a COMPLETE authenticated Console audit.

Only surface inventory and responsive behavior can pass from this evidence.
Accessibility, UI error/loading/empty states, RBAC and critical E2E require
separate complete providers. The encrypted artifact is NEVER decrypted here.
The second, sanitized witness is downloaded with a scope-limited GitHub token;
the signed artifact redirect never receives that token.
"""
from __future__ import annotations

import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass

from .independent_authenticated_console_evidence import (
    AuthenticatedConsoleEvidence, AuthenticatedConsoleEvidenceBlocked, _console_blobs,
)
from .product_readiness_certification import VerifiedCriterionEvidence

SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z", re.ASCII)
ARTIFACT_FILE = "block1-b3-completed-surface-witness.json"
NAMES = (
    "overview", "projects", "runs", "new-project", "human-gates",
    "run-detail", "work-queue", "agents", "orchestration", "evals",
    "deployments", "models-usage", "audit-log", "configuration",
)
FIELDS = frozenset({
    "schema", "runId", "sourceCommit", "targetCommit", "desktopRoutes",
    "mobileRoutes", "accessibleRoutes", "routeNames", "mobileDetailVerified",
    "keyboardSkipVerified", "browserErrors", "pageErrors", "failedResources",
    "productionWrites", "paidCalls", "fullStatesCertified",
    "fullAccessibilityCertified", "criticalE2eCertified",
})

class ConsoleFullSurfaceEvidenceBlocked(RuntimeError):
    """Only fixed internal codes; never provider or operator data."""


@dataclass(frozen=True)
class VerifiedConsoleSurface:
    repository: str
    assessed_commit: str
    run_id: int
    target_commit: str
    artifact_id: int
    source_commit: str | None = None  # captured run SHA, not later identical Console source

    def receipt(self) -> dict:
        return {
            "schema": "factory-b3-full-surface-proof-v1",
            "repository": self.repository,
            "assessed_commit": self.assessed_commit,
            "workflow_run_id": self.run_id,
            "served_console_commit": self.target_commit,
            "artifact_id": self.artifact_id,
            "desktop_route_count": len(NAMES),
            "mobile_route_count": len(NAMES),
            "real_project_detail_on_mobile": True,
            "keyboard_skip_verified": True,
            "certifies": ["surface_inventory", "responsive"],
            "does_not_certify": [
                "accessibility", "states", "authn_authz",
                "data_access_boundaries", "critical_e2e", "critical_journeys",
                "product_ready",
            ],
            "writes": 0,
            "paid_calls": 0,
        }

    def criterion(self, name: str) -> VerifiedCriterionEvidence:
        if name not in ("surface_inventory", "responsive"):
            raise ConsoleFullSurfaceEvidenceBlocked("b3_unapproved_criterion")
        return VerifiedCriterionEvidence(
            domain="product_experience", criterion=name,
            repository=self.repository, assessed_commit=self.assessed_commit,
            verification_state="observed",
            source="independent_complete_browser_surface_witness",
            evidence=(
                "https://github.com/" + self.repository + "/actions/runs/"
                + str(self.run_id) + "#sha=" + self.assessed_commit,
            ),
            retained_receipt={**self.receipt(), "criterion": name},
        )

    def bounded_accessibility_evidence(self) -> tuple[str, ...]:
        """Real browser keyboard/semantic checks, deliberately not WCAG PASS."""
        return ("https://github.com/" + self.repository + "/actions/runs/"
                + str(self.run_id) + "#sha=" + self.assessed_commit,)


def validate_surface_witness(payload: object, *, run_id: int, source_sha: str) -> str:
    """Validate allowlisted, quantified output; never trust arbitrary JSON claims."""
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        raise ConsoleFullSurfaceEvidenceBlocked("b3_witness_shape_invalid")
    if (payload["schema"] != "factory-b3-completed-surface-witness-v1"
            or type(payload["runId"]) is not int or payload["runId"] != run_id
            or payload["sourceCommit"] != source_sha
            or not isinstance(payload["targetCommit"], str)
            or SHA.fullmatch(payload["targetCommit"]) is None
            or not isinstance(payload["routeNames"], list)
            or len(payload["routeNames"]) != len(NAMES)
            or tuple(payload["routeNames"]) != NAMES):
        raise ConsoleFullSurfaceEvidenceBlocked("b3_witness_identity_invalid")
    for key in ("desktopRoutes", "mobileRoutes", "accessibleRoutes"):
        if type(payload[key]) is not int or payload[key] != len(NAMES):
            raise ConsoleFullSurfaceEvidenceBlocked("b3_witness_coverage_missing")
    for key in ("mobileDetailVerified", "keyboardSkipVerified"):
        if payload[key] is not True:
            raise ConsoleFullSurfaceEvidenceBlocked("b3_witness_coverage_missing")
    for key in ("browserErrors", "pageErrors", "failedResources", "productionWrites", "paidCalls"):
        if type(payload[key]) is not int or payload[key] != 0:
            raise ConsoleFullSurfaceEvidenceBlocked("b3_witness_error_or_mutation")
    for key in ("fullStatesCertified", "fullAccessibilityCertified", "criticalE2eCertified"):
        if payload[key] is not False:
            raise ConsoleFullSurfaceEvidenceBlocked("b3_witness_overclaims")
    return payload["targetCommit"]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_verified_artifact_json(*, repository: str, artifact_id: int, token: str,
                                artifact_file: str = ARTIFACT_FILE) -> dict:
    if (not REPO.fullmatch(repository) or type(artifact_id) is not int
            or artifact_id < 1 or not isinstance(token, str) or not token):
        raise ConsoleFullSurfaceEvidenceBlocked("b3_artifact_request_invalid")
    if artifact_file not in {
        ARTIFACT_FILE,
        "block1-b2-live-boundary-witness.json",
        "block1-b2-supabase-security.json",
        "block1-b3-console-state-witness.json",
        "block1-b3-live-state-witness.json",
        "block1-b3-wcag-accessibility-witness.json",
    }:
        raise ConsoleFullSurfaceEvidenceBlocked("b3_artifact_file_unapproved")
    request = urllib.request.Request(
        "https://api.github.com/repos/" + repository + "/actions/artifacts/"
        + str(artifact_id) + "/zip",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        _NoRedirect()
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=20) as response:
            raise ConsoleFullSurfaceEvidenceBlocked("b3_artifact_redirect_missing")
    except urllib.error.HTTPError as exc:
        if exc.code not in (302, 303, 307):
            raise ConsoleFullSurfaceEvidenceBlocked("b3_artifact_unavailable") from None
        redirect = exc.headers.get("Location", "")
    parsed = urllib.parse.urlsplit(redirect)
    hostname = parsed.hostname or ""
    # An HTTPS-only Microsoft-hosted Actions result or GitHub-owned artifact
    # host is expected. Never attach the GitHub token to the signed URL.
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port
            or not (
                hostname.endswith(".blob.core.windows.net")
                or hostname.endswith(".actions.githubusercontent.com")
                or hostname.endswith(".githubusercontent.com")
            )):
        raise ConsoleFullSurfaceEvidenceBlocked("b3_artifact_redirect_untrusted")
    try:
        signed = urllib.request.Request(redirect, headers={"Accept": "application/zip"})
        with urllib.request.urlopen(signed, timeout=20) as response:
            archive = response.read(65537)
        if len(archive) > 65536:
            raise ConsoleFullSurfaceEvidenceBlocked("b3_artifact_too_large")
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            if zf.namelist() != [artifact_file]:
                raise ConsoleFullSurfaceEvidenceBlocked("b3_artifact_files_unexpected")
            info = zf.getinfo(artifact_file)
            if info.file_size > 8192 or info.file_size < 100:
                raise ConsoleFullSurfaceEvidenceBlocked("b3_artifact_file_invalid")
            data = zf.read(artifact_file)
    except (OSError, ValueError, zipfile.BadZipFile, urllib.error.URLError) as exc:
        raise ConsoleFullSurfaceEvidenceBlocked("b3_artifact_read_unavailable") from None
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise ConsoleFullSurfaceEvidenceBlocked("b3_artifact_json_invalid") from None


def verify_complete_console_surface(*, repository: str, assessed_commit: str,
                                    authenticated_capture: AuthenticatedConsoleEvidence,
                                    github_get, control_plane_get,
                                    artifact_reader) -> VerifiedConsoleSurface:
    if (not REPO.fullmatch(repository) or not SHA.fullmatch(assessed_commit)
            or not isinstance(authenticated_capture, AuthenticatedConsoleEvidence)
            or authenticated_capture.repository != repository
            or authenticated_capture.assessed_commit != assessed_commit
            or type(authenticated_capture.workflow_run_id) is not int
            or authenticated_capture.workflow_run_id < 1
            or (authenticated_capture.artifact_id is None
                and authenticated_capture.source_commit is None)):
        raise ConsoleFullSurfaceEvidenceBlocked("b3_original_capture_unverified")
    prefix = "/repos/" + repository
    run_id = authenticated_capture.workflow_run_id
    source_sha = authenticated_capture.source_commit or assessed_commit
    if not isinstance(source_sha, str) or SHA.fullmatch(source_sha) is None:
        raise ConsoleFullSurfaceEvidenceBlocked("b3_source_sha_invalid")
    artifacts = github_get(prefix + "/actions/runs/" + str(run_id) + "/artifacts?per_page=100")
    rows = artifacts.get("artifacts") if isinstance(artifacts, dict) else None
    if not isinstance(rows, list) or artifacts.get("total_count") != len(rows):
        raise ConsoleFullSurfaceEvidenceBlocked("b3_artifact_inventory_incomplete")
    name = "block1-b3-full-surface-" + str(run_id)
    matched = [x for x in rows if isinstance(x, dict) and x.get("name") == name]
    if len(matched) != 1:
        raise ConsoleFullSurfaceEvidenceBlocked("b3_full_surface_artifact_absent")
    a = matched[0]
    provenance = a.get("workflow_run") if isinstance(a, dict) else None
    if (type(a.get("id")) is not int or a["id"] < 1
            or a.get("expired") is not False
            or type(a.get("size_in_bytes")) is not int or not 100 <= a["size_in_bytes"] <= 65536
            or not isinstance(provenance, dict)
            or provenance.get("id") != run_id or provenance.get("head_sha") != source_sha
            or provenance.get("head_branch") != "main"):
        raise ConsoleFullSurfaceEvidenceBlocked("b3_artifact_provenance_invalid")
    rows = control_plane_get(
        "factory_visual_evidence_runs?select=workflow_run_id,source_commit,artifact_name,status"
        "&workflow_run_id=eq." + str(run_id) + "&limit=2"
    )
    if not isinstance(rows, list) or len(rows) != 1 or rows[0] != {
        "workflow_run_id": run_id,
        "source_commit": source_sha,
        "artifact_name": "authenticated-console-" + str(run_id),
        "status": "captured",
    }:
        raise ConsoleFullSurfaceEvidenceBlocked("b3_control_plane_capture_unverified")
    payload = artifact_reader(repository=repository, artifact_id=a["id"])
    served_sha = validate_surface_witness(payload, run_id=run_id, source_sha=source_sha)
    if served_sha != assessed_commit:
        comparison = github_get(prefix + "/compare/" + served_sha + "..." + assessed_commit)
        if (not isinstance(comparison, dict)
                or comparison.get("status") != "ahead"
                or comparison.get("behind_by") != 0
                or (comparison.get("base_commit") or {}).get("sha") != served_sha
                or (comparison.get("merge_base_commit") or {}).get("sha") != served_sha):
            raise ConsoleFullSurfaceEvidenceBlocked("b3_served_commit_not_ancestor")
        served_tree = github_get(prefix + "/git/trees/" + served_sha + "?recursive=1")
        current_tree = github_get(prefix + "/git/trees/" + assessed_commit + "?recursive=1")
        if _console_blobs(served_tree) != _console_blobs(current_tree):
            raise ConsoleFullSurfaceEvidenceBlocked("b3_served_console_not_identical")
    return VerifiedConsoleSurface(
        repository=repository, assessed_commit=assessed_commit, run_id=run_id,
        target_commit=served_sha, artifact_id=a["id"], source_commit=source_sha,
    )
