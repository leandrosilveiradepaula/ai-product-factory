"""An unprovable native CI test must not crash the whole follow-up lane."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ai_product_factory.bounded_continuation import drain_waiting_followups
from ai_product_factory.github_loop import CIState, GitHubLoopAction
from ai_product_factory.github_rest import GitHubCheckFailure
from ai_product_factory.runtime_cli import run_ci_once


class NativeTestScopeAttestationWaitingTests(unittest.TestCase):
    def test_unverified_contract_preserves_candidate_and_model_budget(self):
        candidate = "a" * 40
        item = SimpleNamespace(
            repository="owner/crm", issue_number=7, pr_number=197,
            candidate_commit=candidate, branch="factory/change-set-x",
            run_id="123e4567-e89b-42d3-a456-426614174002",
            human_gate_required=True,
        )
        queue = MagicMock()
        queue.next_pending.return_value = item
        github = MagicMock()
        github.get_pull_request.return_value = SimpleNamespace(
            head_sha=candidate, merged=False,
        )
        github.get_issue.return_value = SimpleNamespace(number=7)
        github.get_failed_checks.return_value = (
            GitHubCheckFailure(
                name="native-ci/tests", conclusion="failure",
                failure_class="code",
                summary="Verified failed GitHub Actions step (run and attempt bound)",
            ),
        )
        store = MagicMock()
        loop = MagicMock()
        loop.evaluate.return_value = SimpleNamespace(
            action=GitHubLoopAction.RETURN_TO_IMPLEMENTATION,
            ci_state=CIState.FAILURE,
        )
        repair = MagicMock()
        repair.enqueue_failure.side_effect = PermissionError(
            "native CI test-scope proof unavailable; no model call"
        )
        with (
            patch("ai_product_factory.runtime_cli.SupabaseCIFollowupQueue", return_value=queue),
            patch("ai_product_factory.runtime_cli.GitHubRestAdapter", return_value=github),
            patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore", return_value=store),
            patch("ai_product_factory.runtime_cli.AutonomousGitHubLoop", return_value=loop),
            patch("ai_product_factory.runtime_cli.SupabaseCIRepairQueue", return_value=repair),
            patch("ai_product_factory.runtime_cli._assert_project_followup", return_value=1),
        ):
            result = run_ci_once()
        self.assertEqual(result["status"], "ci_repair_attestation_blocked")
        self.assertEqual(result["run_id"], item.run_id)
        store.update_run_status.assert_not_called()
        store.record_tool_usage.assert_not_called()
        self.assertEqual(store.record_audit_event.call_args.kwargs["event_type"],
                         "ci.repair_attestation_blocked")
        self.assertEqual(store.record_audit_event.call_args.kwargs["payload"]["reason_code"],
                         "native_test_scope_not_verified")

    def test_attestation_waiting_does_not_starve_unrelated_ci(self):
        observed = [
            {"claimed": True, "status": "ci_repair_attestation_blocked", "run_id": "r1"},
            {"claimed": True, "status": "repair_pending", "run_id": "r2"},
        ]
        def next_item(seen):
            return observed[len(seen)]
        result = drain_waiting_followups(
            next_item, max_items=1, max_observations=2,
        )
        self.assertEqual(result["status"], "processed")
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["observed_waiting"], 1)
        self.assertEqual(result["waiting"], [{"id": "r1", "status": "ci_repair_attestation_blocked"}])
        self.assertEqual(result["items"], [{"id": "r2", "status": "repair_pending"}])


if __name__ == "__main__":
    unittest.main()
