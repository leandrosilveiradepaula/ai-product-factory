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
# The only historical capture that may be reused.  This is deliberately an
# allowlist, rather than accepting a run id from a caller: reusing an arbitrary
# completed workflow would turn a stale browser run into a new positive claim.
HISTORICAL_WORKFLOW_RUN_ID = 43289096088
HISTORICAL_SOURCE_SHA = "4af001c0de6d42e686c4fb699b8095e6dd59edb8"


class AuthenticatedConsoleEvidenceBlocked(RuntimeError):
    """The browser receipt is absent, stale, ambiguous, or not trustworthy."""


@dataclass(frozen=True)
class AuthenticatedConsoleEvidence:
    repository: str
    assessed_commit: str
    workflow_run_id: int
    artifact_id: int | None
    source_commit: str | None = None

    @property
    def evidence(self) -> tuple[str, ...]:
        return (
            "https://github.com/" + self.repository + "/actions/runs/"
            + str(self.workflow_run_id) + "#sha=" + self.assessed_commit,
        )

    def receipt(self) -> dict:
        receipt = {
            "kind": "github_exact_sha_authenticated_console_metadata",
            "repository": self.repository,
            "assessed_commit": self.assessed_commit,
            "workflow_run_id": self.workflow_run_id,
            "artifact_encrypted_not_read": True,
            "does_not_certify": [
                "authn_authz", "data_access_boundaries", "critical_e2e",
                "states", "critical_journeys", "product_ready",
            ],
        }
        if self.artifact_id is not None:
            receipt["artifact_id"] = self.artifact_id
        else:
            receipt.update(artifact_available=False,
                           source="github_exact_source_run_control_plane_captured_registry_and_identical_console_tree")
        return receipt


def _capture_job(*, github_get, prefix: str, workflow_run_id: int, sha: str) -> None:
    jobs = github_get(prefix + "/actions/runs/" + str(workflow_run_id) + "/jobs?per_page=100")
    rows = jobs.get("jobs") if isinstance(jobs, dict) else None
    if (not isinstance(rows, list) or jobs.get("total_count") != len(rows)
            or not 1 <= len(rows) <= 100):
        raise AuthenticatedConsoleEvidenceBlocked("visual job inventory unavailable")
    capture = [row for row in rows if isinstance(row, dict) and row.get("name") == "capture"]
    if len(capture) != 1 or any(capture[0].get(key) != value for key, value in {
        "run_id": workflow_run_id, "head_sha": sha,
        "status": "completed", "conclusion": "success",
    }.items()):
        raise AuthenticatedConsoleEvidenceBlocked("capture job was not successfully completed")


def _console_blobs(tree: object) -> dict[str, tuple[str, str]]:
    if not isinstance(tree, dict) or tree.get("truncated") is not False:
        raise AuthenticatedConsoleEvidenceBlocked("Console tree is incomplete")
    entries = tree.get("tree")
    if not isinstance(entries, list):
        raise AuthenticatedConsoleEvidenceBlocked("Console tree is unavailable")
    blobs = {}
    paths_seen = set()
    for item in entries:
        if not isinstance(item, dict):
            raise AuthenticatedConsoleEvidenceBlocked("Console tree entry is invalid")
        path = item.get("path")
        if not isinstance(path, str) or not path.startswith("apps/console/"):
            continue
        # GitHub's recursive tree legitimately includes directories with
        # type=tree/mode=040000. Only file blobs are compared; unsafe modes,
        # duplicate paths, and malformed directory metadata must still fail.
        if (path in paths_seen or any(part in ("", ".", "..") for part in path.split("/"))
                or not isinstance(item.get("sha"), str)
                or SHA.fullmatch(item["sha"]) is None):
            raise AuthenticatedConsoleEvidenceBlocked("Console tree provenance mismatch")
        paths_seen.add(path)
        if item.get("type") == "tree" and item.get("mode") == "040000":
            continue
        if (item.get("type") != "blob"
                or item.get("mode") not in ("100644", "100755")):
            raise AuthenticatedConsoleEvidenceBlocked("Console blob provenance mismatch")
        blobs[path] = (item["sha"], item["mode"])
    if not blobs:
        raise AuthenticatedConsoleEvidenceBlocked("Console tree is empty")
    return blobs


