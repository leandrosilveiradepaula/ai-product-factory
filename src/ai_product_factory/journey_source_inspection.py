"""Read-only exact-SHA source inspection for immutable Journey Delivery Binding V2.

An immutable request may identify a class/method but not its repository path.
Resolve only a unique basename from the verified commit's inventory. A
missing/ambiguous match is explicit; it never authorizes new files or writes.
"""
from __future__ import annotations

import re

from .candidate_source_evidence import collect_candidate_source_evidence
from .source_scope_admission import assess_bounded_source_scope

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_METHOD = re.compile(r"\b([A-Z][A-Za-z0-9_]{2,80})\.[A-Za-z_][A-Za-z0-9_]*\b")
_EXPLICIT = re.compile(
    r"(?:src|test|tests|app|apps|pages|lib|packages|scripts)/"
    r"[A-Za-z0-9_./()-]+\.(?:py|tsx?|jsx?|cjs|mjs)"
)
_CODE_SUFFIX = (".ts", ".tsx", ".js", ".jsx", ".py")
_MAX_REQUEST = 12000
_MAX_INVENTORY = 100000


def inspect_journey_source(
    github: object, *, sha: str, request: str, issue_body: str | None = None,
) -> dict:
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise PermissionError("journey source SHA invalid")
    if (not isinstance(request, str) or not request.strip()
        or len(request.encode("utf-8")) > _MAX_REQUEST):
        raise PermissionError("journey request missing or oversized")
    # Same-repository issue description is a read-only discovery hint.
    # It is never write authority; the exact source SHA and unique pathname
    # are still required before any snippet is described as inspected.
    if issue_body is not None and (
        not isinstance(issue_body, str)
        or len(issue_body.encode("utf-8")) > _MAX_REQUEST
    ):
        raise PermissionError("journey issue discovery hint invalid")
    discovery_text = request + "\n" + (issue_body or "")
    paths = github.list_file_paths(ref=sha)
    if (not isinstance(paths, (list, tuple)) or len(paths) > _MAX_INVENTORY
        or any(not isinstance(p, str) or not p or p.startswith("/")
               or ".." in p.split("/") for p in paths)
        or len(paths) != len(set(paths))):
        raise PermissionError("journey source inventory invalid")
    existing = set(paths)
    requested = list(dict.fromkeys(_EXPLICIT.findall(discovery_text)))
    # Class.method is a search hint, not permission to edit a path.
    for class_name in dict.fromkeys(_METHOD.findall(discovery_text)):
        matches = [
            path for path in paths
            if path.startswith(("src/", "app/", "apps/", "pages/", "lib/", "packages/"))
            and path.rsplit("/", 1)[-1] in
            {class_name + suffix for suffix in _CODE_SUFFIX}
        ]
        if len(matches) > 1:
            raise PermissionError("journey source class path ambiguous")
        if len(matches) == 1 and matches[0] not in requested:
            requested.append(matches[0])
    # Do not turn issue prose into a repository-wide file search.
    requested = requested[:4]
    if not requested:
        return {
            "status": "no_scoped_source_paths", "assessed_commit": sha,
            "inspected_files": [], "missing_paths": [],
            "limitation": "No unique source path; no code was inspected.",
        }
    # Reuse the established 24-KiB/4-file excerpt and secret guards.
    evidence = collect_candidate_source_evidence(
        "", github, sha=sha, continuation_request="\n".join(requested),
    )
    assess_bounded_source_scope(evidence, sha=sha)
    evidence["discovery"] = "immutable_journey_request_unique_basename"
    evidence["unmatched_request_paths"] = [
        path for path in requested if path not in existing
    ]
    return evidence
