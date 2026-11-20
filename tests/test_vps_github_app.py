"""Offline privileged native IBM GitHub App token exchange; zero real writes."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from ai_product_factory.vps_github_app import (
    VpsGitHubAppUnavailable, issue_for_repository,
    mint_vps_github_app_token,
)

SHA = "a" * 40
REPO = "leandrosilveiradepaula/crm-infodive"
PROJECT = "crm-infodive"
ID = "19f0f200-3777-46c6-969a-acf0d3426ff1"
ENV = {
    "SUPABASE_URL": "https://fjplmxfcshhbmzgvyqlm.supabase.co",
    "SUPABASE_SECRET_KEY": "sb_secret_offline_test",
    "FACTORY_PRIMARY_MODEL_PROVIDER": "infodive_ibm_cloud",
    "FACTORY_PRIMARY_MODEL_ENABLED": "true",
    "FACTORY_INFODIVE_VPS_WORKER_ENABLED": "true",
    "FACTORY_SQL_INFODIVE_PRIVATE_ROUTE_ATTESTED": "true",
    "FACTORY_SQL_INFODIVE_WORKER_SHA": SHA,
    "GITHUB_ACTIONS": "false",
}
ACCESS = {
    "auth_mode": "github_app", "status": "ready",
    "installation_id": 1234, "repository_id": 4321,
    "observed_capabilities": {
        "contents_write": "verified", "issues_write": "verified",
        "pull_requests_write": "verified",
    },
}
PERMISSIONS = {
    "contents": "write", "issues": "write", "pull_requests": "write",
    "actions": "read", "checks": "read", "statuses": "read",
}


class FakeAPI:
    def __init__(self):
        self.access = dict(ACCESS)
        self.created_token = {
            "token": "ghs_offline_testing_only_1234567890",
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(minutes=57)
            ).isoformat(),
            "permissions": dict(PERMISSIONS),
            "repositories": [{"id": 4321, "full_name": REPO}],
        }
        self.listing = {
            "total_count": 1,
            "repositories": [{"id": 4321, "full_name": REPO}],
        }
        self.repository = {
            "id": 4321, "full_name": REPO,
            "permissions": {"push": False},
        }
        self.project = {
            "id": ID, "repository": REPO, "project_key": PROJECT,
        }
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers))
        if "factory_projects?" in url:
            return 200, [self.project]
        if "factory_project_github_access?" in url:
            return 200, [self.access]
        if url.endswith("rpc/factory_get_github_app_credentials"):
            return 200, {"app_id": 123, "private_key": "FAKE_PEM"}
        if url.endswith("/access_tokens"):
            self.body = json.loads(body.decode("utf-8"))
            return 201, self.created_token
        if url.endswith("/installation/repositories"):
            return 200, self.listing
        if url.endswith("/repos/" + REPO):
            return 200, self.repository
        raise AssertionError("unexpected network target")


def get(api, env=None, checkout=lambda: SHA):
    return issue_for_repository(
        REPO, PROJECT, env=ENV if env is None else env,
        transport=api, signer=lambda appid, pem: "offline.fake.jwt",
        checkout=checkout,
    )


class TokenExchangeTests(unittest.TestCase):
    def test_valid_scope_verified_even_if_repo_push_field_false(self):
        api = FakeAPI()
        token = get(api)
        self.assertEqual(token, api.created_token["token"])
        self.assertEqual(api.body["repositories"], ["crm-infodive"])
        self.assertEqual(api.body["permissions"], PERMISSIONS)
        self.assertEqual(len(api.calls), 6)
        self.assertEqual(api.calls[0][0], "GET")
        self.assertEqual(api.calls[3][0], "POST")
        self.assertEqual(api.calls[4][1], "https://api.github.com/installation/repositories")
        self.assertNotIn("FAKE_PEM", repr(api.calls))

    def test_rejects_cross_project_repository_before_network(self):
        api = FakeAPI()
        with self.assertRaises(VpsGitHubAppUnavailable):
            issue_for_repository(
                "owner/wrong", PROJECT, env=ENV, transport=api,
                checkout=lambda: SHA,
            )
        # Lookup is read-only and must reject mismatch before fetching
        # private key, signing, minting or calling GitHub.
        self.assertEqual(len(api.calls), 1)

    def test_sha_mismatch_blocks_even_before_control_plane(self):
        api = FakeAPI()
        with self.assertRaises(VpsGitHubAppUnavailable):
            get(api, checkout=lambda: "b" * 40)
        self.assertFalse(api.calls)

    def test_missing_privileged_key_blocks_without_network(self):
        api = FakeAPI()
        with self.assertRaises(VpsGitHubAppUnavailable):
            get(api, env={**ENV, "SUPABASE_SECRET_KEY": ""})
        self.assertFalse(api.calls)

    def test_actions_cannot_use_vps_privileged_key_path(self):
        api = FakeAPI()
        with self.assertRaises(VpsGitHubAppUnavailable):
            get(api, env={**ENV, "GITHUB_ACTIONS": "true"})
        self.assertFalse(api.calls)

    def test_project_access_stale_refuses_before_private_key(self):
        api = FakeAPI()
        api.access["status"] = "stale"
        with self.assertRaises(VpsGitHubAppUnavailable):
            get(api)
        self.assertEqual(len(api.calls), 2)

    def test_missing_write_permission_refuses_before_private_key(self):
        api = FakeAPI()
        api.access["observed_capabilities"]["issues_write"] = "unverified"
        with self.assertRaises(VpsGitHubAppUnavailable):
            get(api)
        self.assertEqual(len(api.calls), 2)

    def test_issued_readonly_permissions_block_before_github_get(self):
        api = FakeAPI()
        api.created_token["permissions"]["contents"] = "read"
        with self.assertRaises(VpsGitHubAppUnavailable):
            get(api)
        self.assertEqual(len(api.calls), 4)

    def test_different_repo_access_scope_blocks(self):
        api = FakeAPI()
        api.listing["repositories"][0]["id"] = 9999
        with self.assertRaises(VpsGitHubAppUnavailable):
            get(api)

    def test_expired_token_blocks(self):
        api = FakeAPI()
        api.created_token["expires_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=90)
        ).isoformat()
        with self.assertRaises(VpsGitHubAppUnavailable):
            get(api)

    def test_malformed_source_url_blocks(self):
        api = FakeAPI()
        with self.assertRaises(VpsGitHubAppUnavailable):
            get(api, env={**ENV, "SUPABASE_URL": "http://127.0.0.1"})
        self.assertFalse(api.calls)

    def test_pipe_exchange_never_uses_stdout_or_env_token(self):
        from ai_product_factory import vps_github_app
        # A mocked process provides only an anonymous pipe, not real creds.
        with patch.dict(os.environ, ENV, clear=True), \
             patch.object(vps_github_app.subprocess, "Popen") as process, \
             patch.object(vps_github_app.os, "read", return_value=b"ghs_offline_testing_only_1234567890"):
            process.return_value.wait.return_value = 0
            process.return_value.poll.return_value = 0
            token = mint_vps_github_app_token(REPO, PROJECT)
            self.assertEqual(token, "ghs_offline_testing_only_1234567890")
            args,kwargs = process.call_args
            self.assertEqual(kwargs["stdout"], vps_github_app.subprocess.DEVNULL)
            self.assertEqual(kwargs["stderr"], vps_github_app.subprocess.DEVNULL)
            self.assertTrue(kwargs["pass_fds"])
            self.assertNotIn("FACTORY_SQL_INFODIVE_API_KEY", kwargs["env"])
            self.assertNotIn("FACTORY_GITHUB_TOKEN", kwargs["env"])
            self.assertEqual(args[0][-4:], ["--repository", REPO, "--project-key", PROJECT])


if __name__ == "__main__":
    unittest.main()
