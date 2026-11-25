"""Read-only exact-SHA source inspection for immutable Journey Delivery Binding V2.

An immutable request may identify a class/method but not its repository path.
Resolve only a unique basename from the verified commit's inventory. A
missing/ambiguous match is explicit; it never authorizes new files or writes.
"""
from __future__ import annotations

import re

from .candidate_source_evidence import (
    collect_candidate_source_evidence, _SECRET_MATERIAL, _bounded_excerpt,
)
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
    allow_inventory_fallback: bool = False,
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
    # Broad, already-authorized greenfield delivery may need a bounded
    # read-only sample of the existing app. Issue-scoped work stays strict.
    if not requested and allow_inventory_fallback and issue_body is None:
        return _inspect_greenfield_inventory(github, sha=sha, paths=paths)
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


_TEST_PATH = re.compile(r"(?:^|/)(?:tests?|__tests__|e2e)/|(?:\.test|\.spec)\.")
_ENTRY_NAMES = {"server", "main", "index", "app", "page", "layout"}

def _inspect_greenfield_inventory(github: object, *, sha: str, paths: list | tuple) -> dict:
    """Sample real committed code; this is not write scope or proof of delivery."""
    candidates = sorted(path for path in paths if _EXPLICIT.fullmatch(path)
                        and ".." not in path.split("/")
                        and not any(part.startswith(".") for part in path.split("/")))
    def rank(path):
        name = path.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        return (name not in _ENTRY_NAMES, path.count("/"), path)
    code = sorted((path for path in candidates if not _TEST_PATH.search(path)), key=rank)
    tests = sorted(path for path in candidates if _TEST_PATH.search(path))
    selected = code[:2]
    for path in selected[:]:
        stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        match = next((test for test in tests if test.rsplit("/", 1)[-1].startswith(stem + ".")
                      and test not in selected), None)
        if match:
            selected.append(match)
    for path in tests + code:
        if len(selected) >= 4:
            break
        if path not in selected:
            selected.append(path)
    if selected:
        evidence = collect_candidate_source_evidence("", github, sha=sha,
                    continuation_request="\n".join(selected))
        assess_bounded_source_scope(evidence, sha=sha)
        evidence["request_source_paths"] = []
    else:
        evidence = {"status": "no_scoped_source_paths", "assessed_commit": sha,
                    "inspected_files": [], "missing_paths": []}
    governance = {}
    for path in ("README.md", "package.json"):
        if path in paths:
            value = github.get_file_text(path, ref=sha)
            if not isinstance(value, str) or not value.strip() or _SECRET_MATERIAL.search(value):
                raise PermissionError("greenfield governance source invalid")
            excerpt, complete = _bounded_excerpt(value, 4096)
            governance[path] = {"content": excerpt, "complete": complete}
    evidence.update(discovery="immutable_greenfield_inventory_sample",
                    inventory_paths=candidates[:128], inventory_count=len(candidates),
                    inventory_truncated=len(candidates)>128, inventory_sample_paths=selected,
                    governance=governance,
                    limitation="Bounded exact-SHA read-only sample; not a full audit, write scope, test run or release proof.")
    return evidence
