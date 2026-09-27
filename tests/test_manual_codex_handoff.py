import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ai_product_factory.github_rest import GitHubIssue, GitHubPullRequest
from ai_product_factory.manual_codex_handoff import (
    ManualCodexItem,
    followup_once,
    prepare_once,
    run_marker,
)


def item(issue_number=None):
    return ManualCodexItem(
        run_id="run-1",
        task_id="task-1",
        project_key="demo",
        repository="owner/repo",
        issue_number=issue_number,
        title="Complex refactor",
        description="Refactor the subsystem safely.",
        codex_level=4,
    )


class ManualCodexHandoffTests(unittest.TestCase):
    def test_prepare_creates_issue_binds_and_waits(self):
        queue = MagicMock()
        queue.claim_next.return_value = item()
        github = MagicMock()
        github.find_open_issue_containing.return_value = None
        github.create_issue.return_value = GitHubIssue(
            17,
            "Complex refactor",
            run_marker("run-1"),
            "https://example/issues/17",
        )
        binding = MagicMock()

        with patch.dict("os.environ", {}, clear=True):
            out = prepare_once(
                "worker-1",
                queue=queue,
                binding=binding,
                github_factory=lambda repository: github,
            )

        self.assertEqual(out["status"], "awaiting_codex_manual")
        self.assertEqual(out["issue_number"], 17)
        self.assertEqual(out["marker"], "Factory run: run-1")
        github.create_issue.assert_called_once()
        body = github.create_issue.call_args.kwargs["body"]
        self.assertIn("Factory run: run-1", body)
        self.assertIn("Do not merge", body)
        self.assertIn("63-question benchmark", body)
        binding.bind_issue.assert_called_once()
        queue.mark_waiting.assert_called_once_with("run-1")

    def test_prepare_reuses_existing_marker_issue(self):
        queue = MagicMock()
        queue.claim_next.return_value = item()
        github = MagicMock()
        github.find_open_issue_containing.return_value = GitHubIssue(
            18,
            "Existing",
            run_marker("run-1"),
            "https://example/issues/18",
        )
        binding = MagicMock()

        with patch.dict("os.environ", {}, clear=True):
            out = prepare_once(
                "worker-1",
                queue=queue,
                binding=binding,
                github_factory=lambda repository: github,
            )

        self.assertEqual(out["issue_number"], 18)
        github.create_issue.assert_not_called()
        binding.bind_issue.assert_called_once()
        queue.mark_waiting.assert_called_once_with("run-1")

    def test_prepare_uses_already_bound_issue_without_duplicate(self):
        queue = MagicMock()
        queue.claim_next.return_value = item(issue_number=19)
        github = MagicMock()
        github.get_issue.return_value = GitHubIssue(
            19,
            "Bound",
            run_marker("run-1"),
            "https://example/issues/19",
        )

        with patch.dict("os.environ", {}, clear=True):
            out = prepare_once(
                "worker-1",
                queue=queue,
                binding=MagicMock(),
                github_factory=lambda repository: github,
            )

        self.assertEqual(out["issue_number"], 19)
        github.find_open_issue_containing.assert_not_called()
        github.create_issue.assert_not_called()

    def test_prepare_does_not_race_automatic_codex(self):
        queue = MagicMock()
        with patch.dict("os.environ", {"FACTORY_CODEX_ENABLED": "true"}, clear=True):
            out = prepare_once("worker-1", queue=queue)
        self.assertEqual(out["reason"], "automatic_codex_enabled")
        queue.claim_next.assert_not_called()

    def test_followup_waits_until_marker_pr_exists(self):
        queue = MagicMock()
        queue.next_waiting.return_value = item(issue_number=17)
        github = MagicMock()
        github.find_open_pull_request_containing.return_value = None

        out = followup_once(
            queue=queue,
            github_factory=lambda repository: github,
        )

        self.assertEqual(out["status"], "awaiting_codex_manual")
        queue.adopt_pr.assert_not_called()

    def test_followup_adopts_manual_pr_and_resumes_ci(self):
        queue = MagicMock()
        waiting = item(issue_number=17)
        queue.next_waiting.return_value = waiting
        pr = GitHubPullRequest(
            number=21,
            head_sha="abc123",
            html_url="https://example/pull/21",
            head_ref="codex/refactor",
            base_ref="main",
        )
        github = MagicMock()
        github.find_open_pull_request_containing.return_value = pr
        queue.adopt_pr.return_value = {"status": "ci_pending"}

        out = followup_once(
            queue=queue,
            github_factory=lambda repository: github,
        )

        self.assertEqual(out["status"], "ci_pending")
        self.assertEqual(out["candidate_commit"], "abc123")
        queue.adopt_pr.assert_called_once_with(waiting, pr)

    def test_followup_refuses_pr_targeting_non_main(self):
        queue = MagicMock()
        queue.next_waiting.return_value = item(issue_number=17)
        github = MagicMock()
        github.find_open_pull_request_containing.return_value = GitHubPullRequest(
            number=22,
            head_sha="def456",
            html_url="https://example/pull/22",
            head_ref="codex/refactor",
            base_ref="develop",
        )

        out = followup_once(
            queue=queue,
            github_factory=lambda repository: github,
        )

        self.assertEqual(out["status"], "blocked")
        self.assertIn("target main", out["error"])
        queue.adopt_pr.assert_not_called()


if __name__ == "__main__":
    unittest.main()
