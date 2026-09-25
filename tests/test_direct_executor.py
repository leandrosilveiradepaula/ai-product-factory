import unittest

from ai_product_factory.autonomous_github import AutonomousGitHubLoop
from ai_product_factory.control_plane import MemoryControlPlaneStore
from ai_product_factory.direct_executor import ChangeSet, DirectExecutionPolicy, DirectExecutor
from ai_product_factory.github_loop import CIState
from ai_product_factory.github_rest import GitHubIssue


class FakeGitHub:
    def get_issue(self, issue_number):
        return GitHubIssue(issue_number, "Feature", "Body", f"https://example/issue/{issue_number}")

    def create_branch(self, branch, *, base_branch="main"):
        return "base"

    def commit_files(self, branch, files, *, message):
        if ".factory/plans/issue-12.md" in files:
            return "plan"
        return "impl"

    def create_pull_request(self, *, title, body, head, base="main"):
        raise AssertionError("not needed")

    def get_ci_state(self, pr_number):
        return CIState.SUCCESS

    def merge_pull_request(self, pr_number):
        return "merge"

    def close_issue(self, issue_number):
        return None


class DirectExecutorTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryControlPlaneStore()
        project = self.store.create_project(
            project_key="factory",
            name="Factory",
            repository="owner/repo",
            project_kind="platform",
        )
        task = self.store.create_task(project_id=project.id, title="Direct")
        run = self.store.create_run(task_id=task.id, execution_route="direct")
        loop = AutonomousGitHubLoop(FakeGitHub(), self.store)
        self.session = loop.start_issue(
            issue_number=12,
            branch="feat/direct",
            run_id=run.id,
            plan_markdown="# Plan",
        )
        self.executor = DirectExecutor(loop, self.store)

    def test_executes_small_changeset(self):
        result = self.executor.execute(
            self.session,
            ChangeSet(
                files={"src/a.py": "x = 1\n", "tests/test_a.py": "def test_x(): pass\n"},
                commit_message="feat: add x",
            ),
        )
        self.assertEqual(result.commit_sha, "impl")
        self.assertEqual(result.file_count, 2)
        self.assertGreater(result.total_bytes, 0)
        self.assertEqual(self.store.tool_usage[-1].operation, "apply_changeset")

    def test_rejects_too_many_files(self):
        executor = DirectExecutor(
            self.executor.github_loop,
            self.store,
            policy=DirectExecutionPolicy(max_files=1),
        )
        with self.assertRaises(ValueError):
            executor.validate(
                ChangeSet(files={"a.py": "a", "b.py": "b"}, commit_message="x")
            )

    def test_rejects_large_changeset(self):
        executor = DirectExecutor(
            self.executor.github_loop,
            self.store,
            policy=DirectExecutionPolicy(max_total_bytes=3),
        )
        with self.assertRaises(ValueError):
            executor.validate(ChangeSet(files={"a.py": "1234"}, commit_message="x"))

    def test_rejects_parent_traversal_and_git_paths(self):
        for path in ("../secret", ".git/config", "src/../../secret"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.executor.validate(ChangeSet(files={path: "x"}, commit_message="x"))

    def test_rejects_secret_files(self):
        for path in (".env", ".env.local", "cert.pem", "private.key", "keys/id_rsa"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.executor.validate(ChangeSet(files={path: "secret"}, commit_message="x"))

    def test_rejects_empty_changeset_and_message(self):
        with self.assertRaises(ValueError):
            self.executor.validate(ChangeSet(files={}, commit_message="x"))
        with self.assertRaises(ValueError):
            self.executor.validate(ChangeSet(files={"a.py": "x"}, commit_message="  "))


if __name__ == "__main__":
    unittest.main()
