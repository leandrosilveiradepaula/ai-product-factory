"""Separate verified CI repair candidate lineage from imported-project repin.

A CI repair edits an already Factory-integrated PR candidate, not the pinned
Preview source. The caller has verified the project's pinned Preview target;
this helper additionally requires a live, exact candidate PR and branch.
"""
from __future__ import annotations

import re
from uuid import UUID

from .journey_delivery_binding import JourneyBinding

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
    assignment = source.get("assignment")
    if not isinstance(assignment, dict):
        raise PermissionError("CI repair requires the existing project's verified assignment")
    project_key = source.get("project_key")
    repository = source.get("repository")
    raw_journey = source.get("journey_binding")
    journey = None
    if raw_journey is not None:
        # V2 deliberately masks the mutable V1 imported-project target.
        # Reuse ONLY its immutable, request-scoped delivery binding.
        if (not isinstance(raw_journey, dict)
            or source.get("delivery_target") is not None):
            raise PermissionError("V2 CI repair cannot inherit a V1 delivery target")
        journey = JourneyBinding.parse(
            raw_journey,
            project_id=str(raw_journey.get("project_id") or ""),
            request_id=str(source.get("request_id") or ""),
            repository=repository,
        )
        if (source.get("journey_id") != journey.journey_id
            or source.get("project_id") not in (None, journey.project_id)
            or journey.integration_branch != integration_branch
            or github.get_branch_sha(journey.preview_base_ref) != journey.source_commit):
            raise PermissionError("V2 CI repair journey or pinned Preview source changed")
        target = {"repository": repository, "sha": journey.source_commit,
                  "branch": journey.preview_base_ref}
        valid_branch = True
    else:
        target = source.get("delivery_target")
        if not isinstance(target, dict):
            raise PermissionError("CI repair requires the existing project's verified target")
        valid_branch = (isinstance(integration_branch, str)
                        and integration_branch.startswith("factory/change-set-"))
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
        or not valid_branch
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
    proof = {
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
    if journey is not None:
        proof["journey_id"] = journey.journey_id
        proof["execution_generation"] = journey.execution_generation
        proof["binding_version"] = journey.binding_version
    return proof
