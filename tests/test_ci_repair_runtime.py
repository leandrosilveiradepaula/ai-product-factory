import unittest
from unittest.mock import MagicMock, patch

from ai_product_factory.ci_followup_queue import CIFollowupItem
from ai_product_factory.github_loop import CIState, GitHubLoopAction
from ai_product_factory.github_rest import GitHubCheckFailure
from ai_product_factory.runtime_cli import run_ci_once


SHA = "a" * 40
PROJECT_ID = "123e4567-e89b-42d3-a456-426614174000"
CHANGE_SET_ID = "123e4567-e89b-42d3-a456-426614174001"


class CIRepairRuntimeTests(unittest.TestCase):
    def item(self):
        return CIFollowupItem(
            run_id="123e4567-e89b-42d3-a456-426614174002",
            project_key="factory", repository="owner/repo", issue_number=7,
            branch="factory/change-set-a", pr_number=9, candidate_commit=SHA,
            human_gate_required=False, change_set_id=CHANGE_SET_ID,
            project_id=PROJECT_ID, execution_generation=4,
            require_execution_generation=True,
        )

    def _failure_loop(self):
        loop = MagicMock()
        loop.evaluate.return_value = MagicMock(
            action=GitHubLoopAction.RETURN_TO_IMPLEMENTATION,
            ci_state=CIState.FAILURE,
        )
        return loop

    def _github(self, failure):
        github = MagicMock()
        github.get_pull_request.return_value = MagicMock(head_sha=SHA, merged=False)
        github.get_issue.return_value = MagicMock(number=7)
        github.get_failed_checks.return_value = (failure,)
        return github

    def test_code_failure_becomes_exact_durable_repair_request(self):
        followups = MagicMock(); followups.next_pending.return_value = self.item()
        repairs = MagicMock(); repairs.enqueue_failure.return_value = {
            "status": "repair_pending", "repair_request_id": "repair-1", "attempt": 1,
        }
        failure = GitHubCheckFailure("pytest", "failure", summary="1 failed", failure_class="code")
        with patch("ai_product_factory.runtime_cli.SupabaseCIFollowupQueue", return_value=followups), \
             patch("ai_product_factory.runtime_cli.SupabaseCIRepairQueue", return_value=repairs), \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter", return_value=self._github(failure)), \
             patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore"), \
             patch("ai_product_factory.runtime_cli.AutonomousGitHubLoop", return_value=self._failure_loop()), \
             patch("ai_product_factory.runtime_cli._assert_project_followup", return_value=4):
            result = run_ci_once()
        self.assertEqual(result["status"], "repair_pending")
        self.assertEqual(result["failure_classes"], ["code"])
        repairs.enqueue_failure.assert_called_once()
        kwargs = repairs.enqueue_failure.call_args.kwargs
        self.assertEqual(kwargs["item"].candidate_commit, SHA)
        self.assertEqual(kwargs["failures"][0].failure_class, "code")
        self.assertEqual(kwargs["max_attempts"], 2)

    def test_infrastructure_failure_is_persisted_without_patch_execution(self):
        followups = MagicMock(); followups.next_pending.return_value = self.item()
        repairs = MagicMock(); repairs.enqueue_failure.return_value = {"status": "blocked", "reason": "non_code_ci_failure"}
        failure = GitHubCheckFailure("runner unavailable", "failure", summary="runner unavailable", failure_class="runner")
        github = self._github(failure)
        with patch("ai_product_factory.runtime_cli.SupabaseCIFollowupQueue", return_value=followups), \
             patch("ai_product_factory.runtime_cli.SupabaseCIRepairQueue", return_value=repairs), \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter", return_value=github), \
             patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore"), \
             patch("ai_product_factory.runtime_cli.AutonomousGitHubLoop", return_value=self._failure_loop()), \
             patch("ai_product_factory.runtime_cli._assert_project_followup", return_value=4), \
             patch("ai_product_factory.runtime_cli.ChangeSetBuilderWorker") as worker:
            result = run_ci_once()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["failure_classes"], ["runner"])
        worker.assert_not_called()

    def test_diverged_sha_rejects_evidence_and_never_enqueues_repair(self):
        followups = MagicMock(); followups.next_pending.return_value = self.item()
        repairs = MagicMock()
        github = self._github(GitHubCheckFailure("pytest", "failure", failure_class="code"))
        github.get_failed_checks.side_effect = RuntimeError("CI failure evidence PR head diverged from candidate SHA")
        store = MagicMock()
        with patch("ai_product_factory.runtime_cli.SupabaseCIFollowupQueue", return_value=followups), \
             patch("ai_product_factory.runtime_cli.SupabaseCIRepairQueue", return_value=repairs), \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter", return_value=github), \
             patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore", return_value=store), \
             patch("ai_product_factory.runtime_cli.AutonomousGitHubLoop", return_value=self._failure_loop()), \
             patch("ai_product_factory.runtime_cli._assert_project_followup", return_value=4):
            result = run_ci_once()
        self.assertEqual(result["status"], "ci_repair_evidence_rejected")
        repairs.enqueue_failure.assert_not_called()
        store.update_run_status.assert_called_once_with(self.item().run_id, "failed_gate")


class FailureClassificationTests(unittest.TestCase):
    def test_failure_classes_are_conservative(self):
        from ai_product_factory.github_rest import GitHubRestAdapter
        self.assertEqual(GitHubRestAdapter._failure_class(name="pytest", conclusion="failure", summary="test failed"), "code")
        self.assertEqual(GitHubRestAdapter._failure_class(name="runner unavailable", conclusion="failure", summary=""), "runner")
        self.assertEqual(GitHubRestAdapter._failure_class(name="deploy", conclusion="failure", summary="rate limit"), "quota")
        self.assertEqual(GitHubRestAdapter._failure_class(name="check", conclusion="failure", summary="mystery"), "unknown")
