import unittest

from ai_product_factory.autonomous_github import AutonomousGitHubLoop
from ai_product_factory.ci_repair import CIFailure, CIRepairController, RepairPolicy
from ai_product_factory.control_plane import MemoryControlPlaneStore
from ai_product_factory.direct_executor import ChangeSet, DirectExecutor
from ai_product_factory.github_loop import CIState
from ai_product_factory.github_rest import GitHubIssue


class FakeGitHub:
    def get_issue(self, issue_number):
        return GitHubIssue(issue_number, "Repair", "Body", "https://example/issue")
    def create_branch(self, branch, *, base_branch="main"):
        return "base"
    def commit_files(self, branch, files, *, message):
        return "plan" if any(p.startswith(".factory/plans/") for p in files) else "fix"
    def create_pull_request(self, **kwargs):
        raise AssertionError("not needed")
    def get_ci_state(self, pr_number):
        return CIState.FAILURE
    def merge_pull_request(self, pr_number):
        raise AssertionError("not needed")
    def close_issue(self, issue_number):
        return None


class Planner:
    def propose(self, failures, *, attempt):
        return ChangeSet(
            files={"src/fix.py": f"attempt = {attempt}\n"},
            commit_message=f"fix: repair CI attempt {attempt}",
        )


class CIRepairControllerTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryControlPlaneStore()
        p = self.store.create_project(project_key="x", name="X", repository="o/r", project_kind="app")
        t = self.store.create_task(project_id=p.id, title="Repair")
        r = self.store.create_run(task_id=t.id, execution_route="direct")
        loop = AutonomousGitHubLoop(FakeGitHub(), self.store)
        self.session = loop.start_issue(issue_number=14, branch="feat/repair", run_id=r.id, plan_markdown="# Plan")
        self.controller = CIRepairController(DirectExecutor(loop, self.store), self.store)

    def test_repairs_failed_ci_and_records_attempt(self):
        failure = CIFailure("test", "failure", "https://example/check")
        attempt = self.controller.repair(
            self.session, failures=(failure,), planner=Planner(), attempt=1
        )
        self.assertEqual(attempt.result.commit_sha, "fix")
        self.assertEqual(self.store.runs[self.session.run_id].status, "ci_pending")
        self.assertEqual(self.store.tool_usage[-1].operation, "repair_attempt")

    def test_attempt_limit_stops_loop(self):
        controller = CIRepairController(
            self.executor if hasattr(self, "executor") else DirectExecutor(
                AutonomousGitHubLoop(FakeGitHub(), self.store), self.store
            ),
            self.store,
            policy=RepairPolicy(max_attempts=1),
        )
        with self.assertRaises(RuntimeError):
            controller.repair(
                self.session,
                failures=(CIFailure("test", "failure"),),
                planner=Planner(),
                attempt=2,
            )
        self.assertEqual(self.store.runs[self.session.run_id].status, "failed_gate")

    def test_next_action_is_bounded(self):
        self.assertEqual(self.controller.next_action(ci_state=CIState.SUCCESS, attempts_used=0), "continue")
        self.assertEqual(self.controller.next_action(ci_state=CIState.PENDING, attempts_used=0), "wait")
        self.assertEqual(self.controller.next_action(ci_state=CIState.FAILURE, attempts_used=0), "repair")
        self.assertEqual(self.controller.next_action(ci_state=CIState.FAILURE, attempts_used=2), "failed_gate")

    def test_requires_failure_evidence(self):
        with self.assertRaises(ValueError):
            self.controller.repair(self.session, failures=(), planner=Planner(), attempt=1)


if __name__ == "__main__":
    unittest.main()
