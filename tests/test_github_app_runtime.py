import base64
import json
import unittest
from unittest.mock import patch

from ai_product_factory.github_app_runtime import (
    APP_PERMISSIONS,
    create_app_jwt,
    resolve_github_app_installation_token,
)


def _decode_segment(value):
    value += "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode(value.encode()).decode())


class FakeTransport:
    def __init__(self, *, auth_mode="github_app", status="ready"):
        self.auth_mode = auth_mode
        self.status = status
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
        if url.endswith("/rpc/factory_get_github_app_credentials"):
            return 200, {
                "app_id": 42,
                "app_slug": "factory-app",
                "client_id": "Iv1.fake",
                "status": "registered",
                "private_key": "PRIVATE KEY MATERIAL",
            }
        if url == "https://api.github.com/app/installations/1234/access_tokens":
            self.assert_app_token_request(headers, payload)
            return 201, {
                "token": "ghs_installation_token",
                "expires_at": "2026-10-02T23:00:00Z",
                "permissions": APP_PERMISSIONS,
            }
        raise AssertionError(url)

    @staticmethod
    def assert_app_token_request(headers, payload):
        assert headers["Authorization"].startswith("Bearer ")
        assert payload["repository_ids"] == [5678]
        assert payload["permissions"] == APP_PERMISSIONS


class GitHubAppRuntimeTests(unittest.TestCase):
    def test_create_app_jwt_has_bounded_claims_and_uses_injected_signer(self):
        seen = {}

        def signer(payload, private_key):
            seen["payload"] = payload
            seen["private_key"] = private_key
            return b"signature"

        token = create_app_jwt(42, "PEM", now=1_000, signer=signer)
        header, payload, signature = token.split(".")
        self.assertEqual(_decode_segment(header), {"alg": "RS256", "typ": "JWT"})
        self.assertEqual(_decode_segment(payload), {"iat": 940, "exp": 1540, "iss": "42"})
        self.assertEqual(seen["payload"], f"{header}.{payload}".encode())
        self.assertEqual(seen["private_key"], "PEM")
        self.assertNotIn("PEM", token)
        self.assertTrue(signature)

    def test_ready_github_app_mints_repository_scoped_installation_token(self):
        transport = FakeTransport()
        env = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SECRET_KEY": "sb_secret_test",
        }
        with patch.dict("os.environ", env, clear=True):
            token = resolve_github_app_installation_token(
                "owner/target",
                transport=transport,
                signer=lambda payload, private_key: b"signature",
                now=1_000,
            )
        self.assertEqual(token, "ghs_installation_token")
        urls = [call[1] for call in transport.calls]
        self.assertTrue(any("repository=eq.owner%2Ftarget" in url for url in urls))
        self.assertTrue(any(url.endswith("/rpc/factory_get_github_app_credentials") for url in urls))
        self.assertIn(
            "https://api.github.com/app/installations/1234/access_tokens",
            urls,
        )

    def test_non_app_project_keeps_legacy_fallback_available(self):
        transport = FakeTransport(auth_mode="fine_grained_pat", status="partial")
        env = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SECRET_KEY": "sb_secret_test",
        }
        with patch.dict("os.environ", env, clear=True):
            token = resolve_github_app_installation_token(
                "owner/target",
                transport=transport,
                signer=lambda payload, private_key: b"signature",
            )
        self.assertIsNone(token)
        self.assertFalse(any("/rpc/factory_get_github_app_credentials" in call[1] for call in transport.calls))

    def test_github_app_mode_fails_closed_until_installation_is_ready(self):
        transport = FakeTransport(auth_mode="github_app", status="blocked")
        env = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SECRET_KEY": "sb_secret_test",
        }
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaises(PermissionError):
                resolve_github_app_installation_token(
                    "owner/target",
                    transport=transport,
                    signer=lambda payload, private_key: b"signature",
                )

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
