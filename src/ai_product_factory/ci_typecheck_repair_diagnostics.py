"""Reconfirm bounded native TypeScript diagnostics for an existing CI repair.

The caller has checked the live PR and supplies get_failed_checks() scoped to
its candidate SHA. Only the previously persisted trusted job URLs may
contribute. No raw job log, free text, or model instructions are forwarded.
"""
from __future__ import annotations

import re

_PREFIX = "Verified native TypeScript identifiers only: "
_LINE = re.compile(
    r"(?:src|app|apps|packages|test|tests|scripts|docs)/"
    r"[A-Za-z0-9_.()/\[\]-]+:[1-9][0-9]{0,5}:[1-9][0-9]{0,5}"
    r" TS[0-9]{4,5}(?: import=@/[A-Za-z0-9_./-]{1,150})?\Z"
)


def _sanitized_typecheck_identifiers(summary: object) -> list[str]:
    if not isinstance(summary, str) or len(summary) > 2000:
        return []
    if summary.count(_PREFIX) != 1:
        return []
    text = summary.split(_PREFIX, 1)[1]
    if len(text) > 1600:
        return []
    entries = text.split("; ")
    if not 1 <= len(entries) <= 20:
        return []
    for entry in entries:
        if not _LINE.fullmatch(entry):
            return []
        path = entry.split(":", 1)[0]
        if any(part in ("", ".", "..") or part.startswith(".")
               for part in path.split("/")):
            return []
        if " import=" in entry:
            alias = entry.split(" import=", 1)[1]
            if "//" in alias or ".." in alias or ".env" in alias.lower():
                return []
    return list(dict.fromkeys(entries))


def verified_typecheck_repair_diagnostics(
    *, source: dict, failures: object,
) -> tuple[str, ...]:
    repair = source.get("repair")
    if not isinstance(repair, dict) or repair.get("repair_kind") != "ci":
        return ()
    stored = repair.get("failures")
    if not isinstance(stored, list) or not stored:
        raise PermissionError("CI repair has no durable failed-job identities")
    native = [
        entry for entry in stored
        if isinstance(entry, dict) and entry.get("name") == "native-ci/typescript"
    ]
    if not native:
        return ()
    if len(native) > 20 or any(
        entry.get("failure_class") != "code"
        or entry.get("conclusion") != "failure"
        or not isinstance(entry.get("details_url"), str)
        or not re.fullmatch(
            r"https://github[.]com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/"
            r"actions/runs/[1-9][0-9]*/job/[1-9][0-9]*",
            entry["details_url"],
        ) for entry in native
    ):
        raise PermissionError("CI repair failed-job identities are invalid")

    # Every candidate match was independently re-fetched from GitHub native
    # Actions by expected SHA; persisted entries are only an allowlist.
    if not isinstance(failures, (list, tuple)):
        raise PermissionError("verified native CI check list is missing")
    allowed = {entry["details_url"] for entry in native}
    result: list[str] = []
    for failure in failures:
        if (getattr(failure, "name", None) != "native-ci/typescript"
            or getattr(failure, "failure_class", None) != "code"
            or getattr(failure, "conclusion", None) != "failure"
            or getattr(failure, "details_url", None) not in allowed):
            continue
        for entry in _sanitized_typecheck_identifiers(
            getattr(failure, "summary", None)
        ):
            if entry not in result:
                result.append(entry)
            if len(result) > 20:
                raise PermissionError("unbounded verified TypeScript diagnostics")
    if not result:
        # Don't spend another model call on an opaque TypeScript failure.
        raise PermissionError("verified TypeScript repair diagnostics unavailable")
    return tuple(result)
