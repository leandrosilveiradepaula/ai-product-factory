"""Read-only proof that the Factory consumed an imported Preview source.

A source SHA belongs to an authorized Change Set; the Preview merge SHA is a
*different* identity. Neither a draft PR nor an ancestry comparison alone can
turn the merge into a new source authorization. This module never writes a
branch, mutates Control Plane state, or claims a production release.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
_MAX_RECEIPTS = 20
_MAX_FILES = 30


@dataclass(frozen=True)
class ConsumedSource:
    change_set_id: str
    source_sha: str
    implementation_sha: str
    preview_merge_sha: str
    implementation_pr: int
    execution_generation: int


def _identity(project: dict, target: Any, observed_sha: str) -> tuple[str, int]:
    project_id = project.get("id")
    control = project.get("execution_control")
    if (not isinstance(project_id, str) or not _UUID.fullmatch(project_id)
            or not isinstance(control, dict) or control.get("state") != "running"
            or type(control.get("generation")) is not int or control["generation"] < 1
            or type(control.get("version")) is not int or control["version"] < 0
            or project.get("project_kind") != "existing"
            or project.get("is_active") is not True
            or getattr(target, "repository", None) != project.get("repository")
            or not isinstance(observed_sha, str) or not _SHA.fullmatch(observed_sha)
            or observed_sha == target.sha):
        raise PermissionError("consumed source project, epoch or SHA is invalid")
    return project_id, control["generation"]


def attest_consumed_preview_source(
    github: Any, *, project: dict, target: Any,
    observed_sha: str, records: object,
) -> ConsumedSource | None:
    """Recognize only the exact Factory-authored merge in this project epoch.

    The evidence is a completed Change Set with a durable, exact Preview
    integration receipt, plus a fresh GitHub PR/branch and ancestry proof.
    A normal draft advancement *without* this receipt is not consumed.
    """
    project_id, generation = _identity(project, target, observed_sha)
    if not isinstance(records, list) or len(records) > _MAX_RECEIPTS:
        raise PermissionError("consumed source receipt inventory is incomplete")
    if github.repository != target.repository:
        raise PermissionError("consumed source GitHub repository differs")
    matches: list[ConsumedSource] = []
    for row in records:
        if not isinstance(row, dict):
            raise PermissionError("malformed consumed source receipt")
        if (row.get("project_id") != project_id
                or row.get("source_commit") != target.sha
                or row.get("status") != "completed"):
            continue
        cs_id = row.get("id")
        root = row.get("root_task_id")
        candidate = row.get("candidate_commit")
        meta = row.get("metadata")
        if (not isinstance(cs_id, str) or not _UUID.fullmatch(cs_id)
                or not isinstance(root, str) or not _UUID.fullmatch(root)
                or not isinstance(candidate, str) or not _SHA.fullmatch(candidate)
                or not isinstance(meta, dict)):
            raise PermissionError("completed source has invalid identity")
        epoch = meta.get("integration_epoch_receipt")
        receipt = meta.get("nonproduction_integration")
        request = meta.get("integration_release_request")
        changed = meta.get("integrated_files")
        if not (isinstance(epoch, dict) and isinstance(receipt, dict)
                and isinstance(request, dict) and isinstance(changed, list)):
            # Completed does not necessarily mean integrated. It must never
            # be falsely promoted into a consumed-source proof.
            continue
        if receipt.get("merge_sha") != observed_sha:
            continue  # An unrelated completed cycle cannot authorize this head.
        pr_number = receipt.get("pr_number")
        implementation_ref = "factory/change-set-" + cs_id[:8]
        if (epoch.get("project_id") != project_id
                or epoch.get("generation") != generation
                or epoch.get("candidate_commit") != candidate
                or receipt.get("merged") is not True
                or receipt.get("environment") != "preview"
                or receipt.get("repository") != target.repository
                or receipt.get("base_ref") != target.branch
                or receipt.get("head_ref") != implementation_ref
                or receipt.get("head_sha") != candidate
                or receipt.get("candidate_commit") != candidate
                or receipt.get("production_released") is not False
                or type(pr_number) is not int or pr_number < 1
                or request.get("pr_number") != pr_number
                or request.get("branch") != implementation_ref
                or request.get("candidate_commit") != candidate
                or not 1 <= len(changed) <= _MAX_FILES
                or any(not isinstance(path, str) or not path
                       or path.startswith("/") or ".." in path.split("/")
                       or "\\" in path for path in changed)
                or len(set(changed)) != len(changed)):
            raise PermissionError("consumed source evidence is inconsistent")
        matches.append(ConsumedSource(
            change_set_id=cs_id, source_sha=target.sha,
            implementation_sha=candidate, preview_merge_sha=observed_sha,
            implementation_pr=pr_number, execution_generation=generation,
        ))
        if len(matches) > 1:
            raise PermissionError("ambiguous consumed source evidence")
        # Only now spend GitHub reads on the one exact completed integration.
        pr = github.get_pull_request(pr_number)
        if (getattr(pr, "number", None) != pr_number
                or getattr(pr, "state", None) != "closed"
                or getattr(pr, "merged", None) is not True
                or getattr(pr, "draft", None) is not False
                or getattr(pr, "head_repository", None) != target.repository
                or getattr(pr, "head_ref", None) != implementation_ref
                or getattr(pr, "head_sha", None) != candidate
                or getattr(pr, "base_ref", None) != target.branch
                or getattr(pr, "merge_commit_sha", None) != observed_sha):
            raise PermissionError("Factory Preview merge PR identity differs")
        if set(github.get_pull_request_files(pr_number)) != set(changed):
            raise PermissionError("Factory Preview integrated file scope differs")
        compare = github.compare_commits(target.sha, observed_sha)
        if (not isinstance(compare, dict)
                or compare.get("status") != "ahead"
                or type(compare.get("ahead_by")) is not int
                or not 1 <= compare["ahead_by"] <= 64
                or compare.get("behind_by") != 0
                or not isinstance(compare.get("files"), list)
                or set(compare["files"]) != set(changed)):
            raise PermissionError("Factory Preview merge is not an exact-scoped descendant")
        source_pr = github.get_pull_request(target.candidate_pr_number)
        def valid_source(value: Any) -> bool:
            return (
                getattr(value, "number", None) == target.candidate_pr_number
                and getattr(value, "state", None) == "open"
                and getattr(value, "merged", None) is False
                and getattr(value, "head_repository", None) == target.repository
                and getattr(value, "head_ref", None) == target.branch
                and getattr(value, "head_sha", None) == observed_sha
                and getattr(value, "base_ref", None) == "main"
            )
        if (not valid_source(source_pr)
                or github.get_branch_sha(target.branch) != observed_sha
                or not valid_source(github.get_pull_request(target.candidate_pr_number))
                or getattr(github.get_pull_request(pr_number), "merge_commit_sha", None) != observed_sha):
            raise PermissionError("consumed source moved during verification")
    return matches[0] if matches else None
