"""Deterministic, no-model confidence in code scoped to a pinned Git commit.

Missing paths may be intended NEW files; large scopes may be intentionally
partially inspected. Neither is a human gate or proof of a defect. Only forged
or inconsistent source receipts block semantic planning before paid models.
"""
from __future__ import annotations

import re

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_PATH = re.compile(
    r"(?:src|test|tests|app|apps|pages|lib|packages|scripts)/"
    r"[A-Za-z0-9_./()-]+\.(?:py|tsx?|jsx?|cjs|mjs)\Z"
)
_CODES = frozenset({
    "source_sha_unverified",
    "source_evidence_inconsistent",
    "source_paths_not_inspected",
})


class SourceScopeBlocked(PermissionError):
    """Fixed, non-sensitive reason code safe for a durable run error."""

    def __init__(self, code: str):
        if code not in _CODES:
            raise ValueError("unsupported source scope blocker")
        super().__init__(code)
        self.code = code


def _checked_paths(raw: object) -> list[str]:
    if not isinstance(raw, list) or len(raw) > 64:
        raise SourceScopeBlocked("source_evidence_inconsistent")
    found = []
    for path in raw:
        if (not isinstance(path, str) or len(path) > 240
                or _PATH.fullmatch(path) is None
                or ".." in path.split("/") or path in found):
            raise SourceScopeBlocked("source_evidence_inconsistent")
        found.append(path)
    return found


def assess_bounded_source_scope(evidence: object, *, sha: str) -> dict:
    """Read-only classification of the exact-SHA source inspection receipt.

    Admitted evidence can be complete, partial, new_files_only or unscoped.
    Only *structural inconsistency* is blocked: missing source files alone
    must not prevent a real developer from creating them.
    """
    if not isinstance(sha, str) or _SHA.fullmatch(sha) is None:
        raise SourceScopeBlocked("source_sha_unverified")
    if not isinstance(evidence, dict) or evidence.get("assessed_commit") != sha:
        raise SourceScopeBlocked("source_sha_unverified")
    missing = _checked_paths(evidence.get("missing_paths", []))
    omitted = _checked_paths(evidence.get("omitted_paths", []))
    status = evidence.get("status")
    inspected = evidence.get("inspected_files")
    if not isinstance(inspected, list) or len(inspected) > 3:
        raise SourceScopeBlocked("source_evidence_inconsistent")
    seen: set[str] = set()
    truncated = 0
    for entry in inspected:
        if not isinstance(entry, dict):
            raise SourceScopeBlocked("source_evidence_inconsistent")
        path = entry.get("path")
        if (not isinstance(path, str) or len(path) > 240
                or _PATH.fullmatch(path) is None
                or ".." in path.split("/") or path in seen
                or entry.get("assessed_commit") != sha
                or path in missing or path in omitted):
            raise SourceScopeBlocked("source_evidence_inconsistent")
        seen.add(path)
        content = entry.get("content")
        if not isinstance(content, str) or not content.strip():
            raise SourceScopeBlocked("source_evidence_inconsistent")
        if type(entry.get("complete")) is not bool:
            raise SourceScopeBlocked("source_evidence_inconsistent")
        truncated += int(not entry["complete"])
        if len(content.encode("utf-8")) > 14200:
            raise SourceScopeBlocked("source_evidence_inconsistent")

    if status == "no_scoped_source_paths":
        if inspected or missing or omitted:
            raise SourceScopeBlocked("source_evidence_inconsistent")
        coverage = "unscoped"
    elif status == "scoped_source_missing":
        if inspected or not missing or omitted:
            raise SourceScopeBlocked("source_evidence_inconsistent")
        coverage = "new_files_only"
    elif status == "bounded_source_inspected":
        if not inspected:
            raise SourceScopeBlocked("source_evidence_inconsistent")
        coverage = "partial" if (missing or omitted or truncated) else "complete"
    else:
        raise SourceScopeBlocked("source_paths_not_inspected")

    return {
        "status": coverage,
        "assessed_commit": sha,
        "inspected_count": len(inspected),
        "missing_count": len(missing),
        "omitted_count": len(omitted),
        "truncated_count": truncated,
        "code_inspected": bool(inspected),
        "limitation": (
            "Only source identity and bounded scope assessed; no model, CI, "
            "Preview, release or full E2E is verified"
        ),
    }
