"""Exact-SHA, read-only caller context for an explicitly scoped work unit.

A semantic "*-call-sites" scope is a request for evidence, never authority to
edit those callers. Missing evidence must fail BEFORE any paid model call.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

_CODE = (".py", ".ts", ".tsx", ".js", ".jsx")
_NON_FEATURE = {"service", "services", "query", "call", "calls", "site", "sites", "caller", "callers", "code"}


def discover_verified_readonly_callers(
    *, github, source: dict, base_commit: str, all_paths: tuple[str, ...],
    existing_paths: tuple[str, ...], limit: int,
) -> tuple[str, ...]:
    assignment = source.get("assignment")
    if not isinstance(assignment, dict):
        return ()
    scopes = assignment.get("scope_keys")
    if not isinstance(scopes, list):
        return ()
    semantic = [
        value.lower() for value in scopes if isinstance(value, str)
        and re.search(r"(?:call[-_ ]?sites|callers)", value, re.IGNORECASE)
    ]
    if not semantic:
        return ()

    criteria = source.get("task")
    criteria = criteria.get("acceptance_criteria") if isinstance(criteria, dict) else []
    criteria_text = " ".join(str(x) for x in criteria).lower() if isinstance(criteria, list) else ""
    if not any(word in criteria_text for word in ("chamad", "caller", "call site", "call-site")):
        return ()

    source_paths = [
        path for path in existing_paths if path in all_paths
        and path.startswith(("src/", "app/", "apps/", "packages/"))
        and path.endswith(_CODE) and not re.search(r"\.(?:test|spec)\.", path)
    ]
    if not source_paths:
        raise PermissionError("call-site evidence requires a pinned source file")

    method_names: set[str] = set()
    class_names: set[str] = set()
    features: set[str] = set()
    for path in source_paths[:3]:
        name = PurePosixPath(path).stem
        words = [w.lower() for w in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", name)]
        features.update(w for w in words if len(w) >= 4 and w not in _NON_FEATURE)
        original = github.get_file_text(path, ref=base_commit)
        class_names.update(re.findall(r"\bclass\s+([A-Za-z][A-Za-z0-9_]*)", original))
        method_names.update(re.findall(
            r"\bstatic\s+(?:async\s+)?([A-Za-z][A-Za-z0-9_]*)\s*\(",
            original,
        ))
    if not features or not class_names or not method_names:
        raise PermissionError("call-site evidence source symbols unavailable")

    candidates = [
        path for path in all_paths if path not in existing_paths
        and path.startswith(("src/", "app/", "apps/", "packages/"))
        and path.endswith(_CODE)
        and any(feature in path.lower() for feature in features)
    ]
    def rank(path: str) -> tuple[int, int, str]:
        lower = path.lower()
        if "/actions." in lower or lower.endswith("/actions.ts"):
            tier = 0
        elif "/hooks/" in lower or "use" in PurePosixPath(path).name:
            tier = 1
        elif "/app/" in lower:
            tier = 2
        elif "/types/" in lower:
            tier = 3
        else:
            tier = 4
        return tier, len(path), path
    candidates.sort(key=rank)
    verified: list[str] = []
    for path in candidates[:24]:
        try:
            raw = github.get_file_text(path, ref=base_commit)
        except ValueError as exc:
            if "repository context file too large" in str(exc):
                continue
            raise
        # Require an actual reference to a pinned class + its method, or a
        # method call in a feature-named downstream module, not filenames alone.
        has_class_reference = any(re.search(
            r"\b" + re.escape(name) + r"\s*\.\s*(?:" +
            "|".join(re.escape(method) for method in sorted(method_names)) + r")\s*\(",
            raw,
        ) for name in class_names)
        has_method_call = any(re.search(
            r"\b" + re.escape(method) + r"\s*\(", raw,
        ) for method in method_names)
        if has_class_reference or has_method_call:
            verified.append(path)
            if len(verified) >= 3:
                break
    if not verified or not any("/actions." in p or "/actions/" in p for p in verified):
        raise PermissionError("pinned call-site and server action evidence missing")

    remaining = max(0, limit - len(verified))
    if remaining == 0:
        return tuple(verified)

    extras: list[str] = []
    related = set(features)
    if "deal" in criteria_text or "deal_id" in criteria_text:
        related.add("deal")
    for path in all_paths:
        low = path.lower()
        if (path not in existing_paths and path not in verified
            and path.endswith(_CODE) and "/types/" in low
            and any(feature in low for feature in related)):
            extras.append(path)
    auth_required = any(word in criteria_text for word in (
        "rbac", "autoriza", "authentication", "permission", "permiss", "server-side",
    ))
    if auth_required:
        extras.extend(
            path for path in all_paths
            if path not in existing_paths and path not in verified
            and path.startswith(("src/lib/", "app/lib/", "apps/"))
            and path.endswith(_CODE)
            and re.search(r"(?:auth|permission|role)", path.lower())
        )
    extras = sorted(set(extras), key=lambda p: (
        0 if "/types/" in p else 1, len(p), p
    ))
    return tuple([*verified, *extras[:remaining]])
