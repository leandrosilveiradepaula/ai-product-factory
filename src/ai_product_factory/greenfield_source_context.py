"""Read-only, SHA-pinned baseline for an already-created Console greenfield.

An OWNER continuation is authorized by the GitHub event, not by README text.
Unlike existing/CRM, a greenfield need not have AGENTS or CURRENT_TASK, and
a Draft pilot PR is never treated as a verified write target.
"""
from __future__ import annotations

import re

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")


def live_greenfield_source_context(*, project: dict, context: dict, github: object) -> dict:
    if not isinstance(project, dict) or project.get("project_kind") != "greenfield":
        raise PermissionError("greenfield source requires explicit project kind")
    if not isinstance(context, dict):
        raise PermissionError("greenfield source context missing")
    repository = project.get("repository")
    manifest = project.get("manifest")
    if (not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository)
        or getattr(github, "repository", None) != repository
        or not isinstance(manifest, dict)
        or manifest.get("source") != "factory-console"
        or manifest.get("onboarding_mode") != "greenfield"
        or not isinstance(manifest.get("bootstrap_request_id"), str)):
        raise PermissionError("greenfield source provenance unavailable")
    continuation = manifest.get("continuation_request")
    if (not isinstance(continuation, dict)
        or continuation.get("source") != "github-owner"
        or not isinstance(continuation.get("summary"), str)
        or not continuation["summary"].strip()
        or not isinstance(continuation.get("github"), dict)
        or continuation["github"].get("repository") != "leandrosilveiradepaula/ai-product-factory"
        or continuation["github"].get("issue_number") != 1055
        or continuation["github"].get("actor_id") != 256917842):
        raise PermissionError("greenfield source lacks authentic OWNER continuation")

    sha = github.get_branch_sha("main")
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise PermissionError("greenfield main SHA invalid")
    governance = {}
    for name in ("README.md", "package.json"):
        value = github.get_file_text(name, ref=sha)
        if (not isinstance(value, str) or not value.strip()
            or len(value.encode("utf-8")) > 65536):
            raise PermissionError("greenfield source document missing or oversized")
        governance[name] = value
    if github.get_branch_sha("main") != sha:
        raise PermissionError("greenfield main changed during reconciliation")

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
        "observed_from": "live_greenfield_main_exact_sha",
        "verified_open_pr": None,
        "governance": governance,
        "limitation": (
            "main is read-only evidence for planning. No write paths, PR "
            "authorization, tests or Preview verification are inferred; "
            "the independent scoped delivery gate remains mandatory."
        ),
    }
    result["current_state_facts"] = facts
    return result
