"""Bounded exact-SHA code evidence for the latest authorized existing-project task.

The repository's task record is governance, not proof that a listed defect remains.
This reader never writes to GitHub, guesses code paths, or certifies product readiness.
"""
from __future__ import annotations

import re

_AUTHORIZED = re.compile(
    r"^##[ \t]+(?:(?:Additional[ \t]+)?Authorized[ \t]+task|"
    r"Tarefa[ \t]+autorizada)\b[^\n]*$",
    re.IGNORECASE | re.MULTILINE,
)
_H2 = re.compile(r"^##[ \t]+", re.MULTILINE)
_BACKTICK = re.compile(r"\x60([^\x60\r\n]{1,240})\x60")
_CODE_PATH = re.compile(
    r"^(?:src|test|tests|app|apps|pages|lib|packages|scripts)/"
    r"[A-Za-z0-9_./()\-]+\.(?:py|tsx?|jsx?|cjs|mjs)$"
)
_SECRET_MATERIAL = re.compile(
    r"(?i)(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"(?:sk-proj-|sb_secret_|github_pat_|ghp_)[A-Za-z0-9_-]{10,})"
)
_MAX_FILES = 4
_MAX_BYTES = 24000
_MAX_FILE_BYTES = 14000


def _latest_scope(task_record: str) -> tuple[str | None, list[str]]:
    if not isinstance(task_record, str):
        raise ValueError("candidate task record must be text")
    headings = list(_AUTHORIZED.finditer(task_record))
    if not headings:
        return None, []
    latest = headings[-1]
    end = _H2.search(task_record, latest.end())
    section = task_record[latest.end():end.start() if end else len(task_record)]
    paths: list[str] = []
    for raw in _BACKTICK.findall(section):
        path = raw.strip()
        if (_CODE_PATH.fullmatch(path)
            and ".." not in path.split("/")
            and path not in paths):
            paths.append(path)
    return latest.group().strip(), paths


def _request_paths(continuation_request: str | None) -> list[str]:
    """Prioritize read-only source evidence from a new request; never authorize writes."""
    if not isinstance(continuation_request, str):
        return []
    paths: list[str] = []
    pattern = r"(?:src|test|tests|app|apps|pages|lib|packages|scripts)/[A-Za-z0-9_./()\-]+\.(?:tsx?|jsx?|py|cjs|mjs)"
    for match in re.finditer(pattern, continuation_request):
        path = match.group()
        if _CODE_PATH.fullmatch(path) and ".." not in path.split("/") and path not in paths:
            paths.append(path)
    return paths


def _bounded_excerpt(source: str, limit: int) -> tuple[str, bool]:
    encoded = source.encode("utf-8")
    if len(encoded) <= limit:
        return source, True
    marker = "\n\n[OMITTED MIDDLE: partial source evidence]\n\n".encode("utf-8")
    if limit <= len(marker):
        return encoded[:limit].decode("utf-8", "ignore"), False
    source_budget = limit - len(marker)
    prefix_bytes = source_budget * 2 // 3
    suffix_bytes = source_budget - prefix_bytes
    prefix = encoded[:prefix_bytes].decode("utf-8", "ignore")
    suffix = encoded[-suffix_bytes:].decode("utf-8", "ignore") if suffix_bytes else ""
    return prefix + marker.decode("utf-8") + suffix, False


def collect_candidate_source_evidence(
    task_record: str, github: object, *, sha: str, continuation_request: str | None = None
) -> dict:
    """Inspect current task's code/test files at the *verified* pinned GitHub SHA.

    Source snippets are untrusted evidence, not executable instructions or a whole
    repository audit. Missing or truncated files are explicit; there is no fallback
    to main or a floating branch.
    """
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise PermissionError("candidate source evidence requires exact SHA")
    heading, governed = _latest_scope(task_record)
    request_paths = _request_paths(continuation_request)
    requested = list(dict.fromkeys([*request_paths, *governed]))
    if not requested:
        return {
            "status": "no_scoped_source_paths", "scope_heading": heading,
            "assessed_commit": sha, "inspected_files": [], "missing_paths": [],
            "limitation": "No repository code was inspected; do not infer missing implementation.",
        }
    all_paths = github.list_file_paths(ref=sha)
    if not isinstance(all_paths, (tuple, list)) or not all(
        isinstance(path, str) for path in all_paths
    ):
        raise PermissionError("candidate committed path inventory is invalid")
    existing = set(all_paths)
    missing = [path for path in requested if path not in existing]
    available = [path for path in requested if path in existing]
    # Keep all four current task paths represented, including companion tests,
    # without increasing the fixed total prompt byte budget.
    sources: list[tuple[str, str]] = []
    for path in available[:_MAX_FILES]:
        source = github.get_file_text(path, ref=sha)
        if not isinstance(source, str) or not source.strip():
            raise PermissionError("candidate source is blank or invalid")
        if _SECRET_MATERIAL.search(source):
            raise PermissionError("candidate source contains potential secret material")
        sources.append((path, source))
    limits = [min(_MAX_FILE_BYTES, len(source.encode("utf-8"))) for _, source in sources]
    while sum(limits) > _MAX_BYTES:
        largest = max(limits)
        indices = [index for index, size in enumerate(limits) if size == largest]
        next_largest = max((size for size in limits if size < largest), default=0)
        overflow = sum(limits) - _MAX_BYTES
        level_bytes = (largest - next_largest) * len(indices)
        if level_bytes <= overflow:
            for index in indices:
                limits[index] = next_largest
        else:
            reduction, remainder = divmod(overflow, len(indices))
            for position, index in enumerate(indices):
                limits[index] -= reduction + int(position < remainder)
    inspected = []
    for (path, source), limit in zip(sources, limits):
        excerpt, complete = _bounded_excerpt(source, limit)
        inspected.append({
            "path": path, "assessed_commit": sha, "content": excerpt,
            "complete": complete, "total_lines": source.count("\n") + 1,
        })
    return {
        "status": "bounded_source_inspected" if inspected else "scoped_source_missing",
        "scope_heading": heading, "request_source_paths": request_paths,
        "governance_scope_paths": governed,
        "assessed_commit": sha, "inspected_files": inspected,
        "missing_paths": missing,
        "omitted_paths": available[len(inspected):],
        "limitation": (
            "Only request-named or latest task-scope files above were inspected. "
            "An open issue, previous task description, or truncated excerpt does "
            "not prove a defect remains. Do not infer product-wide readiness."
        ),
    }