def verify_reusable_historical_authenticated_console_evidence(*, repository: str,
                                                               assessed_commit: str,
                                                               github_get, control_plane_get,
                                                               require_default_head: bool = True) -> AuthenticatedConsoleEvidence:
    """Reuse a single durable capture only when its rendered Console is unchanged.

    The Control Plane registry proves that the encrypted capture completed
    before artifact expiry.  We never download or decrypt that artifact; a
    byte-identical Console tree and immutable ancestry only bound the partial
    UX observation to the current candidate.
    """
    if (not isinstance(repository, str) or REPO.fullmatch(repository) is None
            or not isinstance(assessed_commit, str) or SHA.fullmatch(assessed_commit) is None
            or not isinstance(require_default_head, bool)):
        raise AuthenticatedConsoleEvidenceBlocked("invalid historical evidence request")
    prefix = "/repos/" + repository
    repo = github_get(prefix)
    branch = repo.get("default_branch") if isinstance(repo, dict) else None
    if not isinstance(branch, str) or not branch:
        raise AuthenticatedConsoleEvidenceBlocked("default branch unavailable")
    if require_default_head:
        head = github_get(prefix + "/git/ref/heads/" + branch)
        if not isinstance(head, dict) or (head.get("object") or {}).get("sha") != assessed_commit:
            raise AuthenticatedConsoleEvidenceBlocked("main no longer matches evidence SHA")
    run = github_get(prefix + "/actions/runs/" + str(HISTORICAL_WORKFLOW_RUN_ID))
    if not isinstance(run, dict) or (
        run.get("id") != HISTORICAL_WORKFLOW_RUN_ID or run.get("name") != WORKFLOW
        or run.get("path") != WORKFLOW_PATH or run.get("event") != "push"
        or run.get("head_branch") != branch or run.get("head_sha") != HISTORICAL_SOURCE_SHA
        or run.get("run_attempt") != 1 or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or (run.get("repository") or {}).get("full_name") != repository
    ):
        raise AuthenticatedConsoleEvidenceBlocked("historical visual workflow provenance mismatch")
    _capture_job(github_get=github_get, prefix=prefix,
                 workflow_run_id=HISTORICAL_WORKFLOW_RUN_ID, sha=HISTORICAL_SOURCE_SHA)
    artifacts = github_get(prefix + "/actions/runs/" + str(HISTORICAL_WORKFLOW_RUN_ID) + "/artifacts?per_page=100")
    # GitHub may retain an expired artifact in its inventory before purging
    # it. Either a deleted artifact or one with exact, non-ambiguous source
    # metadata is safe to pair with the durable capture registry; this does
    # not certify browser interactions, RBAC or a complete UX review.
    rows = artifacts.get("artifacts") if isinstance(artifacts, dict) else None
    count = artifacts.get("total_count") if isinstance(artifacts, dict) else None
    if (type(count) is not int or not 0 <= count <= 100
            or not isinstance(rows, list) or len(rows) != count):
        raise AuthenticatedConsoleEvidenceBlocked("historical artifact inventory is ambiguous")
    matching = [item for item in rows if isinstance(item, dict)
                and item.get("name") == "authenticated-console-" + str(HISTORICAL_WORKFLOW_RUN_ID)]
    if len(matching) > 1:
        raise AuthenticatedConsoleEvidenceBlocked("historical artifact duplicate")
    artifact_id = None
    if matching:
        artifact = matching[0]
        provenance = artifact.get("workflow_run") if isinstance(artifact, dict) else None
        if (not isinstance(artifact, dict)
                or artifact.get("name") != "authenticated-console-" + str(HISTORICAL_WORKFLOW_RUN_ID)
                or type(artifact.get("id")) is not int or artifact["id"] < 1
                or type(artifact.get("size_in_bytes")) is not int or artifact["size_in_bytes"] < 1
                or type(artifact.get("expired")) is not bool
                or not isinstance(provenance, dict)
                or provenance.get("id") != HISTORICAL_WORKFLOW_RUN_ID
                or provenance.get("head_sha") != HISTORICAL_SOURCE_SHA
                or provenance.get("head_branch") != branch):
            raise AuthenticatedConsoleEvidenceBlocked("historical artifact provenance mismatch")
        if artifact["expired"] is False:
            artifact_id = artifact["id"]
    rows = control_plane_get(
        "factory_visual_evidence_runs?select=workflow_run_id,source_commit,artifact_name,status"
        "&workflow_run_id=eq." + str(HISTORICAL_WORKFLOW_RUN_ID) + "&limit=2"
    )
    if not isinstance(rows, list) or len(rows) != 1:
        raise AuthenticatedConsoleEvidenceBlocked("historical visual registry is unavailable or ambiguous")
    registry = rows[0]
    if not isinstance(registry, dict) or registry != {
        "workflow_run_id": HISTORICAL_WORKFLOW_RUN_ID,
        "source_commit": HISTORICAL_SOURCE_SHA,
        "artifact_name": "authenticated-console-" + str(HISTORICAL_WORKFLOW_RUN_ID),
        "status": "captured",
    }:
        raise AuthenticatedConsoleEvidenceBlocked("historical visual registry provenance mismatch")
    comparison = github_get(prefix + "/compare/" + HISTORICAL_SOURCE_SHA + "..." + assessed_commit)
    if not isinstance(comparison, dict) or comparison.get("status") not in ("ahead", "identical") or comparison.get("behind_by") != 0:
        raise AuthenticatedConsoleEvidenceBlocked("historical evidence is not an ancestor of candidate")
    if ((comparison.get("base_commit") or {}).get("sha") != HISTORICAL_SOURCE_SHA
            or (comparison.get("merge_base_commit") or {}).get("sha") != HISTORICAL_SOURCE_SHA):
        raise AuthenticatedConsoleEvidenceBlocked("historical evidence merge base mismatch")
    source = _console_blobs(github_get(prefix + "/git/trees/" + HISTORICAL_SOURCE_SHA + "?recursive=1"))
    candidate = _console_blobs(github_get(prefix + "/git/trees/" + assessed_commit + "?recursive=1"))
    if source != candidate:
        raise AuthenticatedConsoleEvidenceBlocked("Console changed after historical browser capture")
    return AuthenticatedConsoleEvidence(
        repository=repository, assessed_commit=assessed_commit,
        workflow_run_id=HISTORICAL_WORKFLOW_RUN_ID, artifact_id=artifact_id,
        source_commit=HISTORICAL_SOURCE_SHA,
    )


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
        or run.get("path") != WORKFLOW_PATH or run.get("event") not in ("workflow_dispatch", "push")
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
