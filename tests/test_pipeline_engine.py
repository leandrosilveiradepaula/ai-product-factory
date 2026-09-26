import unittest

from ai_product_factory.autonomous_github import AutonomousGitHubLoop
from ai_product_factory.ci_repair import CIRepairController
from ai_product_factory.control_plane import MemoryControlPlaneStore
from ai_product_factory.direct_executor import ChangeSet, DirectExecutor
from ai_product_factory.github_loop import CIState
from ai_product_factory.github_rest import GitHubCheckFailure, GitHubIssue, GitHubPullRequest
from ai_product_factory.pipeline_engine import PipelineEngine, PipelineStatus
from ai_product_factory.review_gate import EvalResult, ReviewFinding, Severity
from ai_product_factory.browser_evidence import BrowserEvidence
from ai_product_factory.deployment import DeploymentResult
from ai_product_factory.preview_flow import VerifiedPreviewResult
from ai_product_factory.release_policy import ReleaseEnvironment


class FakeGitHub:
    def __init__(self):
        self.ci = CIState.SUCCESS
        self.merged = []
        self.closed = []
    def get_issue(self, n): return GitHubIssue(n, "Feature", "Body", "https://example/issue")
    def create_branch(self, branch, *, base_branch="main"): return "base"
    def commit_files(self, branch, files, *, message):
        return "plan" if any(p.startswith(".factory/plans/") for p in files) else "impl"
    def create_pull_request(self, *, title, body, head, base="main"):
        return GitHubPullRequest(1, "impl", "https://example/pr/1")
    def get_ci_state(self, n): return self.ci
    def get_failed_checks(self, n):
        return (GitHubCheckFailure("tests", "failure", "https://example/check", "failed"),)
    def merge_pull_request(self, n):
        self.merged.append(n); return "merge"
    def close_issue(self, n): self.closed.append(n)


class RepairPlanner:
    def propose(self, failures, *, attempt):
        return ChangeSet({"src/fix.py": f"attempt={attempt}\n"}, f"fix: attempt {attempt}")


class PipelineEngineTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryControlPlaneStore()
        p = self.store.create_project(project_key="x", name="X", repository="o/r", project_kind="app")
        t = self.store.create_task(project_id=p.id, title="Feature")
        r = self.store.create_run(task_id=t.id, execution_route="direct")
        self.github = FakeGitHub()
        loop = AutonomousGitHubLoop(self.github, self.store)
        self.session = loop.start_issue(issue_number=1, branch="feat/x", run_id=r.id, plan_markdown="# Plan")
        executor = DirectExecutor(loop, self.store)
        repair = CIRepairController(executor, self.store)
        self.engine = PipelineEngine(github_loop=loop, direct_executor=executor, repair_controller=repair, store=self.store)
        self.session = self.engine.implement(
            self.session,
            changeset=ChangeSet({"src/x.py": "x=1\n"}, "feat: x"),
            pr_title="x",
            pr_body="x",
        )

    def test_happy_path_requires_preview_before_merge(self):
        q = self.engine.evaluate_quality(self.session, evals=(EvalResult("tests", True),))
        self.assertEqual(q.status, PipelineStatus.CI_PENDING)
        out = self.engine.evaluate_ci(self.session, human_gate_required=False)
        self.assertEqual(out.status, PipelineStatus.PREVIEW_READY)
        preview = VerifiedPreviewResult(
            DeploymentResult("vercel", ReleaseEnvironment.PREVIEW, "success", "dep-1", "https://preview.example"),
            BrowserEvidence("success", "https://preview.example", ("page_load",)),
        )
        release = self.engine.finalize_preview(self.session, preview=preview)
        self.assertEqual(release.status, PipelineStatus.AWAITING_RELEASE)
        self.assertEqual(self.github.merged, [])

    def test_quality_failure_blocks_before_ci(self):
        out = self.engine.evaluate_quality(
            self.session,
            findings=(ReviewFinding("SEC", Severity.CRITICAL, "bad"),),
        )
        self.assertEqual(out.status, PipelineStatus.QUALITY_FAILED)

    def test_human_gate_waits(self):
        out = self.engine.evaluate_ci(self.session, human_gate_required=True)
        self.assertEqual(out.status, PipelineStatus.AWAITING_HUMAN)

    def test_ci_failure_enters_repair(self):
        self.github.ci = CIState.FAILURE
        out = self.engine.evaluate_ci(
            self.session,
            human_gate_required=False,
            repair_planner=RepairPlanner(),
        )
        self.assertEqual(out.status, PipelineStatus.REPAIRING)
        self.assertEqual(out.repair_attempts, 1)


if __name__ == "__main__":
    unittest.main()
