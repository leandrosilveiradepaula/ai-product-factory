"""Deterministic, no-model repair of one SHA-verified native Vitest alias error.

This is intentionally narrower than a generic CI fixer. The job/attempt must
have been re-verified through GitHub, matched to the Control Plane's persisted
failure identity, and its exact test file and module must exist on the frozen
candidate commit. Only an approved test file can change. Everything else
continues through the regular paid/guarded repair path.
"""
from __future__ import annotations

import json
import posixpath
import re
from typing import Any

from .work_unit_context import redact_repository_text

_SHA = re.compile(r"[a-f0-9]{40}\Z")
_LOG_ERROR = re.compile(
    r"##\[error\]Error: Cannot find package '"
    r"(?P<alias>@/[A-Za-z0-9_/-]{1,100})' imported from '"
    r"[^'\r\n]+/(?P<test>(?:test|tests)/(?:[A-Za-z0-9_-]+/)*"
    r"[A-Za-z0-9_-]+\.test\.tsx?)'"
)
_IMPORT = re.compile(
    r"""(?m)^(?P<lead>[ \t]*import[ \t]+\{[ \t]*[A-Za-z_$][\w$]*"""
    r"""(?:[ \t]*,[ \t]*[A-Za-z_$][\w$]*)*[ \t]*\}[ \t]+from[ \t]+)"""
    r"""(?P<quote>['"])(?P<alias>@/[A-Za-z0-9_/-]+)(?P=quote)"""
    r"""(?P<tail>;?[ \t]*)$"""
)
_CONFIGS = frozenset({
    "vitest.config.ts", "vitest.config.mts", "vitest.config.js",
    "vite.config.ts", "vite.config.mts", "vite.config.js",
    "vitest.workspace.ts", "vitest.workspace.mts",
})


def _valid_path(path: object) -> bool:
    return (
        isinstance(path, str)
        and bool(re.fullmatch(r"(?:test|tests)/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.test\.tsx?", path))
        and ".." not in path.split("/")
    )


def verified_native_vitest_alias_patch(
    *, github: Any, source: dict, base_commit: str,
    repository: str, write_scopes: tuple[str, ...],
) -> dict[str, str] | None:
    """Return one complete scoped test file or None; never guess from model text.

    A return value permits the existing ChangeSetWorker to create a normal
    Work Unit commit and audit receipt without an LLM call. It does not requeue
    exhausted requests, amend scope, or authorize a production merge.
    """
    repair = source.get("repair")
    proof = source.get("ci_repair_evidence")
    if not isinstance(repair, dict) or repair.get("repair_kind") != "ci":
        return None
    if not isinstance(proof, dict) or proof.get("kind") != "verified_native_ci_repair_candidate":
        return None
    if not any(_valid_path(path) for path in write_scopes):
        # A source-only scope never justifies downloading test job logs.
        return None
    if not _SHA.fullmatch(base_commit):
        raise PermissionError("native Vitest alias repair requires exact candidate SHA")
    if (proof.get("candidate_commit") != base_commit
        or proof.get("repository") != repository
        or repair.get("candidate_commit") != base_commit
        or repair.get("repair_request_id") != proof.get("repair_request_id")
        or repair.get("pr_number") != proof.get("pr_number")):
        raise PermissionError("native Vitest alias repair candidate binding changed")
    persisted = repair.get("failures")
    if not isinstance(persisted, list) or len(persisted) != 1:
        return None
    stored = persisted[0]
    if (not isinstance(stored, dict)
        or stored.get("name") != "native-ci/tests"
        or stored.get("failure_class") != "code"
        or stored.get("conclusion") != "failure"):
        return None
    job_url = stored.get("details_url")
    pattern = (
        r"https://github[.]com/" + re.escape(repository)
        + r"/actions/runs/[1-9][0-9]*/job/([1-9][0-9]*)"
    )
    if not isinstance(job_url, str):
        return None
    match_url = re.fullmatch(pattern, job_url)
    if match_url is None:
        raise PermissionError("native Vitest alias repair has no trusted job URL")
    if not isinstance(proof.get("pr_number"), int) or proof["pr_number"] <= 0:
        raise PermissionError("native Vitest alias repair has no trusted PR")
    # Fetch current GitHub failed-job evidence again for this candidate SHA.
    # Persisted request/issue text alone never authorizes an edit.
    failures = github.get_failed_checks(
        proof["pr_number"], expected_head_sha=base_commit,
    )
    if not isinstance(failures, (tuple, list)) or len(failures) != 1:
        return None
    failure = failures[0]
    if (getattr(failure, "name", None) != "native-ci/tests"
        or getattr(failure, "failure_class", None) != "code"
        or getattr(failure, "conclusion", None) != "failure"
        or getattr(failure, "details_url", None) != job_url):
        return None
    reader = getattr(github, "native_log_reader", None)
    if not callable(reader):
        return None
    try:
        log = reader(int(match_url.group(1)))
    except (ValueError, RuntimeError, OSError):
        return None
    if not isinstance(log, str) or len(log.encode("utf-8")) > 524288:
        return None
    log = re.sub(r"\x1b\[[0-9;]*m", "", log)
    if log.count("##[error]Error: Cannot find package") != 1:
        return None
    matches = list(_LOG_ERROR.finditer(log))
    if len(matches) != 1:
        return None
    alias, test_path = matches[0].group("alias", "test")
    if (not _valid_path(test_path)
        or test_path not in write_scopes
        or alias.count("/") < 1
        or any(part in ("", ".", "..") for part in alias[2:].split("/"))):
        return None

    paths = github.list_file_paths(ref=base_commit)
    if not isinstance(paths, (tuple, list)) or test_path not in paths:
        return None
    if any(p in paths for p in _CONFIGS):
        # Existing Vitest configuration can intentionally route @/ differently.
        return None
    if "tsconfig.json" not in paths or "package.json" not in paths:
        return None
    try:
        tsconfig_text = github.get_file_text("tsconfig.json", ref=base_commit)
        package_text = github.get_file_text("package.json", ref=base_commit)
        if (not isinstance(tsconfig_text, str) or len(tsconfig_text) > 8192
            or not isinstance(package_text, str) or len(package_text) > 8192):
            return None
        tsconfig = json.loads(tsconfig_text)
        package = json.loads(package_text)
    except (ValueError, TypeError):
        return None
    if (tsconfig.get("compilerOptions", {}).get("paths", {}).get("@/*") != ["./src/*"]
        or package.get("scripts", {}).get("test") != "vitest run"
        or "vite-tsconfig-paths" in (package.get("dependencies") or {})
        or "vite-tsconfig-paths" in (package.get("devDependencies") or {})):
        return None

    module_stem = "src/" + alias[2:]
    candidates = [p for p in (module_stem + ".ts", module_stem + ".tsx") if p in paths]
    if len(candidates) != 1:
        return None
    content = github.get_file_text(test_path, ref=base_commit)
    if not isinstance(content, str) or len(content.encode("utf-8")) > 16384:
        return None
    if redact_repository_text(content) != content:
        raise PermissionError("native Vitest alias test contains unsafe content")
    matches = [m for m in _IMPORT.finditer(content) if m.group("alias") == alias]
    if len(matches) != 1:
        return None
    specifier = posixpath.relpath(module_stem, start=posixpath.dirname(test_path))
    if not specifier.startswith(".") or specifier.startswith("/"):
        return None
    m = matches[0]
    corrected = content[:m.start("alias")] + specifier + content[m.end("alias"):]
    if corrected == content or redact_repository_text(corrected) != corrected:
        return None
    return {test_path: corrected}
