"""Native IBM VPS Direct must validate GitHub before lease or paid model."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ai_product_factory.runtime_cli import run_direct_once
from ai_product_factory.github_rest import GitHubRestAdapter
from ai_product_factory.project_github_access import SupabaseProjectGitHubAccessStore

ENV = {
    "FACTORY_PRIMARY_MODEL_PROVIDER": "infodive_ibm_cloud",
    "FACTORY_INFODIVE_VPS_WORKER_ENABLED": "true",
    "GITHUB_ACTIONS": "false",
    "GITHUB_REPOSITORY": "owner/factory",
}


class NativeVpsDirectClaimTests(unittest.TestCase):
    def setup_mocks(self, stack, *, token=None):
        env = {**ENV}
        if token is not None:
            env["FACTORY_GITHUB_TOKEN"] = token
        stack.enter_context(patch.dict(os.environ, env, clear=True))
        stack.enter_context(patch("ai_product_factory.runtime_cli.require_primary_runtime_enabled"))
        stack.enter_context(patch("ai_product_factory.runtime_cli.require_primary_provider_ready"))
        stack.enter_context(patch("ai_product_factory.runtime_cli.require_paid_runtime_budget"))
        scheduler = stack.enter_context(patch("ai_product_factory.runtime_cli.SupabaseAgentScheduler"))
        scheduler.return_value.require_route_tools.return_value = SimpleNamespace(
            model_policy={"provider": "infodive_ibm_cloud", "enabled": True},
        )
        queue = stack.enter_context(patch("ai_product_factory.runtime_cli.SupabaseDirectRunQueue"))
        queue.return_value.preflight_target.return_value = ("owner/crm", "crm-infodive")
        access = stack.enter_context(patch("ai_product_factory.runtime_cli.SupabaseProjectGitHubAccessStore"))
        github = stack.enter_context(patch("ai_product_factory.runtime_cli.GitHubRestAdapter"))
        producer = stack.enter_context(patch("ai_product_factory.runtime_cli.ModelImplementationProducer"))
        return scheduler, queue, access, github, producer

    def test_missing_vps_token_blocks_without_claim_or_model(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            scheduler, queue, access, github, producer = self.setup_mocks(stack)
            outcome = run_direct_once("worker", "development", "run-1")
            self.assertEqual(outcome["status"], "blocked_github_credential")
            self.assertFalse(outcome["claimed"])
            self.assertEqual(outcome["reason_code"], "native_ibm_direct_requires_factory_github_token")
            queue.return_value.claim_next.assert_not_called()
            access.assert_not_called()
            github.assert_not_called()
            producer.assert_not_called()
            scheduler.return_value.release.assert_not_called()

    def test_with_token_preflight_verified_before_claim_and_no_model_if_empty(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            scheduler, queue, access, github, producer = self.setup_mocks(stack, token="dummy-factory-token")
            queue.return_value.claim_next.return_value = None
            outcome = run_direct_once("worker", "development", "run-1")
            self.assertEqual(outcome, {"claimed": False, "status": "empty"})
            access.return_value.require_capabilities.assert_called_once_with(
                "crm-infodive", ("contents_write", "issues_write", "pull_requests_write")
            )
            github.assert_called_once_with(repository="owner/crm")
            github.return_value.assert_repository_identity.assert_called_once_with()
            queue.return_value.claim_next.assert_called_once_with("worker", "development", "run-1")
            producer.assert_not_called()

    def test_wrong_github_identity_fails_before_claim(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            scheduler, queue, access, github, producer = self.setup_mocks(stack, token="dummy")
            github.return_value.assert_repository_identity.side_effect = PermissionError("identity")
            with self.assertRaisesRegex(PermissionError, "identity"):
                run_direct_once("worker", "development", "run-1")
            queue.return_value.claim_next.assert_not_called()
            producer.assert_not_called()
            scheduler.return_value.release.assert_not_called()

    def test_unready_github_project_fails_before_claim(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            scheduler, queue, access, github, producer = self.setup_mocks(stack, token="dummy")
            access.return_value.require_capabilities.side_effect = PermissionError("not ready")
            with self.assertRaisesRegex(PermissionError, "not ready"):
                run_direct_once("worker", "development", "run-1")
            github.assert_not_called()
            queue.return_value.claim_next.assert_not_called()
            producer.assert_not_called()

    def test_queued_project_missing_causes_safe_idle(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            scheduler, queue, access, github, producer = self.setup_mocks(stack)
            queue.return_value.preflight_target.return_value = None
            self.assertEqual(
                run_direct_once("worker", "development", "run-1"),
                {"claimed": False, "status": "empty"},
            )
            access.assert_not_called()
            github.assert_not_called()
            queue.return_value.claim_next.assert_not_called()

    def test_repository_identity_matches_exact_namespace_and_id(self):
        expected = {"full_name": "Owner/CRM", "id": 123, "permissions": {"push": True}}
        calls = []
        def request(method, url, headers, body):
            calls.append((method, url, headers))
            return 200, expected
        github = GitHubRestAdapter(repository="owner/crm", token="test-not-real", transport=request)
        self.assertEqual(github.assert_repository_identity(), 123)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][1].endswith("/repos/owner/crm"))
        self.assertEqual(calls[0][2]["Authorization"], "Bearer test-not-real")

    def test_invalid_or_readonly_github_identity_rejected(self):
        for payload in (
            {"full_name": "owner/another", "id": 7},
            {"full_name": "owner/crm", "id": False},
            {"full_name": "owner/crm"},
            {"full_name": "owner/crm", "id": 8, "permissions": {"push": False}},
            [],
        ):
            with self.subTest(payload=payload):
                gh = GitHubRestAdapter(
                    repository="owner/crm", token="test-not-real",
                    transport=lambda *a: (200, payload),
                )
                with self.assertRaises(PermissionError):
                    gh.assert_repository_identity()

    def test_stale_control_plane_capabilities_never_authorize_direct(self):
        store = SupabaseProjectGitHubAccessStore(
            url="https://example.supabase.co", secret_key="sb_secret_fake",
        )
        project = [{"id": "project", "repository": "owner/crm"}]
        stale = [{"status": "stale", "observed_capabilities": {
            "contents_write": "verified", "issues_write": "verified",
            "pull_requests_write": "verified",
        }}]
        with patch.object(store, "_get", side_effect=[project, stale]):
            with self.assertRaisesRegex(PermissionError, "not currently ready"):
                store.require_capabilities(
                    "crm-infodive", ("contents_write", "issues_write", "pull_requests_write"),
                )


if __name__ == "__main__":
    unittest.main()
