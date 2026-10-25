"""SHA-bound, bounded provenance for a stale literal-count Vitest contract.

A model never sees raw GitHub logs. Automatic test-scope amendment is possible
only when a known successful source change makes the stale count demonstrable
against the candidate commit and the test references that same source file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .work_unit_context import redact_repository_text

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_PATH = re.compile(r"(?:src|test|tests|app|apps|packages)/[A-Za-z0-9_./()-]{1,190}\Z")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_LOC = re.compile(
    r"(?:src|test|tests|app|apps|packages)/[A-Za-z0-9_./()-]+"
    r"\.(?:test|spec)\.tsx?:[1-9][0-9]{0,5}:[1-9][0-9]{0,5}"
)
_FAIL = re.compile(
    r"AssertionError: expected (?P<actual>[0-9]{1,3}) to be "
    r"(?P<expected>[0-9]{1,3}) // Object[.]is equality"
)
_CONST = re.compile(
    r"""(?m)^\s*const\s+(?P<identifier>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"""
    r"""readFileSync\(\s*['"](?P<source>(?:src|app|apps|packages)/[A-Za-z0-9_./()-]+)['"]"""
    r"""\s*,\s*['"]utf8['"]\s*\);?\s*$"""
)
_MATCH = re.compile(
    r"(?P<identifier>[A-Za-z_][A-Za-z0-9_]*)[.]match"
    r"\(/(?P<literal>[A-Za-z0-9_={}\\-]{3,140})/g\)"
)
_TO_BE = re.compile(r"[.]toBe\((?P<count>[0-9]{1,3})\)")
_MAX_LOG = 1024 * 1024
_MAX_SOURCE = 30000
_PREFIX = "Verified native Vitest count: "


@dataclass(frozen=True)
class StaticCountContract:
    test_path: str
    source_path: str
    expected: int
    actual: int

    def as_summary(self) -> str:
        return (
            f"{_PREFIX}test={self.test_path} source={self.source_path}"
            f" expected={self.expected} actual={self.actual}"
        )


def _read(github: object, path: str, sha: str) -> str | None:
    try:
        data = github.get_file_text(path, ref=sha)
    except (RuntimeError, OSError, ValueError, KeyError):
        return None
    if not isinstance(data, str) or len(data.encode("utf-8")) > _MAX_SOURCE:
        return None
    if redact_repository_text(data) != data:
        return None
    return data


def verify_native_vitest_static_count(
    log: str, *, github: object, candidate_sha: str,
) -> StaticCountContract | None:
    """Return no receipt unless the log, test and source agree on one mismatch.

    The caller *already* binds the native Actions job id to exact
    workflow run/attempt/SHA. Re-read both source files at that SHA.
    """
    if (not isinstance(log, str) or len(log.encode("utf-8")) > _MAX_LOG
        or not _SHA.fullmatch(candidate_sha)):
        return None
    cleaned = _ANSI.sub("", log)
    failures = list(_FAIL.finditer(cleaned))
    # No attestation for mixed failures, generic stacktraces or multiple tests.
    # GitHub logs repeat the same assertion in Vitest and Actions output.
    # A mixed assertion inventory cannot attest a single test-scope change.
    pairs={(m.group("expected"), m.group("actual")) for m in failures}
    if len(pairs)!=1 or not 1<=len(failures)<=3:
        return None
    expected, actual = int(failures[0].group("expected")), int(failures[0].group("actual"))
    if expected == actual or expected > 100 or actual > 100:
        return None
    locations = {
        m.group(0) for m in _LOC.finditer(cleaned)
    }
    if not 1<=len(locations)<=2:
        return None
    # One test file / statement may appear twice in the GitHub annotation.
    unique_paths={v.rsplit(":", 2)[0] for v in locations}
    unique_lines={int(v.rsplit(":", 2)[1]) for v in locations}
    if len(unique_paths)!=1 or len(unique_lines)!=1:
        return None
    test_path=next(iter(unique_paths))
    line=next(iter(unique_lines))
    if not _PATH.fullmatch(test_path) or ".." in test_path.split("/") or "//" in test_path:
        return None
    test_text=_read(github,test_path,candidate_sha)
    if test_text is None:
        return None
    rows=test_text.splitlines()
    if line>len(rows):
        return None
    assertion=rows[line-1]
    found=_MATCH.search(assertion)
    expected_literal=_TO_BE.search(assertion)
    if (not found or not expected_literal
        or int(expected_literal.group("count"))!=expected
        or "expect(" not in assertion or ".length" not in assertion):
        return None
    variables=[
        m.group("source") for m in _CONST.finditer(test_text)
        if m.group("identifier")==found.group("identifier")
    ]
    if len(variables)!=1:
        return None
    source_path=variables[0]
    if not _PATH.fullmatch(source_path) or ".." in source_path.split("/") or "//" in source_path:
        return None
    pattern=found.group("literal")
    # Only a literal grep pattern is admissible, not arbitrary dynamic regex.
    if re.search(r"\\(?![{}])",pattern):
        return None
    literal=pattern.replace(r"\{","{").replace(r"\}","}")
    source_text=_read(github,source_path,candidate_sha)
    if source_text is None or source_text.count(literal)!=actual:
        return None
    return StaticCountContract(
        test_path=test_path,source_path=source_path,
        expected=expected,actual=actual,
    )
