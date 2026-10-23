"""Offline tests for bounded, identity-linked lint diagnostic extraction."""
import unittest
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import patch, MagicMock

from ai_product_factory.ci_native_lint_diagnostics import (
    _trusted_log_host,
    download_native_job_log,
    summarize_native_lint_errors,
)

PATH = "src/app/(dashboard)/reports/client-page.tsx"
LINE = "2026-10-23T18:33:18Z LINT_CHANGED_ERROR " + PATH + ":121:45 @typescript-eslint/no-explicit-any Unexpected any. Sensitive text must not be persisted."
SECOND = "2026-10-23T18:33:18Z LINT_CHANGED_ERROR " + PATH + ":121:53 jsx-a11y/control-has-associated-label Not labelled secret-value"


class _Response:
    status = 200

    def __init__(self, data):
        self._io = BytesIO(data)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, n=-1):
        return self._io.read(n)


class NativeLintDiagnosticTests(unittest.TestCase):
    def test_allowlisted_identifiers_from_real_crm_failure(self):
        report = summarize_native_lint_errors(LINE + "\n" + SECOND + "\n" + LINE)
        self.assertIsNotNone(report)
        self.assertEqual(report.count(PATH), 2)
        self.assertIn(PATH + ":121:45 @typescript-eslint/no-explicit-any", report)
        self.assertIn(PATH + ":121:53 jsx-a11y/control-has-associated-label", report)
        self.assertNotIn("Sensitive text", report)
        self.assertNotIn("secret-value", report)
        self.assertNotIn("Unexpected any", report)
        self.assertNotIn("2026-10-23", report)

    def test_no_diagnostics_no_evidence_and_never_guess(self):
        self.assertIsNone(summarize_native_lint_errors("Error: lint failed"))
        self.assertIsNone(summarize_native_lint_errors("LINT_CHANGED_FAILED=4"))
        self.assertIsNone(summarize_native_lint_errors(
            "LINT_CHANGED_ERROR ../../secrets.env:1:2 malicious rule"
        ))
        self.assertIsNone(summarize_native_lint_errors(
            "LINT_CHANGED_ERROR src/../.env:1:2 fake/rule"
        ))
        self.assertIsNone(summarize_native_lint_errors(
            "LINT_CHANGED_ERROR https://evil.example/x.ts:1:2 fake/rule"
        ))

    def test_duplicate_and_unbounded_logs_fail_closed(self):
        self.assertIsNone(summarize_native_lint_errors(LINE * 20000))
        many = "\n".join(
            f"LINT_CHANGED_ERROR src/component{i}.tsx:1:2 foo/rule"
            for i in range(21)
        )
        self.assertIsNone(summarize_native_lint_errors(many))
        self.assertIsNone(summarize_native_lint_errors(123))

    def test_signed_urls_accept_only_allowlisted_https_hosts(self):
        self.assertTrue(_trusted_log_host("https://prod.blob.core.windows.net/job/abc?sig=secret"))
        self.assertTrue(_trusted_log_host("https://pipelines.actions.githubusercontent.com/job/abc?sig=secret"))
        for uri in (
            "https://attacker.com/job", "http://prod.blob.core.windows.net/abc",
            "https://prod.blob.core.windows.net.evil.com/abc",
            "https://user:pass@prod.blob.core.windows.net/abc",
            "https://prod.blob.core.windows.net:8443/abc",
        ):
            with self.subTest(uri=uri):
                self.assertFalse(_trusted_log_host(uri))

    def test_authenticated_api_redirect_drops_bearer_for_signed_log(self):
        signed_url = "https://prod.blob.core.windows.net/logs/signed?sig=SECRET_QUERY"
        calls = []

        def initial(req, timeout):
            calls.append(("github", req, timeout))
            raise HTTPError(
                req.full_url, 302, "Moved", {"Location": signed_url}, None
            )

        def cdn(req, timeout):
            calls.append(("cdn", req, timeout))
            self.assertEqual(req.full_url, signed_url)
            self.assertIsNone(req.get_header("Authorization"))
            self.assertIsNone(req.get_header("X-github-api-version"))
            return _Response((LINE + "\n").encode())

        with patch(
            "ai_product_factory.ci_native_lint_diagnostics.request.build_opener"
        ) as opener_factory, patch(
            "ai_product_factory.ci_native_lint_diagnostics.request.urlopen",
            side_effect=cdn,
        ):
            opener_factory.return_value.open.side_effect = initial
            log = download_native_job_log(
                api_url="https://api.github.com",
                repository="owner/repo", job_id=431, token="test-private-token",
            )
        self.assertIn("LINT_CHANGED_ERROR", log)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1].get_header("Authorization"), "Bearer test-private-token")
        self.assertTrue(calls[0][1].full_url.endswith("/actions/jobs/431/logs"))
        self.assertIsNone(calls[1][1].get_header("Authorization"))

    def test_untrusted_redirect_fails_without_following(self):
        with patch(
            "ai_product_factory.ci_native_lint_diagnostics.request.build_opener"
        ) as opener_factory, patch(
            "ai_product_factory.ci_native_lint_diagnostics.request.urlopen"
        ) as cdn:
            opener_factory.return_value.open.side_effect = HTTPError(
                "https://api.github.com/repos/owner/repo/actions/jobs/1/logs",
                302, "Moved", {"Location": "https://evil.example/steal"}, None,
            )
            with self.assertRaisesRegex(RuntimeError, "redirect host"):
                download_native_job_log(
                    api_url="https://api.github.com",
                    repository="owner/repo", job_id=1, token="not-exposed",
                )
            cdn.assert_not_called()

    def test_invalid_identity_never_invokes_network(self):
        for values in (
            {"repository": "invalid"},
            {"job_id": 0},
            {"api_url": "https://evil.example"},
            {"token": ""},
        ):
            args=dict(api_url="https://api.github.com",repository="owner/repo",
                      job_id=431,token="test")
            args.update(values)
            with self.subTest(args=args), patch(
                "ai_product_factory.ci_native_lint_diagnostics.request.build_opener"
            ) as opener_factory:
                with self.assertRaises(ValueError):
                    download_native_job_log(**args)
                opener_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
