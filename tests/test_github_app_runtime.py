import json
import unittest
from unittest.mock import patch

from ai_product_factory.github_app_runtime import resolve_github_app_installation_token


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
            if self.broker_status == 409:
                return 409, {"error": "github_app_not_ready"}
            return 200, {
                "token": "ghs_installation_token",
                "expires_at": "2026-10-02T23:00:00Z",
                "installation_id": 1234,
                "repository_id": 5678,
                "token_persisted": False,
            }
        raise AssertionError(url)


class GitHubAppRuntimeTests(unittest.TestCase):
    def test_ready_github_app_uses_control_plane_token_broker(self):
        transport = FakeTransport()
        env = {
            "SUPABASE_URL": "https://example.supabase.co/functions/v1/factory-runtime-control-plane",
            "SUPABASE_SECRET_KEY": "oidc-token",
        }
        with patch.dict("os.environ", env, clear=True):
            token = resolve_github_app_installation_token("owner/target", transport=transport)
        self.assertEqual(token, "ghs_installation_token")
        broker_calls = [call for call in transport.calls if call[1].endswith("/github-app/token")]
        self.assertEqual(len(broker_calls), 1)
        method, _, headers, payload = broker_calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(payload, {"repository": "owner/target"})
        self.assertNotIn("private_key", json.dumps(payload))
        self.assertIn("Authorization", headers)

    def test_non_app_project_keeps_legacy_fallback_available(self):
        transport = FakeTransport(auth_mode="fine_grained_pat", status="partial")
        env = {
            "SUPABASE_URL": "https://example.supabase.co/functions/v1/factory-runtime-control-plane",
            "SUPABASE_SECRET_KEY": "oidc-token",
        }
        with patch.dict("os.environ", env, clear=True):
            token = resolve_github_app_installation_token("owner/target", transport=transport)
        self.assertIsNone(token)
        self.assertFalse(any(call[1].endswith("/github-app/token") for call in transport.calls))

    def test_github_app_mode_fails_closed_until_installation_is_ready(self):
        transport = FakeTransport(auth_mode="github_app", status="blocked")
        env = {
            "SUPABASE_URL": "https://example.supabase.co/functions/v1/factory-runtime-control-plane",
            "SUPABASE_SECRET_KEY": "oidc-token",
        }
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaises(PermissionError):
                resolve_github_app_installation_token("owner/target", transport=transport)
        self.assertFalse(any(call[1].endswith("/github-app/token") for call in transport.calls))

    def test_broker_refusal_does_not_fall_back_silently(self):
        transport = FakeTransport(broker_status=409)
        env = {
            "SUPABASE_URL": "https://example.supabase.co/functions/v1/factory-runtime-control-plane",
            "SUPABASE_SECRET_KEY": "oidc-token",
        }
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


if __name__ == "__main__":
    unittest.main()
