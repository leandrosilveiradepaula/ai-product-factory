import unittest

from ai_product_factory.control_plane import MemoryControlPlaneStore
from ai_product_factory.github_loop import (
    CIState,
    GitHubLoopAction,
    GitHubLoopCoordinator,
    decide_after_ci,
)


class FakeGitHub:
    def __init__(self, ci_state: CIState):
        self.ci_state = ci_state
        self.merged = []

    def get_ci_state(self, pr_number: int) -> CIState:
        return self.ci_state

    def merge_pull_request(self, pr_number: int) -> str:
        self.merged.append(pr_number)
        return "merge-sha-123"


class GitHubLoopDecisionTests(unittest.TestCase):
    def test_pending_ci_waits(self):
        d = decide_after_ci(CIState.PENDING, human_gate_required=False)
        self.assertEqual(d.action, GitHubLoopAction.WAIT_CI)

    def test_failed_ci_returns_to_implementation(self):
        d = decide_after_ci(CIState.FAILURE, human_gate_required=False)
        self.assertEqual(d.action, GitHubLoopAction.RETURN_TO_IMPLEMENTATION)

    def test_green_ci_with_gate_waits_for_human(self):
        d = decide_after_ci(CIState.SUCCESS, human_gate_required=True)
        self.assertEqual(d.action, GitHubLoopAction.WAIT_HUMAN)

    def test_green_ci_without_gate_merges(self):
        d = decide_after_ci(CIState.SUCCESS, human_gate_required=False)
        self.assertEqual(d.action, GitHubLoopAction.MERGE)


class GitHubLoopCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryControlPlaneStore()
        project = self.store.create_project(
            project_key="demo",
            name="Demo",
            repository="owner/demo",
            project_kind="application",
        )
        task = self.store.create_task(project_id=project.id, title="Feature")
        self.run = self.store.create_run(task_id=task.id, execution_route="direct")

    def test_failure_updates_run_for_correction_without_merge(self):
        github = FakeGitHub(CIState.FAILURE)
        d = GitHubLoopCoordinator(github, self.store).evaluate(
            pr_number=12,
            run_id=self.run.id,
            human_gate_required=False,
        )
        self.assertEqual(d.action, GitHubLoopAction.RETURN_TO_IMPLEMENTATION)
        self.assertEqual(self.store.runs[self.run.id].status, "needs_correction")
        self.assertEqual(github.merged, [])

    def test_success_without_gate_merges_and_records_sha(self):
        github = FakeGitHub(CIState.SUCCESS)
        d = GitHubLoopCoordinator(github, self.store).evaluate(
            pr_number=12,
            run_id=self.run.id,
            human_gate_required=False,
        )
        self.assertEqual(d.action, GitHubLoopAction.MERGE)
        self.assertEqual(github.merged, [12])
        self.assertEqual(self.store.runs[self.run.id].status, "merged")
        self.assertEqual(self.store.runs[self.run.id].candidate_commit, "merge-sha-123")

    def test_success_with_gate_never_merges(self):
        github = FakeGitHub(CIState.SUCCESS)
        d = GitHubLoopCoordinator(github, self.store).evaluate(
            pr_number=12,
            run_id=self.run.id,
            human_gate_required=True,
        )
        self.assertEqual(d.action, GitHubLoopAction.WAIT_HUMAN)
        self.assertEqual(self.store.runs[self.run.id].status, "awaiting_human")
        self.assertEqual(github.merged, [])


if __name__ == "__main__":
    unittest.main()
