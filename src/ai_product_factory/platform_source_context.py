"""Fail-closed, read-only source context for an explicitly registered platform project.

An existing/CRM project keeps its stricter pinned nonproduction PR contract.
Platforms use the exact main commit as READ evidence only, not a write target.
"""
from __future__ import annotations

import re

from .candidate_source_evidence import collect_candidate_source_evidence
from .source_scope_admission import assess_bounded_source_scope

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
_GOVERNANCE = ("AGENTS.md", "PROJECT_PLAN.md")
_ISSUE_REF = re.compile(r"\b(?:issue|tarefa)\s*#([1-9][0-9]{0,5})\b", re.IGNORECASE)
_PATH_HINT = re.compile(
    r"(?:src|test|tests|app|apps|pages|lib|packages|scripts)/"
    r"[A-Za-z0-9_./()\-]+\.(?:tsx?|jsx?|py|cjs|mjs)"
)


def _issue_path_hints(github: object, summary: object) -> tuple[int | None, tuple[str, ...]]:
    """Extract *paths only* from one repository issue; never import its instructions.

    An issue is mutable/untrusted and is not authorization to edit files.
    Fail closed if the referenced issue cannot be fetched or verified.
    """
    if not isinstance(summary, str) or not summary:
        return None, ()
    issues = set(_ISSUE_REF.findall(summary))
    if not issues:
        return None, ()
    if len(issues) != 1:
        raise PermissionError("continuation refers to multiple GitHub issues")
    number = int(next(iter(issues)))
    issue = github.get_issue(number)
    if getattr(issue, "number", None) != number:
        raise PermissionError("issue lookup did not match requested identity")
    body = getattr(issue, "body", None)
    if not isinstance(body, str) or len(body.encode("utf-8")) > 20000:
        raise PermissionError("issue scope body missing or oversized")
    paths = tuple(dict.fromkeys(
        path for path in _PATH_HINT.findall(body)
        if ".." not in path.split("/")
    ))
    if len(paths) > 20:
        raise PermissionError("issue scope inventory exceeds safe bound")
    return number, paths



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
    issue_number, issue_paths = _issue_path_hints(github, summary)
    # Source retrieval is bounded to filenames; the mutable issue body is
    # not treated as authority or copied into model prompts.
    requested_source = (summary or "") + "\n" + "\n".join(issue_paths)
    evidence = collect_candidate_source_evidence(
        governance["PROJECT_PLAN.md"], github, sha=sha,
        continuation_request=requested_source,
    )
    evidence["issue_reference"] = issue_number
    evidence["issue_path_hint_count"] = len(issue_paths)
    admission = assess_bounded_source_scope(evidence, sha=sha)
    # The trusted source receipt is checked BEFORE Product Stage can call
    # a paid model. Missing files can be intentional creation work, and large
    # scopes can be partial. Neither is called complete or treated as a
    # human gate. Incorrect SHA or contradictory evidence blocks safely.
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
        "source_admission": admission,
        "limitation": (
            "main is a read-only planning baseline; no open candidate PR "
            "or CI/Preview verification is implied"
        ),
    }
    result["current_state_facts"] = facts
    return result
