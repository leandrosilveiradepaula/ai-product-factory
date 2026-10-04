import json
import unittest
from unittest.mock import patch

from ai_product_factory.github_app_runtime import resolve_github_app_installation_token


BROKER_URL = "https://example.supabase.co/functions/v1/factory-runtime-control-plane"
DIRECT_URL = "https://example.supabase.co"


class FakeTransport:
    def __init__(self, *, auth_mode="github_app", status="ready", broker_status=200):
        self.auth_mode = auth_mode
        self.status = status
        self.broker_status = broker_status
        self.calls = []

    def __call__(self, method, url, headers, body):
        payload = json.loads(body.decode()) if body else None
        self.calls.append((method, url, headers, payload))
        if "/factory_projects?" in url:
            return 200, [{"id": "project-1", "repository": "owner/target"}]
        if "/factory_project_github_access?" in url:
            return 200, [{
                "auth_mode": self.auth_mode,
                "status": self.status,
                "installation_id": 1234,
                "repository_id": 5678,
            }]
        if url.endswith("/github-app/token"):
            if self.broker_status == 404:
                return 404, {"error": "project_not_found"}
            if self.broker_status == 409:
                code = "github_app_not_migrated" if self.auth_mode != "github_app" else "github_app_not_ready"
                return 409, {"error": code}
            return 200, {
                "token": "ghs_installation_token",
                "expires_at": "2026-10-02T23:00:00Z",
                "installation_id": 1234,
                "repository_id": 5678,
                "token_persisted": False,
            }
        raise AssertionError(url)


class GitHubAppRuntimeTests(unittest.TestCase):
    def test_oidc_broker_path_calls_only_dedicated_token_endpoint(self):
        transport = FakeTransport()
        env = {"SUPABASE_URL": BROKER_URL, "SUPABASE_SECRET_KEY": "oidc-token"}
        with patch.dict("os.environ", env, clear=True):
            token = resolve_github_app_installation_token("owner/target", transport=transport)
        self.assertEqual(token, "ghs_installation_token")
        self.assertEqual(len(transport.calls), 1)
        method, url, headers, payload = transport.calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/github-app/token"))
        self.assertEqual(payload, {"repository": "owner/target"})
        self.assertNotIn("private_key", json.dumps(payload))
        self.assertIn("Authorization", headers)

    def test_oidc_broker_non_app_project_keeps_legacy_fallback_available(self):
        transport = FakeTransport(auth_mode="fine_grained_pat", status="partial", broker_status=409)
        env = {"SUPABASE_URL": BROKER_URL, "SUPABASE_SECRET_KEY": "oidc-token"}
        with patch.dict("os.environ", env, clear=True):
            token = resolve_github_app_installation_token("owner/target", transport=transport)
        self.assertIsNone(token)
        self.assertEqual(len(transport.calls), 1)

    def test_oidc_broker_missing_project_keeps_legacy_fallback_available(self):
        transport = FakeTransport(broker_status=404)
        env = {"SUPABASE_URL": BROKER_URL, "SUPABASE_SECRET_KEY": "oidc-token"}
        with patch.dict("os.environ", env, clear=True):
            token = resolve_github_app_installation_token("owner/target", transport=transport)
        self.assertIsNone(token)

    def test_oidc_broker_not_ready_fails_closed(self):
        transport = FakeTransport(auth_mode="github_app", status="blocked", broker_status=409)
        env = {"SUPABASE_URL": BROKER_URL, "SUPABASE_SECRET_KEY": "oidc-token"}
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaises(PermissionError):
                resolve_github_app_installation_token("owner/target", transport=transport)

    def test_direct_control_plane_non_app_project_keeps_legacy_fallback_available(self):
        transport = FakeTransport(auth_mode="fine_grained_pat", status="partial")
        env = {"SUPABASE_URL": DIRECT_URL, "SUPABASE_SECRET_KEY": "sb_secret_test"}
        with patch.dict("os.environ", env, clear=True):
            token = resolve_github_app_installation_token("owner/target", transport=transport)
        self.assertIsNone(token)
        self.assertFalse(any(call[1].endswith("/github-app/token") for call in transport.calls))

    def test_direct_control_plane_github_app_mode_fails_closed_until_ready(self):
        transport = FakeTransport(auth_mode="github_app", status="blocked")
        env = {"SUPABASE_URL": DIRECT_URL, "SUPABASE_SECRET_KEY": "sb_secret_test"}
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaises(PermissionError):
                resolve_github_app_installation_token("owner/target", transport=transport)
        self.assertFalse(any(call[1].endswith("/github-app/token") for call in transport.calls))

    def test_broker_refusal_does_not_fall_back_silently(self):
        transport = FakeTransport(broker_status=409)
        env = {"SUPABASE_URL": BROKER_URL, "SUPABASE_SECRET_KEY": "oidc-token"}
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaises(PermissionError):
                resolve_github_app_installation_token("owner/target", transport=transport)

    def test_without_control_plane_credentials_app_resolution_is_inert(self):
        called = False

        def transport(*args):
            nonlocal called
            called = True
            raise AssertionError("transport should not be called")

        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(resolve_github_app_installation_token("owner/target", transport=transport))
        self.assertFalse(called)

    def test_direct_broker_binding_mismatch_is_rejected(self):
        class MismatchTransport(FakeTransport):
            def __call__(self, method, url, headers, body):
                status, payload = super().__call__(method, url, headers, body)
                if url.endswith("/github-app/token") and status == 200:
                    payload = dict(payload)
                    payload["repository_id"] = 9999
                return status, payload

        env = {"SUPABASE_URL": DIRECT_URL, "SUPABASE_SECRET_KEY": "sb_secret_test"}
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaises(PermissionError):
                resolve_github_app_installation_token("owner/target", transport=MismatchTransport())

    def test_broker_requires_positive_binding_ids(self):
        class IncompleteTransport(FakeTransport):
            def __call__(self, method, url, headers, body):
                status, payload = super().__call__(method, url, headers, body)
                if url.endswith("/github-app/token") and status == 200:
                    payload = dict(payload)
                    payload["repository_id"] = 0
                return status, payload

        env = {"SUPABASE_URL": BROKER_URL, "SUPABASE_SECRET_KEY": "oidc-token"}
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaises(PermissionError):
                resolve_github_app_installation_token("owner/target", transport=IncompleteTransport())

    def test_broker_must_prove_token_is_not_persisted(self):
        class PersistenceTransport(FakeTransport):
            def __call__(self, method, url, headers, body):
                status, payload = super().__call__(method, url, headers, body)
                if url.endswith("/github-app/token") and status == 200:
                    payload = dict(payload)
                    payload["token_persisted"] = True
                return status, payload

        env = {"SUPABASE_URL": BROKER_URL, "SUPABASE_SECRET_KEY": "oidc-token"}
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaises(PermissionError):
                resolve_github_app_installation_token("owner/target", transport=PersistenceTransport())


if __name__ == "__main__":
    unittest.main()
