"""Separate verified CI repair candidate lineage from imported-project repin.

A CI repair edits an already Factory-integrated PR candidate, not the pinned
Preview source. The caller has verified the project's pinned Preview target;
this helper additionally requires a live, exact candidate PR and branch.
"""
from __future__ import annotations

import re
from uuid import UUID

_SHA = re.compile(r"[a-f0-9]{40}\Z")


def _positive(value: object) -> bool:
    return type(value) is int and value > 0


def verify_existing_ci_repair_candidate(
    *, source: dict, base_commit: str, integration_branch: str,
    github: object,
) -> dict | None:
    repair = source.get("repair")
    if not isinstance(repair, dict) or repair.get("repair_kind") != "ci":
        return None
    if source.get("project_kind") != "existing":
        return None
    target = source.get("delivery_target")
    assignment = source.get("assignment")
    if not isinstance(target, dict) or not isinstance(assignment, dict):
        raise PermissionError("CI repair requires the existing project's verified target")
    project_key = source.get("project_key")
    repository = source.get("repository")
    scopes = assignment.get("scope_keys")
    requested = repair.get("write_scopes")
    candidate = repair.get("candidate_commit")
    pr_number = repair.get("pr_number")
    attempt, max_attempts = repair.get("attempt"), repair.get("max_attempts")
    if (
        not isinstance(project_key, str) or not project_key
        or not isinstance(repository, str) or repository != getattr(github, "repository", None)
        or target.get("repository") != repository
        or not isinstance(target.get("sha"), str) or not _SHA.fullmatch(target["sha"])
        or not isinstance(target.get("branch"), str) or not target["branch"].startswith("preview/")
        or not isinstance(candidate, str) or not _SHA.fullmatch(candidate)
        or candidate != base_commit
        or repair.get("branch") != integration_branch
        or not isinstance(integration_branch, str) or not integration_branch.startswith("factory/change-set-")
        or not _positive(pr_number)
        or not _positive(attempt) or not _positive(max_attempts)
        or max_attempts > 3 or attempt > max_attempts
        or not isinstance(scopes, list) or not isinstance(requested, list)
        or not scopes or len(scopes) > 20 or len(scopes) != len(set(scopes))
        or scopes != requested
        or any(not isinstance(p, str) or not p or p.startswith("/")
               or "\\" in p or p in (".", "..") or p.endswith("/**")
               or any(segment in ("", ".", "..") for segment in p.split("/"))
               for p in scopes)
    ):
        raise PermissionError("CI repair candidate identity or exact scopes were revoked")
    try:
        request_id = str(UUID(str(repair.get("repair_request_id"))))
    except (ValueError, TypeError, AttributeError):
        raise PermissionError("CI repair request identity is not a valid UUID") from None
    if request_id != repair.get("repair_request_id"):
        raise PermissionError("CI repair request identity was not canonical")
    if github.get_branch_sha(integration_branch) != candidate:
        raise PermissionError("CI repair integration branch is not the exact candidate")
    pr = github.get_pull_request(pr_number)
    if (
        getattr(pr, "number", None) != pr_number
        or getattr(pr, "state", None) != "open"
        or bool(getattr(pr, "merged", True))
        or bool(getattr(pr, "draft", False))
        or getattr(pr, "head_sha", None) != candidate
        or getattr(pr, "head_ref", None) != integration_branch
        or getattr(pr, "base_ref", None) != target["branch"]
        or getattr(pr, "head_repository", None) != repository
    ):
        raise PermissionError("CI repair PR head or base differs from approved candidate")
    return {
        "kind": "verified_native_ci_repair_candidate",
        "project_key": project_key,
        "repository": repository,
        "base_preview_sha": target["sha"],
        "base_preview_branch": target["branch"],
        "candidate_commit": candidate,
        "integration_branch": integration_branch,
        "pr_number": pr_number,
        "repair_request_id": request_id,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "write_scopes": list(scopes),
    }
