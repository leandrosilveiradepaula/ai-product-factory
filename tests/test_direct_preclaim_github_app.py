"""Direct route must authenticate the GitHub App before burning a run attempt."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

from ai_product_factory.runtime_auth import AuthKind
from ai_product_factory.runtime_cli import run_direct_once
from ai_product_factory.direct_run_queue import SupabaseDirectRunQueue


class Response:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.data).encode()


class DirectPreclaimTests(unittest.TestCase):
    def test_control_plane_preflight_uses_exact_run_task_and_project(self):
        seen = []

        def request(req, **_):
            path = urlsplit(req.full_url).path
            seen.append(path)
            if path.endswith("/factory_runs"):
                return Response([{"id": "run", "task_id": "task", "status": "queued", "execution_route": "direct"}])
            if path.endswith("/factory_tasks"):
                return Response([{"id": "task", "project_id": "project", "status": "queued_execution"}])
            if path.endswith("/factory_projects"):
                return Response([{"id": "project", "project_key": "crm", "repository": "owner/target", "is_active": True}])
            raise AssertionError(path)

        with patch("urllib.request.urlopen", side_effect=request):
            result = SupabaseDirectRunQueue(url="https://example.supabase.co", service_role_key="secret").preflight_target("run")
        self.assertEqual(result, ("owner/target", "crm"))
        self.assertEqual(len(seen), 3)
        self.assertTrue(seen[0].endswith("/factory_runs"))
        self.assertTrue(seen[1].endswith("/factory_tasks"))
        self.assertTrue(seen[2].endswith("/factory_projects"))

    def test_denied_github_app_is_before_claim_and_no_paid_model(self):
        queue = MagicMock()
        queue.preflight_target.return_value = ("owner/target", "crm")
        scheduler = MagicMock()
        auth = MagicMock()
        auth.resolve_primary_api.return_value = SimpleNamespace(kind=AuthKind.OPENAI_API_KEY)
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "factory/main"}, clear=False), \\
             patch("ai_product_factory.runtime_cli.require_primary_runtime_enabled"), \\
             patch("ai_product_factory.runtime_cli.require_paid_runtime_budget"), \\
             patch("ai_product_factory.runtime_cli.RuntimeAuthResolver", return_value=auth), \\
             patch("ai_product_factory.runtime_cli.SupabaseAgentScheduler", return_value=scheduler), \\
             patch("ai_product_factory.runtime_cli.SupabaseDirectRunQueue", return_value=queue), \\
             patch("ai_product_factory.runtime_cli.SupabaseProjectGitHubAccessStore") as access, \\
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter", side_effect=PermissionError("broker 403")) as github, \\
             patch("ai_product_factory.runtime_cli.ModelImplementationProducer") as producer, \\
             patch("ai_product_factory.runtime_cli.OpenAIResponsesProvider") as model:
            with self.assertRaisesRegex(PermissionError, "broker 403"):
                run_direct_once("w", "development", "run")
        queue.claim_next.assert_not_called()
        producer.assert_not_called()
        model.assert_not_called()
        scheduler.release.assert_not_called()
        access.return_value.require_capabilities.assert_called_once_with(
            "crm", ("contents_write", "issues_write", "pull_requests_write")
        )
        github.assert_called_once_with(repository="owner/target")

    def test_valid_ephemeral_token_is_reused_and_no_work_is_claimed_if_empty(self):
        queue = MagicMock()
        queue.preflight_target.return_value = ("owner/target", "crm")
        queue.claim_next.return_value = None
        scheduler = MagicMock()
        auth = MagicMock()
        auth.resolve_primary_api.return_value = SimpleNamespace(kind=AuthKind.OPENAI_API_KEY)
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "factory/main"}, clear=False), \\
             patch("ai_product_factory.runtime_cli.require_primary_runtime_enabled"), \\
             patch("ai_product_factory.runtime_cli.require_paid_runtime_budget"), \\
             patch("ai_product_factory.runtime_cli.RuntimeAuthResolver", return_value=auth), \\
             patch("ai_product_factory.runtime_cli.SupabaseAgentScheduler", return_value=scheduler), \\
             patch("ai_product_factory.runtime_cli.SupabaseDirectRunQueue", return_value=queue), \\
             patch("ai_product_factory.runtime_cli.SupabaseProjectGitHubAccessStore"), \\
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github, \\
             patch("ai_product_factory.runtime_cli.OpenAIResponsesProvider") as model:
            result = run_direct_once("w", "development", "run")
        self.assertEqual(result, {"claimed": False, "status": "empty"})
        queue.claim_next.assert_called_once_with("w", "development", "run")
        model.assert_not_called()
        scheduler.release.assert_not_called()
        github.assert_called_once_with(repository="owner/target")

    def test_preflight_without_eligible_task_does_not_create_lease(self):
        queue = MagicMock()
        queue.preflight_target.return_value = None
        auth = MagicMock()
        auth.resolve_primary_api.return_value = SimpleNamespace(kind=AuthKind.OPENAI_API_KEY)
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}, clear=False), \\
             patch("ai_product_factory.runtime_cli.require_primary_runtime_enabled"), \\
             patch("ai_product_factory.runtime_cli.require_paid_runtime_budget"), \\
             patch("ai_product_factory.runtime_cli.RuntimeAuthResolver", return_value=auth), \\
             patch("ai_product_factory.runtime_cli.SupabaseAgentScheduler"), \\
             patch("ai_product_factory.runtime_cli.SupabaseDirectRunQueue", return_value=queue), \\
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github:
            result = run_direct_once("w", "development", "run")
        self.assertEqual(result["status"], "empty")
        queue.claim_next.assert_not_called()
        github.assert_not_called()


if __name__ == "__main__":
    unittest.main()
