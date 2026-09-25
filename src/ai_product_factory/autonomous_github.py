from __future__ import annotations

from dataclasses import dataclass

from .control_plane import ControlPlaneStore
from .github_loop import GitHubLoopAction, GitHubLoopCoordinator, GitHubLoopDecision
from .github_rest import GitHubIssue, GitHubPullRequest, GitHubRestAdapter


@dataclass(frozen=True)
class GitHubWorkSession:
    issue: GitHubIssue
    branch: str
    run_id: str
    base_sha: str
    plan_commit: str
    pull_request: GitHubPullRequest | None = None


class AutonomousGitHubLoop:
    """Executable GitHub workflow around an already-routed factory run."""

    def __init__(self, github: GitHubRestAdapter, store: ControlPlaneStore) -> None:
        self.github = github
        self.store = store
        self.ci = GitHubLoopCoordinator(github, store)

    def start_issue(self, *, issue_number: int, branch: str, run_id: str, plan_markdown: str,
                    base_branch: str = "main") -> GitHubWorkSession:
        issue = self.github.get_issue(issue_number)
        base_sha = self.github.create_branch(branch, base_branch=base_branch)
        plan_path = f".factory/plans/issue-{issue_number}.md"
        plan_commit = self.github.commit_files(
            branch, {plan_path: plan_markdown}, message=f"plan: issue #{issue_number}"
        )
        self.store.record_tool_usage(
            run_id=run_id, tool_family="github", operation="issue_branch_plan",
            metadata={"issue": issue_number, "branch": branch, "base_sha": base_sha, "plan_commit": plan_commit},
        )
        self.store.update_run_status(run_id, "implementing", candidate_commit=plan_commit)
        return GitHubWorkSession(issue, branch, run_id, base_sha, plan_commit)

    def commit_implementation(self, session: GitHubWorkSession, *, files: dict[str, str], message: str) -> str:
        sha = self.github.commit_files(session.branch, files, message=message)
        self.store.record_tool_usage(
            run_id=session.run_id, tool_family="github", operation="commit_implementation",
            metadata={"commit": sha, "files": sorted(files)},
        )
        self.store.update_run_status(session.run_id, "review_ready", candidate_commit=sha)
        return sha

    def open_pull_request(self, session: GitHubWorkSession, *, title: str, body: str,
                          base: str = "main") -> GitHubWorkSession:
        pr = self.github.create_pull_request(title=title, body=body, head=session.branch, base=base)
        self.store.record_tool_usage(
            run_id=session.run_id, tool_family="github", operation="create_pr",
            metadata={"pr": pr.number, "head_sha": pr.head_sha},
        )
        self.store.update_run_status(session.run_id, "ci_pending", candidate_commit=pr.head_sha)
        return GitHubWorkSession(
            session.issue, session.branch, session.run_id, session.base_sha, session.plan_commit, pr
        )

    def evaluate(self, session: GitHubWorkSession, *, human_gate_required: bool) -> GitHubLoopDecision:
        if session.pull_request is None:
            raise ValueError("pull request has not been opened")
        decision = self.ci.evaluate(
            pr_number=session.pull_request.number,
            run_id=session.run_id,
            human_gate_required=human_gate_required,
        )
        self.store.record_tool_usage(
            run_id=session.run_id, tool_family="github", operation="evaluate_ci",
            metadata={
                "pr": session.pull_request.number,
                "ci_state": decision.ci_state.value,
                "action": decision.action.value,
            },
        )
        if decision.action == GitHubLoopAction.MERGE:
            self.github.close_issue(session.issue.number)
            self.store.record_tool_usage(
                run_id=session.run_id, tool_family="github", operation="close_issue",
                metadata={"issue": session.issue.number},
            )
        return decision
