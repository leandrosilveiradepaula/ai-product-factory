"""Bounded, read-only preflight for a reported *existing* code expression.

A GitHub issue is a problem statement, not proof that its described current
implementation is present in the immutable journey source. Only explicit
backticked, code-shaped expressions that the issue asserts are ALREADY used
are checked. Missing anchors are a blocking mismatch, not evidence that
the feature is implemented or that a different branch is deployable.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

_ISSUE = re.compile(r"\bissue\s*#([1-9][0-9]{0,6})\b", re.I)
_QUOTED = re.compile(r"`([^`\r\n]{5,160})`")
_BEHAVIOR = re.compile(
    r"\b(?:busca|utiliza|usa|envia|faz|uses|calls|sends|currently|atualmente|hoje)\b",
    re.I,
)
_CODE = re.compile(r"^\.?[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\([A-Za-z0-9_$,'\".\s-]{1,130}\)$")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_QUALIFIED_METHOD = re.compile(
    r"^(?P<class_name>[A-Z][A-Za-z0-9_]*)\."
    r"(?P<method>[A-Za-z_][A-Za-z0-9_]*)\("
    r"(?P<argument>[A-Za-z_][A-Za-z0-9_]*)\)$"
)


def _declaration_at_frozen_source(anchor: str, files: list, source_sha: str) -> bool:
    """Resolve a class-method *reference*, not a literal invocation.

    A qualified reference such as \`ContractService.getContracts(organizationId)\`
    describes a declaration in TypeScript rather than a call expression.
    Require a uniquely matching exact-SHA class file, class declaration,
    method name and parameter identifier; never satisfy arbitrary code calls.
    """
    match = _QUALIFIED_METHOD.fullmatch(anchor)
    if match is None:
        return False
    cls, method, argument = match.group("class_name", "method", "argument")
    matching = [
        f for f in files
        if isinstance(f, Mapping)
        and f.get("complete") is True
        and f.get("assessed_commit") == source_sha
        and isinstance(f.get("content"), str)
        and isinstance(f.get("path"), str)
        and f["path"].startswith(("src/", "app/", "apps/", "packages/"))
        and f["path"].rsplit("/", 1)[-1] in (cls + ".ts", cls + ".tsx")
    ]
    if len(matching) != 1:
        return False
    code = matching[0]["content"]
    if re.search(r"\bclass\s+" + re.escape(cls) + r"\b", code) is None:
        return False
    declaration = (
        r"\b(?:static\s+)?(?:async\s+)?"
        + re.escape(method)
        + r"\s*\(\s*"
        + re.escape(argument)
        + r"\s*(?::\s*[^)\n,]+)?\s*\)"
    )
    return re.search(declaration, code) is not None



class IssueSourceMismatch(PermissionError):
    """Fixed, sanitised mismatch class; no issue/user text in durable error."""


def unique_issue(request: object, repository: object) -> int | None:
    if not isinstance(request, str) or not isinstance(repository, str):
        return None
    if repository.count("/") != 1 or repository not in request:
        return None
    numbers = {int(m.group(1)) for m in _ISSUE.finditer(request)}
    return next(iter(numbers)) if len(numbers) == 1 else None


def check_reported_existing_code(
    *, request: str, repository: str, source_sha: str,
    issue_number: int, issue_body: str, source_evidence: object,
) -> dict:
    if (unique_issue(request, repository) != issue_number
        or not isinstance(source_sha, str) or not _SHA.fullmatch(source_sha)
        or not isinstance(issue_body, str) or len(issue_body) > 20000
        or not isinstance(source_evidence, Mapping)
        or source_evidence.get("assessed_commit") != source_sha):
        raise IssueSourceMismatch("journey_issue_source_evidence_invalid")
    files = source_evidence.get("inspected_files")
    if not isinstance(files, list):
        raise IssueSourceMismatch("journey_issue_source_evidence_invalid")
    # Only interpret a small, declarative sentence (not instructions, headings,
    # historical PR references, acceptance criteria or desired code snippets).
    anchors: list[str] = []
    for sentence in re.split(r"[\n;]+", issue_body):
        if not _BEHAVIOR.search(sentence):
            continue
        for match in _QUOTED.finditer(sentence):
            code = match.group(1).strip()
            if _CODE.fullmatch(code) and code not in anchors:
                anchors.append(code)
    anchors = anchors[:4]
    if not anchors:
        return {"status":"no_asserted_existing_code","issue_number":issue_number,"source_commit":source_sha}
    complete = [
        f["content"] for f in files
        if isinstance(f, Mapping) and f.get("assessed_commit")==source_sha
        and f.get("complete") is True and isinstance(f.get("content"), str)
    ]
    if not complete or source_evidence.get("omitted_paths"):
        # Never treat truncated/uninspected code as an absence proof.
        return {"status":"insufficient_source_evidence","issue_number":issue_number,"source_commit":source_sha}
    # Whitespace differences do not change syntax. Explicit quoted expressions
    # with different identifiers/arguments still must not match.
    normalized = ["".join(c.split()) for c in complete]
    missing = [
        a for a in anchors
        if not any("".join(a.split()) in s for s in normalized)
        and not _declaration_at_frozen_source(a, files, source_sha)
    ]
    if missing:
        raise IssueSourceMismatch("journey_reported_existing_code_not_at_source")
    return {"status":"reported_code_present","issue_number":issue_number,
            "source_commit":source_sha,"checked_anchor_count":len(anchors)}
