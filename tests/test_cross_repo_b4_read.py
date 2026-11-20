"""Private B4 comparison never exposes GitHub App credentials to the certifier."""
import json
import unittest
from unittest.mock import patch

from ai_product_factory.cross_repo_b4_read import (
    cross_repo_b4_reader, resolve_b4_cross_repo_token,
    _read_b4_immutable_compare_from_broker,
)
from ai_product_factory.bounded_github_evidence_read import (
    GitHubEvidenceTransportBlocked,
)

FACTORY = "leandrosilveiradepaula/ai-product-factory"
STUDIO = "leandrosilveiradepaula/dark-channel-studio"
A, B = "a" * 40, "b" * 40
COMPARE = "/repos/" + STUDIO + "/compare/" + A + "..." + B
BROKER = "https://example.supabase.co/functions/v1/factory-runtime-control-plane"
OIDC = "signed-oidc.payload.signature"
RESPONSE = {
    "status": "ahead", "behind_by": 0, "ahead_by": 2,
    "total_commits": 2, "truncated": False,
    "files": [{"filename": "docs/OPERATIONS.md", "status": "modified"}],
}


class CrossRepoB4ReadTests(unittest.TestCase):
    def test_regular_event_uses_only_target_credential(self):
        calls = []
        def resolve(repo):
            calls.append(("resolve", repo))
            return "fake-target-credential"
        def read(token, path):
            calls.append(("get", token, path))
            return RESPONSE
        with patch.dict("os.environ", {}, clear=True):
            get = cross_repo_b4_reader(factory_repository=FACTORY,
                                        github_read=read, token_resolver=resolve)
            self.assertEqual(get(COMPARE), RESPONSE)
        self.assertEqual(calls, [
            ("resolve", STUDIO),
            ("get", "fake-target-credential", COMPARE),
        ])

    def test_workflow_run_uses_server_side_read_only_broker_not_token(self):
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "workflow_run",
            "GITHUB_REPOSITORY": FACTORY,
            "GITHUB_TOKEN": "native-must-not-be-used",
            "FACTORY_GITHUB_TOKEN": "cross-repo-pat-must-not-be-used",
            "SUPABASE_URL": BROKER,
            "SUPABASE_SECRET_KEY": OIDC,
        }
        with patch.dict("os.environ", env, clear=True):
            with patch(
                "ai_product_factory.cross_repo_b4_read._read_b4_immutable_compare_from_broker",
                return_value=RESPONSE,
            ) as broker:
                with patch(
                    "ai_product_factory.cross_repo_b4_read.resolve_github_token",
                    side_effect=AssertionError("no client-side App token"),
                ):
                    get = cross_repo_b4_reader(
                        factory_repository=FACTORY,
                        github_read=lambda *_: self.fail("GitHub direct called"),
                        token_resolver=lambda *_: self.fail("PAT resolution attempted"),
                    )
                    self.assertEqual(get(COMPARE), RESPONSE)
                    broker.assert_called_once_with(COMPARE)

    def test_workflow_run_direct_token_resolver_denied_even_with_secret(self):
        with patch.dict("os.environ", {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "workflow_run",
            "FACTORY_GITHUB_TOKEN": "must-not-escape",
        }, clear=True):
            with patch("ai_product_factory.cross_repo_b4_read.resolve_github_token",
                       side_effect=AssertionError("must not mint token")):
                with self.assertRaisesRegex(PermissionError,
                                            "b4_certifier_direct_token_forbidden"):
                    resolve_b4_cross_repo_token(STUDIO)

    def test_broker_uses_only_oidc_and_fixed_exact_sha_request(self):
        requests = []
        def transport(method, url, headers, body):
            requests.append((method, url, headers, json.loads(body)))
            return 200, RESPONSE
        with patch.dict("os.environ", {
            "GITHUB_ACTIONS":"true", "GITHUB_EVENT_NAME":"workflow_run",
            "SUPABASE_URL":BROKER, "SUPABASE_SECRET_KEY":OIDC,
            "GITHUB_TOKEN":"native-must-not-cross", "FACTORY_GITHUB_TOKEN":"other-secret",
        }, clear=True):
            result = _read_b4_immutable_compare_from_broker(
                COMPARE, transport=transport)
        self.assertEqual(result, RESPONSE)
        self.assertEqual(len(requests), 1)
        method,url,headers,body=requests[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, BROKER+"/github-app/read-only-compare")
        self.assertEqual(body, {
            "repository": STUDIO, "predecessor": A, "current": B})
        self.assertEqual(headers["Authorization"], "Bearer "+OIDC)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertNotIn("native-must-not-cross", repr(requests))
        self.assertNotIn("other-secret", repr(requests))

    def test_missing_broker_or_oidc_credential_never_falls_back(self):
        variants = [
            {"SUPABASE_URL": "", "SUPABASE_SECRET_KEY": OIDC},
            {"SUPABASE_URL": BROKER, "SUPABASE_SECRET_KEY": ""},
            {"SUPABASE_URL": BROKER, "SUPABASE_SECRET_KEY": "sb_secret_not_oidc"},
            {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SECRET_KEY": OIDC},
            {"SUPABASE_URL": BROKER, "SUPABASE_SECRET_KEY": "bad-token"},
        ]
        for variation in variants:
            with self.subTest(variation=variation):
                with patch.dict("os.environ", {
                    "GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_run",
                    "GITHUB_TOKEN":"native", "FACTORY_GITHUB_TOKEN":"crossrepo",
                    **variation,
                }, clear=True):
                    with self.assertRaises(PermissionError):
                        _read_b4_immutable_compare_from_broker(
                            COMPARE,
                            transport=lambda *_: self.fail("network called"))

    def test_broker_denials_and_malformed_response_fail_closed(self):
        with patch.dict("os.environ", {
            "GITHUB_ACTIONS":"true", "GITHUB_EVENT_NAME":"workflow_run",
            "SUPABASE_URL":BROKER, "SUPABASE_SECRET_KEY":OIDC,
        }, clear=True):
            for status in (401, 403, 404):
                with self.subTest(status=status):
                    with self.assertRaises(PermissionError):
                        _read_b4_immutable_compare_from_broker(
                            COMPARE,transport=lambda *_: (status,{"error":"secret"}))
            for status in (409, 502, 503):
                with self.subTest(status=status):
                    with self.assertRaises(RuntimeError):
                        _read_b4_immutable_compare_from_broker(
                            COMPARE,transport=lambda *_: (status,{"error":"secret"}))
            for result in ({}, [], {"status":"ahead","behind_by":2,"files":[]},
                           {"status":"ahead","behind_by":0,"files":"not-a-list"}):
                with self.subTest(result=result):
                    with self.assertRaises(RuntimeError):
                        _read_b4_immutable_compare_from_broker(
                            COMPARE,transport=lambda *_: (200,result))

    def test_non_certifier_uses_existing_supported_resolver(self):
        with patch.dict("os.environ", {
            "GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch",
        }, clear=True):
            with patch("ai_product_factory.cross_repo_b4_read.resolve_github_token",
                       return_value="verified-github-app-token") as original:
                self.assertEqual(resolve_b4_cross_repo_token(STUDIO),
                                 "verified-github-app-token")
                original.assert_called_once_with(STUDIO)

    def test_denies_non_compare_and_current_factory_without_network(self):
        calls=[]
        with patch.dict("os.environ", {}, clear=True):
            get=cross_repo_b4_reader(
                factory_repository=FACTORY,
                github_read=lambda *_: self.fail("network called"),
                token_resolver=lambda target: calls.append(target) or "unused")
            for path in (
                "/repos/" + FACTORY + "/compare/" + A + "..." + B,
                "/repos/" + STUDIO + "/pulls/2",
                "/repos/" + STUDIO + "/compare/main...main",
                COMPARE + "?unsafe=1", COMPARE + "/files",
                "/repos/" + STUDIO + "/issues/1/comments",
                "/repos/" + STUDIO + "/git/trees/" + A,
                COMPARE + "\nAuthorization: evil", "", None,
            ):
                with self.subTest(path=repr(path)):
                    with self.assertRaises((PermissionError, GitHubEvidenceTransportBlocked)):
                        get(path)
        self.assertEqual(calls, [])

    def test_empty_explicit_token_denied_for_non_certifier(self):
        with patch.dict("os.environ", {}, clear=True):
            for bad in ("", " ", None):
                get=cross_repo_b4_reader(
                    factory_repository=FACTORY,
                    github_read=lambda *_: self.fail("network called"),
                    token_resolver=lambda _repo, value=bad:value)
                with self.assertRaises(PermissionError):
                    get(COMPARE)
        with self.assertRaises(ValueError):
            cross_repo_b4_reader(factory_repository="invalid",
                                 github_read=lambda *_: {})
if __name__ == "__main__":
    unittest.main()
