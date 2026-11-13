"""Bounded retry of *read-only* GitHub evidence sources.

GitHub's immutable commit/tree endpoints may intermittently return a 502 while
a certification revalidates many independent sources. An isolated transport
fault must not require changing source identity, bypassing the monotonic guard
or publishing an unverified certificate.

This wrapper does not retry missing, forbidden, or rate-limited sources, does
not change response data, cache mutable run/ref/status results or perform any
GitHub write. The independent verifiers still compare every fetched field.
"""
from __future__ import annotations

import time
import urllib.error
from collections.abc import Callable
from typing import Any


RETRYABLE_GATEWAY_STATUS = frozenset({502, 503, 504})
RETRY_DELAYS_SECONDS = (0.5, 1.5, 3.0)


class GitHubEvidenceTransportBlocked(RuntimeError):
    """Only a fixed diagnostic is safe to expose in Actions logs."""


def bounded_github_evidence_read(
    read: Callable[[str], Any], *,
    sleep: Callable[[float], None] = time.sleep,
) -> Callable[[str], Any]:
    """Return a fresh read for every call, with at most three gateway retries.

    A persistent gateway error blocks before any readiness write. Never retry
    401/403/404, 429 (explicit rate limit), or malformed JSON: these are not
    independent evidence. Do not cache responses or cross process lifetimes.
    """
    if not callable(read) or not callable(sleep):
        raise TypeError("invalid_github_evidence_reader")

    def get(path: str) -> Any:
        if not isinstance(path, str) or not path.startswith("/repos/"):
            raise GitHubEvidenceTransportBlocked("github_evidence_path_invalid")
        for attempt in range(len(RETRY_DELAYS_SECONDS) + 1):
            try:
                return read(path)
            except urllib.error.HTTPError as error:
                if error.code not in RETRYABLE_GATEWAY_STATUS:
                    raise
                if attempt == len(RETRY_DELAYS_SECONDS):
                    raise GitHubEvidenceTransportBlocked(
                        "github_evidence_gateway_unavailable"
                    ) from None
                sleep(RETRY_DELAYS_SECONDS[attempt])
        raise GitHubEvidenceTransportBlocked("github_evidence_gateway_unavailable")

    return get
