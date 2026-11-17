"""Strict read-only credential boundary for independent cross-repository B4 ancestry.

The current-repository GitHub Actions GITHUB_TOKEN cannot read a private target
repository. Only an explicitly resolved installation credential or
FACTORY_GITHUB_TOKEN can read the exact target SHA comparison; a failure
must leave the entire independent B4 criterion unverified.
"""
from __future__ import annotations

import re
from collections.abc import Callable

from .bounded_github_evidence_read import bounded_github_evidence_read
from .github_auth import resolve_github_token

TARGET_COMPARE = re.compile(
    r"/repos/(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/compare/"
    r"[0-9a-f]{40}\.\.\.[0-9a-f]{40}\Z"
)


def cross_repo_b4_reader(
    *, factory_repository: str,
    github_read: Callable[[str, str], object],
    token_resolver: Callable[[str], str] = resolve_github_token,
) -> Callable[[str], object]:
    """Return a narrowly scoped, non-caching cross-repo GitHub compare reader.

    No arbitrary repository URL, file, token, release, PR, mutating endpoint,
    or current-Factory endpoint can be requested with the cross-repo token.
    Credential absence fails closed; no fallback to Actions GITHUB_TOKEN.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", factory_repository):
        raise ValueError("b4_factory_repository_invalid")
    if not callable(github_read) or not callable(token_resolver):
        raise TypeError("b4_cross_repo_reader_invalid")

    def read(path: str) -> object:
        match = TARGET_COMPARE.fullmatch(path) if isinstance(path, str) else None
        if not match:
            raise PermissionError("b4_cross_repo_path_denied")
        target = match.group("repository")
        if target.lower() == factory_repository.lower():
            raise PermissionError("b4_same_repo_cross_token_denied")
        token = token_resolver(target)
        if not isinstance(token, str) or not token.strip():
            raise PermissionError("b4_explicit_cross_repo_credential_required")
        return github_read(token, path)

    return bounded_github_evidence_read(read)
