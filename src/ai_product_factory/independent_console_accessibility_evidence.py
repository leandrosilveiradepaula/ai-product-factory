"""Fail-closed independent review of a real authenticated WCAG/keyboard audit.

The trusted browser producer may emit a bounded numerical receipt. This verifier
requires the successful exact-run complete Console surface proof plus matching,
unexpired, single-artifact GitHub provenance. It does not claim comprehensive
WCAG conformance, unaudited roles or unexercised dynamic business journeys.
"""
from __future__ import annotations

from dataclasses import dataclass

from .independent_complete_console_evidence import (
    NAMES, REPO, SHA, VerifiedConsoleSurface,
)
from .product_readiness_certification import VerifiedCriterionEvidence

FILE = "block1-b3-wcag-accessibility-witness.json"
PREFIX = "block1-b3-wcag-accessibility-"
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
FIELDS = frozenset({
    "schema", "runId", "sourceCommit", "targetCommit", "routeNames",
    "engine", "tags", "desktopScans", "mobileScans",
    "mobileMenuScans", "projectDetailScans", "contrastNodes",
    "axeRulePasses", "keyboardSkipVerified", "keyboardFocusVisible",
    "productionWrites", "paidCalls", "personalDataRetained",
    "fullWcagCertified", "allRolesCertified",
})


class ConsoleAccessibilityBlocked(RuntimeError):
    """A closed reason code, never browser content or operator data."""


def validate_a11y_receipt(payload: object, *, run_id: int, source_sha: str,
                          served_sha: str) -> None:
    if (not isinstance(payload, dict) or set(payload) != FIELDS
            or payload.get("schema") != "factory-b3-wcag22-aa-keyboard-audit-v1"
            or type(payload.get("runId")) is not int or payload["runId"] != run_id
            or payload.get("sourceCommit") != source_sha
            or payload.get("targetCommit") != served_sha
            or payload.get("routeNames") != list(NAMES)
            or payload.get("engine") != "@axe-core/playwright@4.14.0"
            or payload.get("tags") != TAGS
            or any(type(payload.get(k)) is not int or payload[k] != len(NAMES)
                   for k in ("desktopScans", "mobileScans", "mobileMenuScans"))
            or type(payload.get("projectDetailScans")) is not int
            or payload["projectDetailScans"] != 2
            or type(payload.get("contrastNodes")) is not int
            or payload["contrastNodes"] < len(NAMES) * 3 + 2
            or type(payload.get("axeRulePasses")) is not int
            or payload["axeRulePasses"] < len(NAMES) * 3 + 2
            or any(payload.get(k) is not True for k in (
                "keyboardSkipVerified", "keyboardFocusVisible"))
            or any(payload.get(k) is not False for k in (
                "personalDataRetained", "fullWcagCertified", "allRolesCertified"))
            or type(payload.get("productionWrites")) is not int
            or payload["productionWrites"] != 0
            or type(payload.get("paidCalls")) is not int
            or payload["paidCalls"] != 0):
        raise ConsoleAccessibilityBlocked("b3_a11y_receipt_invalid")


@dataclass(frozen=True)
class VerifiedConsoleAccessibility:
    repository: str
    assessed_commit: str
    run_id: int
    artifact_id: int

    def receipt(self) -> dict:
        return {
            "schema": "factory-b3-independent-wcag-accessibility-v1",
            "repository": self.repository,
            "assessed_commit": self.assessed_commit,
            "workflow_run_id": self.run_id,
            "artifact_id": self.artifact_id,
            "scanned_operator_routes": len(NAMES),
            "scanned_viewports_per_route": ["desktop", "mobile", "mobile-menu"],
            "project_detail_scans": 2,
            "full_wcag_conformance_claimed": False,
            "all_roles_claimed": False,
            "writes": 0,
            "paid_calls": 0,
        }

    def criterion(self) -> VerifiedCriterionEvidence:
        return VerifiedCriterionEvidence(
            domain="product_experience", criterion="accessibility",
            repository=self.repository, assessed_commit=self.assessed_commit,
            verification_state="observed",
            source="independent_executed_axe_wcag22_keyboard_audit",
            evidence=("https://github.com/" + self.repository + "/actions/runs/"
                      + str(self.run_id) + "#sha=" + self.assessed_commit,),
            retained_receipt=self.receipt(),
        )


def verify_console_accessibility(*, repository: str, assessed_commit: str,
                                 surface: VerifiedConsoleSurface,
                                 github_get, artifact_reader) -> VerifiedConsoleAccessibility | None:
    if (not REPO.fullmatch(repository) or not SHA.fullmatch(assessed_commit)
            or not isinstance(surface, VerifiedConsoleSurface)
            or surface.repository != repository or surface.assessed_commit != assessed_commit
            or type(surface.run_id) is not int or surface.run_id < 1):
        raise ConsoleAccessibilityBlocked("b3_a11y_surface_unverified")
    run_id = surface.run_id
    # Reused captures are admissible only after independently verified
    # ancestry, immutable Console blobs, captured Control Plane receipt and
    # the original executed run-bound full-surface witness.
    source_sha = surface.source_commit or assessed_commit
    if not SHA.fullmatch(source_sha):
        raise ConsoleAccessibilityBlocked("b3_a11y_source_sha_invalid")
    rows = github_get("/repos/" + repository + "/actions/runs/" + str(run_id)
                      + "/artifacts?per_page=100")
    artifacts = rows.get("artifacts") if isinstance(rows, dict) else None
    if not isinstance(artifacts, list) or rows.get("total_count") != len(artifacts):
        raise ConsoleAccessibilityBlocked("b3_a11y_artifact_inventory_invalid")
    matches = [a for a in artifacts if isinstance(a, dict)
               and a.get("name") == PREFIX + str(run_id)]
    if not matches:
        return None  # Historical runs lacking this audit cannot imply PASS.
    if len(matches) != 1:
        raise ConsoleAccessibilityBlocked("b3_a11y_duplicate_artifact")
    artifact = matches[0]
    provenance = artifact.get("workflow_run")
    if (type(artifact.get("id")) is not int or artifact["id"] < 1
            or artifact.get("expired") is not False
            or type(artifact.get("size_in_bytes")) is not int
            or not 100 <= artifact["size_in_bytes"] <= 65536
            or not isinstance(provenance, dict)
            or provenance.get("id") != run_id
            or provenance.get("head_branch") != "main"
            or provenance.get("head_sha") != source_sha):
        raise ConsoleAccessibilityBlocked("b3_a11y_provenance_invalid")
    payload = artifact_reader(repository=repository, artifact_id=artifact["id"], artifact_file=FILE)
    validate_a11y_receipt(payload, run_id=run_id, source_sha=source_sha,
                          served_sha=surface.target_commit)
    return VerifiedConsoleAccessibility(repository, assessed_commit, run_id, artifact["id"])
