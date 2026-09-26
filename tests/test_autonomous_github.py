import unittest

from ai_product_factory.autonomous_github import AutonomousGitHubLoop
from ai_product_factory.control_plane import MemoryControlPlaneStore
from ai_product_factory.github_loop import CIState, GitHubLoopAction
from ai_product_factory.github_rest import GitHubIssue, GitHubPullRequest
from ai_product_factory.browser_evidence import BrowserEvidence
from ai_product_factory.deployment import DeploymentResult
from ai_product_factory.preview_flow import VerifiedPreviewResult
from ai_product_factory.release_policy import ReleaseEnvironment


class FakeGitHub:
    def __init__(self):
        self.ci_state = CIState.SUCCESS
        self.closed = []
        self.merged = []

    def get_issue(self, issue_number):
        return GitHubIssue(issue_number, "Feature", "Body", f"https://example/issue/{issue_number}")

    def create_branch(self, branch, *, base_branch="main"):
        return "base123"

    def commit_files(self, branch, files, *, message):
        return "plan123" if ".factory/plans/issue-5.md" in files else "impl456"

    def create_pull_request(self, *, title, body, head, base="main"):
        return GitHubPullRequest(9, "impl456", "https://example/pr/9")

    def get_ci_state(self, pr_number):
        return self.ci_state

    def merge_pull_request(self, pr_number):
        self.merged.append(pr_number)
        return "merge999"

    def close_issue(self, issue_number):
        self.closed.append(issue_number)


class AutonomousGitHubLoopTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryControlPlaneStore()
        p = self.store.create_project(
            project_key="factory", name="Factory", repository="owner/repo", project_kind="platform"
        )
        t = self.store.create_task(project_id=p.id, title="GitHub loop")
        self.run = self.store.create_run(task_id=t.id, execution_route="direct")
        self.github = FakeGitHub()
        self.loop = AutonomousGitHubLoop(self.github, self.store)

    def _session_with_pr(self):
        session = self.loop.start_issue(issue_number=5, branch="feat/5", run_id=self.run.id, plan_markdown="# Plan")
        self.loop.commit_implementation(session, files={"x.py": "x = 1\n"}, message="feat: implement")
        return self.loop.open_pull_request(session, title="Feature", body="Closes #5")

    def test_full_green_loop_stops_at_preview_boundary(self):
        session = self._session_with_pr()
        decision = self.loop.evaluate(session, human_gate_required=False)
        self.assertEqual(decision.action, GitHubLoopAction.PREVIEW_READY)
        self.assertEqual(self.github.merged, [])
        self.assertEqual(self.github.closed, [])
        self.assertEqual(self.store.runs[self.run.id].status, "preview_ready")

    def test_verified_preview_allows_merge_and_closes_issue(self):
        session = self._session_with_pr()
        self.loop.evaluate(session, human_gate_required=False)
        preview = VerifiedPreviewResult(
            DeploymentResult("vercel", ReleaseEnvironment.PREVIEW, "success", "dep-1", "https://preview.example"),
            BrowserEvidence("success", "https://preview.example", ("page_load", "console_clean")),
        )
        merge_sha = self.loop.finalize_verified_preview(session, preview)
        self.assertEqual(merge_sha, "merge999")
        self.assertEqual(self.github.merged, [9])
        self.assertEqual(self.github.closed, [5])
        self.assertEqual(self.store.runs[self.run.id].status, "merged")

    def test_unverified_preview_cannot_merge(self):
        session = self._session_with_pr()
        preview = VerifiedPreviewResult(
            DeploymentResult("vercel", ReleaseEnvironment.PREVIEW, "success", "dep-1", "https://preview.example"),
            BrowserEvidence("failure", "https://preview.example"),
        )
        with self.assertRaises(ValueError):
            self.loop.finalize_verified_preview(session, preview)
        self.assertEqual(self.github.merged, [])

    def test_failed_ci_returns_to_implementation_without_closing_issue(self):
        self.github.ci_state = CIState.FAILURE
        session = self._session_with_pr()
        decision = self.loop.evaluate(session, human_gate_required=False)
        self.assertEqual(decision.action, GitHubLoopAction.RETURN_TO_IMPLEMENTATION)
        self.assertEqual(self.github.closed, [])

    def test_human_gate_blocks_merge_even_with_green_ci(self):
        session = self._session_with_pr()
        decision = self.loop.evaluate(session, human_gate_required=True)
        self.assertEqual(decision.action, GitHubLoopAction.WAIT_HUMAN)
        self.assertEqual(self.github.merged, [])
        self.assertEqual(self.github.closed, [])

if __name__ == "__main__":
    unittest.main()
