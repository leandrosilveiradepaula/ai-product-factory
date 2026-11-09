"""Verify one completed authenticated Console capture without promoting a criterion.

The encrypted artifact is deliberately never downloaded or decrypted here.  A
successful browser capture can be retained as a *partial* UX receipt, but it
is not proof of JWT claims, RBAC, tenant isolation, critical E2E, or a full
accessibility review.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z", re.ASCII)
WORKFLOW = "Authenticated Console visual evidence"
WORKFLOW_PATH = ".github/workflows/authenticated-visual-evidence.yml"


class AuthenticatedConsoleEvidenceBlocked(RuntimeError):
    """The browser receipt is absent, stale, ambiguous, or not trustworthy."""


@dataclass(frozen=True)
class AuthenticatedConsoleEvidence:
    repository: str
    assessed_commit: str
    workflow_run_id: int
    artifact_id: int

    @property
    def evidence(self) -> tuple[str, ...]:
        return (
            "https://github.com/" + self.repository + "/actions/runs/"
            + str(self.workflow_run_id) + "#sha=" + self.assessed_commit,
        )

    def receipt(self) -> dict:
        return {
            "kind": "github_exact_sha_authenticated_console_metadata",
            "repository": self.repository,
            "assessed_commit": self.assessed_commit,
            "workflow_run_id": self.workflow_run_id,
            "artifact_id": self.artifact_id,
            "artifact_encrypted_not_read": True,
            "does_not_certify": [
                "authn_authz", "data_access_boundaries", "critical_e2e",
                "states", "critical_journeys", "product_ready",
            ],
        }


def verify_authenticated_console_evidence(*, repository: str, assessed_commit: str,
                                          workflow_run_id: int, github_get) -> AuthenticatedConsoleEvidence:
    if not isinstance(repository, str) or REPO.fullmatch(repository) is None:
        raise AuthenticatedConsoleEvidenceBlocked("invalid repository")
    if not isinstance(assessed_commit, str) or SHA.fullmatch(assessed_commit) is None:
        raise AuthenticatedConsoleEvidenceBlocked("invalid assessed commit")
    if type(workflow_run_id) is not int or workflow_run_id < 1:
        raise AuthenticatedConsoleEvidenceBlocked("invalid workflow run")
    prefix = "/repos/" + repository
    repo = github_get(prefix)
    branch = repo.get("default_branch") if isinstance(repo, dict) else None
    if not isinstance(branch, str) or not branch:
        raise AuthenticatedConsoleEvidenceBlocked("default branch unavailable")
    head = github_get(prefix + "/git/ref/heads/" + branch)
    if not isinstance(head, dict) or (head.get("object") or {}).get("sha") != assessed_commit:
        raise AuthenticatedConsoleEvidenceBlocked("main no longer matches evidence SHA")
    run = github_get(prefix + "/actions/runs/" + str(workflow_run_id))
    if not isinstance(run, dict) or (
        run.get("id") != workflow_run_id or run.get("name") != WORKFLOW
        or run.get("path") != WORKFLOW_PATH or run.get("event") != "workflow_dispatch"
        or run.get("head_branch") != branch or run.get("head_sha") != assessed_commit
        or run.get("run_attempt") != 1 or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or (run.get("repository") or {}).get("full_name") != repository
    ):
        raise AuthenticatedConsoleEvidenceBlocked("visual workflow provenance mismatch")
    jobs = github_get(prefix + "/actions/runs/" + str(workflow_run_id) + "/jobs?per_page=100")
    rows = jobs.get("jobs") if isinstance(jobs, dict) else None
    if (not isinstance(rows, list) or jobs.get("total_count") != len(rows)
            or not 1 <= len(rows) <= 100):
        raise AuthenticatedConsoleEvidenceBlocked("visual job inventory unavailable")
    capture = [row for row in rows if isinstance(row, dict) and row.get("name") == "capture"]
    if len(capture) != 1 or any(capture[0].get(key) != value for key, value in {
        "run_id": workflow_run_id, "head_sha": assessed_commit,
        "status": "completed", "conclusion": "success",
    }.items()):
        raise AuthenticatedConsoleEvidenceBlocked("capture job was not successfully completed")
    artifacts = github_get(prefix + "/actions/runs/" + str(workflow_run_id) + "/artifacts?per_page=100")
    rows = artifacts.get("artifacts") if isinstance(artifacts, dict) else None
    if (not isinstance(rows, list) or artifacts.get("total_count") != len(rows)
            or not 1 <= len(rows) <= 10):
        raise AuthenticatedConsoleEvidenceBlocked("visual artifact inventory unavailable")
    expected_name = "authenticated-console-" + str(workflow_run_id)
    matched = [row for row in rows if isinstance(row, dict) and row.get("name") == expected_name]
    if len(matched) != 1:
        raise AuthenticatedConsoleEvidenceBlocked("visual artifact is missing or ambiguous")
    artifact = matched[0]
    provenance = artifact.get("workflow_run")
    if (type(artifact.get("id")) is not int or artifact["id"] < 1
            or artifact.get("expired") is not False
            or type(artifact.get("size_in_bytes")) is not int or artifact["size_in_bytes"] < 1
            or not isinstance(provenance, dict) or provenance.get("id") != workflow_run_id
            or provenance.get("head_sha") != assessed_commit
            or provenance.get("head_branch") != branch):
        raise AuthenticatedConsoleEvidenceBlocked("visual artifact provenance mismatch")
    return AuthenticatedConsoleEvidence(
        repository=repository, assessed_commit=assessed_commit,
        workflow_run_id=workflow_run_id, artifact_id=artifact["id"],
    )
