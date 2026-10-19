"""Regression for the CRM Direct Work Unit that committed code but failed in cleanup.

These tests never contact GitHub, Supabase, the model provider, or Codex.
"""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ai_product_factory.change_set_worker import ChangeSetWorkResult
from ai_product_factory.runtime_auth import AuthKind
from ai_product_factory.runtime_cli import (
    _release_completed_change_set,
    _release_routed_run,
    run_direct_once,
    run_codex_once,
)


class TerminalChangeSetReleaseTests(unittest.TestCase):
    @staticmethod
    def item():
        return SimpleNamespace(
            run_id="run-1", task_id="task-1", project_id="project-1",
            project_key="crm-infodive", repository="owner/repo",
            execution_generation=4, branch="factory/cs-example/conditions",
            change_set_id="change-set-1", work_unit_id="work-unit-1",
            issue_number=None, title="Condition editor", description="",
            human_gate_required=False,
        )

    @staticmethod
    def receipt():
        return ChangeSetWorkResult(
            run_id="run-1", change_set_id="change-set-1",
            work_unit_id="work-unit-1", output_commit="a" * 40,
            changed_files=("src/components/automations/NewAutomationModal.tsx",),
            base_commit="b" * 40,
            branch="factory/cs-example/conditions",
        )

    def test_terminal_release_does_not_recheck_revoked_implementing_lease(self):
        scheduler = MagicMock()
        item = self.item()
        receipt = self.receipt()
        with patch(
            "ai_product_factory.runtime_cli._routed_checkpoint",
            side_effect=PermissionError("already completed: 409"),
        ) as checkpoint:
            _release_completed_change_set(scheduler, item, receipt)
        checkpoint.assert_not_called()
        scheduler.release.assert_called_once_with(item.run_id, "completed")

    def test_terminal_release_rejects_wrong_work_unit_branch_or_commit(self):
        scheduler = MagicMock()
        item = self.item()
        receipt = self.receipt()
        altered = (
            ("work_unit_id", "another-work-unit"),
            ("change_set_id", "another-change-set"),
            ("run_id", "another-run"),
            ("branch", "another-branch"),
            ("output_commit", "not-a-git-sha"),
        )
        for key, value in altered:
            with self.subTest(key=key):
                data = dict(vars(receipt))
                data[key] = value
                with self.assertRaises(PermissionError):
                    _release_completed_change_set(scheduler, item, SimpleNamespace(**data))
        scheduler.release.assert_not_called()

    def test_incomplete_or_unbound_receipt_cannot_release_completed(self):
        scheduler = MagicMock()
        item = self.item()
        for bad in (None, SimpleNamespace(), {"status": "completed"}):
            with self.subTest(receipt=type(bad).__name__):
                with self.assertRaises(PermissionError):
                    _release_completed_change_set(scheduler, item, bad)
        item.change_set_id = None
        with self.assertRaises(PermissionError):
            _release_completed_change_set(scheduler, item, self.receipt())
        scheduler.release.assert_not_called()

    def test_regular_completed_run_still_requires_live_epoch(self):
        scheduler = MagicMock()
        with patch(
            "ai_product_factory.runtime_cli._routed_checkpoint",
            side_effect=PermissionError("revoked"),
        ):
            with self.assertRaises(PermissionError):
                _release_routed_run(scheduler, self.item(), "worker-1", "completed")
        scheduler.release.assert_not_called()

    def test_direct_and_codex_success_skip_only_post_completion_checkpoint(self):
        for route in ("direct", "codex"):
            with self.subTest(route=route):
                item = self.item()
                receipt = self.receipt()
                scheduler = MagicMock()
                queue = MagicMock()
                queue.claim_next.return_value = item
                builder = MagicMock()
                builder.execute.return_value = receipt
                resolver = MagicMock()
                resolver.resolve_primary_api.return_value = SimpleNamespace(
                    kind=AuthKind.OPENAI_API_KEY,
                )
                with ExitStack() as stack:
                    stack.enter_context(patch.dict(
                        "os.environ",
                        {"GITHUB_REPOSITORY": "owner/repo",
                         "FACTORY_PRIMARY_MODEL_ENABLED": "true"},
                        clear=True,
                    ))
                    stack.enter_context(patch(
                        "ai_product_factory.runtime_cli.SupabaseAgentScheduler",
                        return_value=scheduler,
                    ))
                    stack.enter_context(patch(
                        "ai_product_factory.runtime_cli.GitHubRestAdapter",
                    ))
                    stack.enter_context(patch(
                        "ai_product_factory.runtime_cli.ChangeSetBuilderWorker",
                        return_value=builder,
                    ))
                    stack.enter_context(patch(
                        "ai_product_factory.runtime_cli.SupabaseChangeSetStore",
                    ))
                    checkpoint = stack.enter_context(patch(
                        "ai_product_factory.runtime_cli._routed_checkpoint",
                    ))
                    if route == "direct":
                        stack.enter_context(patch(
                            "ai_product_factory.runtime_cli.require_primary_runtime_enabled",
                        ))
                        stack.enter_context(patch(
                            "ai_product_factory.runtime_cli.require_paid_runtime_budget",
                        ))
                        stack.enter_context(patch(
                            "ai_product_factory.runtime_cli.RuntimeAuthResolver",
                            return_value=resolver,
                        ))
                        stack.enter_context(patch(
                            "ai_product_factory.runtime_cli.SupabaseDirectRunQueue",
                            return_value=queue,
                        ))
                        stack.enter_context(patch(
                            "ai_product_factory.runtime_cli.ModelImplementationProducer",
                        ))
                        stack.enter_context(patch(
                            "ai_product_factory.runtime_cli.OpenAIResponsesProvider",
                        ))
                        result = run_direct_once("worker-1", "ui", item.run_id)
                    else:
                        stack.enter_context(patch(
                            "ai_product_factory.runtime_cli.require_codex_runtime_enabled",
                        ))
                        stack.enter_context(patch(
                            "ai_product_factory.runtime_cli.SupabaseCodexRunQueue",
                            return_value=queue,
                        ))
                        stack.enter_context(patch(
                            "ai_product_factory.runtime_cli.CodexCLIProducer",
                        ))
                        stack.enter_context(patch(
                            "ai_product_factory.runtime_cli.SupabaseCodexUsageRecorder",
                        ))
                        result = run_codex_once("worker-1", "ui", item.run_id)
                self.assertEqual(result["status"], "work_unit_completed")
                self.assertEqual(result["output_commit"], "a" * 40)
                self.assertEqual(checkpoint.call_count, 1)
                builder.execute.assert_called_once()
                scheduler.release.assert_called_once_with(item.run_id, "completed")


if __name__ == "__main__":
    unittest.main()
