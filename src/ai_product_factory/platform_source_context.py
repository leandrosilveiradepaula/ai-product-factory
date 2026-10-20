"""Fail-closed, read-only source context for an explicitly registered platform project.

An existing/CRM project keeps its stricter pinned nonproduction PR contract.
Platforms use the exact main commit as READ evidence only, not a write target.
"""
from __future__ import annotations

import re

from .candidate_source_evidence import collect_candidate_source_evidence

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
_GOVERNANCE = ("AGENTS.md", "PROJECT_PLAN.md")


def live_platform_source_context(*, project: dict, context: dict, github: object) -> dict:
    if not isinstance(project, dict) or project.get("project_kind") != "platform":
        raise PermissionError("platform source requires an explicitly registered platform")
    if not isinstance(context, dict):
        raise PermissionError("platform source context must be a mapping")
    repository = project.get("repository")
    if not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository):
        raise PermissionError("platform source has invalid repository identity")
    if getattr(github, "repository", None) != repository:
        raise PermissionError("GitHub repository differs from Control Plane project")

    sha = github.get_branch_sha("main")
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise PermissionError("platform source requires exact GitHub main SHA")

    governance = {}
    for path in _GOVERNANCE:
        content = github.get_file_text(path, ref=sha)
        if (not isinstance(content, str) or not content.strip()
                or len(content.encode("utf-8")) > 65536):
            raise PermissionError("platform governance missing or oversized")
        governance[path] = content

    manifest = project.get("manifest")
    manifest = manifest if isinstance(manifest, dict) else {}
    continuation = manifest.get("continuation_request")
    summary = continuation.get("summary") if isinstance(continuation, dict) else None
    evidence = collect_candidate_source_evidence(
        governance["PROJECT_PLAN.md"], github, sha=sha, continuation_request=summary,
    )
    if evidence.get("assessed_commit") != sha:
        raise PermissionError("platform source evidence is not SHA exact")
    # The branch must still agree after bounded reads. A moving main cannot
    # silently become the verified baseline of a paid Product Stage.
    if github.get_branch_sha("main") != sha:
        raise PermissionError("platform main moved during source reconciliation")

    result = dict(context)
    facts = dict(result.get("current_state_facts") or {})
    access = facts.get("github_access")
    if isinstance(access, dict):
        facts["github_access"] = {
            **access, "live_github_head_verified": True,
            "verified_main_sha": sha,
        }
    facts["live_candidate"] = {
        "repository": repository,
        "branch": "main",
        "sha": sha,
        "main_sha": sha,
        "observed_from": "live_github_main_exact_sha",
        "verified_open_pr": None,
        "governance": governance,
        "source_evidence": evidence,
        "limitation": (
            "main is a read-only planning baseline; no open candidate PR "
            "or CI/Preview verification is implied"
        ),
    }
    result["current_state_facts"] = facts
    return result
