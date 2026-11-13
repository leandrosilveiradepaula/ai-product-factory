"""Offline negative/positive HTTP transport contract for exact-SHA certifiers."""
from __future__ import annotations

import io
import urllib.error
import unittest

from ai_product_factory.bounded_github_evidence_read import (
    GitHubEvidenceTransportBlocked,
    RETRY_DELAYS_SECONDS,
    bounded_github_evidence_read,
)

PATH = "/repos/leandrosilveiradepaula/ai-product-factory/git/trees/" + "a"*40 + "?recursive=1"


def error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.github.com" + PATH,
        code, "gateway", {}, io.BytesIO(b"provider response not persisted")
    )


class BoundedGitHubReadTests(unittest.TestCase):
    def test_502_503_504_recover_only_by_refetching_and_reverifying(self):
        seen, sleeps = [], []
        failures = [502, 503, 504]

        def read(path):
            seen.append(path)
            if failures:
                raise error(failures.pop(0))
            return {"sha": "a"*40, "truncated": False, "tree": []}

        get = bounded_github_evidence_read(read, sleep=sleeps.append)
        result = get(PATH)
        self.assertEqual(result, {"sha":"a"*40,"truncated":False,"tree":[]})
        self.assertEqual(len(seen), 4)
        self.assertEqual(sleeps, list(RETRY_DELAYS_SECONDS))
        # A second GET never reuses previous mutable or stale evidence.
        self.assertEqual(get(PATH)["sha"], "a"*40)
        self.assertEqual(len(seen), 5)

    def test_permanent_gateway_failure_is_bounded_and_sanitized(self):
        calls, delays = [], []

        def unavailable(path):
            calls.append(path)
            raise error(502)

        get = bounded_github_evidence_read(unavailable, sleep=delays.append)
        with self.assertRaisesRegex(
            GitHubEvidenceTransportBlocked, "^github_evidence_gateway_unavailable$"
        ) as captured:
            get(PATH)
        self.assertEqual(len(calls), 4)
        self.assertEqual(delays, list(RETRY_DELAYS_SECONDS))
        self.assertNotIn("provider", str(captured.exception))
        self.assertIsNone(captured.exception.__cause__)

    def test_auth_missing_not_found_rate_limit_are_never_retried(self):
        for code in (400, 401, 403, 404, 409, 422, 429, 500):
            calls, delays = [], []

            def read(path):
                calls.append(path)
                raise error(code)

            get = bounded_github_evidence_read(read, sleep=delays.append)
            with self.subTest(code=code), self.assertRaises(urllib.error.HTTPError):
                get(PATH)
            self.assertEqual(calls, [PATH])
            self.assertEqual(delays, [])

    def test_malformed_or_non_github_endpoint_fails_without_io(self):
        called = []
        get = bounded_github_evidence_read(
            lambda path: called.append(path) or {"source": "invalid"},
            sleep=lambda _: self.fail("no retry"),
        )
        for path in ("", "https://attacker.invalid/", "/user", 14, None):
            with self.subTest(path=path), self.assertRaises(
                GitHubEvidenceTransportBlocked
            ):
                get(path)
        self.assertEqual(called, [])
        # The transport wrapper must NOT convert a malformed JSON result to
        # positive evidence: the independent verifier remains responsible.
        self.assertEqual(get(PATH), {"source": "invalid"})


if __name__ == "__main__":
    unittest.main()
