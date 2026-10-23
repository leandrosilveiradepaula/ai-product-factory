"""CI dispatch permission and exact-candidate gates, without external effects."""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ai_product_factory.github_rest import GitHubRequestError
from ai_product_factory.runtime_cli import run_ci_once

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
BRANCH = "factory/change-set-candidate"
REPOSITORY = "owner/factory"


def candidate_pr(**changes):
    attributes = {
        "number": 9,
        "head_sha": SHA,
        "head_ref": BRANCH,
        "head_repository": REPOSITORY,
        "base_ref": "main",
        "state": "open",
        "merged": False,
        "draft": False,
    }
    attributes.update(changes)
    return SimpleNamespace(**attributes)


class SameRepoCIDispatchBoundaryTests(unittest.TestCase):
    def execute(self, *, live_pr=None, live_branch=SHA, request_error=None):
        item = SimpleNamespace(
            repository=REPOSITORY,
            issue_number=7,
            pr_number=9,
            candidate_commit=SHA,
            branch=BRANCH,
            run_id="run-from-verified-control-plane",
            human_gate_required=True,
        )
        queue = MagicMock()
        queue.next_pending.return_value = item
        queue.has_ci_dispatch_receipt.return_value = False

        github = MagicMock()
        github.last_ci_evidence_present = False
        github.get_issue.return_value = SimpleNamespace(number=7)
        github.get_pull_request.side_effect = [candidate_pr(), live_pr or candidate_pr()]
        github.get_branch_sha.return_value = live_branch
        github.dispatch_workflow.side_effect = request_error

        store = MagicMock()
        loop = MagicMock()
        loop.evaluate.return_value = SimpleNamespace(
            action=SimpleNamespace(value="wait_ci"),
            ci_state=SimpleNamespace(value="pending"),
        )
        with (
            patch.dict("os.environ", {"GITHUB_REPOSITORY": REPOSITORY}, clear=False),
            patch("ai_product_factory.runtime_cli._assert_project_followup"),
            patch("ai_product_factory.runtime_cli.SupabaseCIFollowupQueue", return_value=queue),
            patch("ai_product_factory.runtime_cli.GitHubRestAdapter", return_value=github),
            patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore", return_value=store),
            patch("ai_product_factory.runtime_cli.AutonomousGitHubLoop", return_value=loop),
        ):
            result = run_ci_once()
        return result, github, store, queue

    def test_exact_current_pr_and_branch_dispatch_only_validate_once(self):
        result, github, store, queue = self.execute()
        self.assertEqual(result["status"], "ci_triggered")
        github.get_pull_request.assert_called_with(9)
        self.assertEqual(github.get_pull_request.call_count, 2)
        github.get_branch_sha.assert_called_once_with(BRANCH)
        github.dispatch_workflow.assert_called_once_with("validate.yml", ref=BRANCH)
        queue.has_ci_dispatch_receipt.assert_called_once_with(
            run_id="run-from-verified-control-plane",
            pr_number=9, candidate_commit=SHA, branch=BRANCH,
            workflow="validate.yml",
        )
        store.record_tool_usage.assert_called_once()
        store.record_audit_event.assert_called_once()

    def test_pr_moves_between_initial_ci_evaluation_and_dispatch(self):
        result, github, store, _ = self.execute(
            live_pr=candidate_pr(head_sha="b" * 40)
        )
        self.assertEqual(result["status"], "ci_dispatch_identity_blocked")
        github.get_branch_sha.assert_not_called()
        github.dispatch_workflow.assert_not_called()
        store.record_tool_usage.assert_not_called()
        store.record_audit_event.assert_not_called()

    def test_untrusted_pr_identity_and_draft_block_workflow_dispatch(self):
        cases = (
            {"head_ref": "other-branch"},
            {"head_repository": "attacker/repo"},
            {"base_ref": "preview/other"},
            {"state": "closed"},
            {"merged": True},
            {"draft": True},
            {"draft": None},
        )
        for mismatch in cases:
            with self.subTest(mismatch=mismatch):
                result, github, store, _ = self.execute(
                    live_pr=candidate_pr(**mismatch)
                )
                self.assertEqual(result["status"], "ci_dispatch_identity_blocked")
                github.dispatch_workflow.assert_not_called()
                github.get_branch_sha.assert_not_called()
                store.record_tool_usage.assert_not_called()

    def test_branch_ref_moves_even_if_pr_snapshot_is_still_old(self):
        result, github, store, _ = self.execute(live_branch="b" * 40)
        self.assertEqual(result["status"], "ci_dispatch_branch_drift_blocked")
        github.get_branch_sha.assert_called_once_with(BRANCH)
        github.dispatch_workflow.assert_not_called()
        store.record_tool_usage.assert_not_called()
        store.record_audit_event.assert_not_called()

    def test_missing_actions_write_is_audited_not_a_fake_ci_receipt(self):
        result, github, store, _ = self.execute(
            request_error=GitHubRequestError(403)
        )
        self.assertEqual(result["status"], "ci_dispatch_permission_blocked")
        github.dispatch_workflow.assert_called_once_with("validate.yml", ref=BRANCH)
        store.record_tool_usage.assert_not_called()
        store.record_audit_event.assert_called_once()
        self.assertEqual(
            store.record_audit_event.call_args.kwargs["event_type"],
            "ci.same_repo_dispatch_permission_denied",
        )
        self.assertEqual(
            store.record_audit_event.call_args.kwargs["payload"]["http_status"], 403
        )
        self.assertEqual(
            store.record_audit_event.call_args.kwargs["payload"]["required_permission"],
            "actions:write",
        )

    def test_other_github_api_errors_remain_visible(self):
        with self.assertRaises(GitHubRequestError):
            self.execute(request_error=GitHubRequestError(500))

    def test_workflow_permissions_are_local_to_the_ci_followup_job(self):
        text = (ROOT / ".github/workflows/autonomous-runner.yml").read_text()
        ci = text.split("\n  ci-followup:\n", 1)[1].split(
            "\n  specialist-security:\n", 1
        )[0]
        self.assertIn("\n      actions: write # Needed only for exact same-repo", ci)
        self.assertIn("\n      contents: read\n", ci)
        self.assertIn("\n      pull-requests: read\n", ci)
        self.assertNotIn("\n      contents: write\n", ci)
        self.assertNotIn("\n      issues: write\n", ci)
        self.assertNotIn("\n      pull-requests: write\n", ci)
        self.assertNotIn("OPENAI_API_KEY", ci)
        for name, next_job in (
            ("specialist-security", "specialist-qa"),
            ("specialist-qa", "specialist-operations"),
            ("specialist-operations", "release-followup"),
            ("release-followup", "dispatch"),
        ):
            job = text.split(f"\n  {name}:\n", 1)[1].split(
                f"\n  {next_job}:\n", 1
            )[0]
            self.assertNotIn("\n      actions: write", job)

        validate = (ROOT / ".github/workflows/validate.yml").read_text()
        self.assertIn("\n  workflow_dispatch:", validate)
        self.assertIn("\npermissions:\n  contents: read\n", validate)


if __name__ == "__main__":
    unittest.main()
