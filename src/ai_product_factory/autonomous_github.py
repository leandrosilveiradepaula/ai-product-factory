from __future__ import annotations

from dataclasses import dataclass

from .delivery_store import DeliveryStore
from .github_loop import GitHubLoopAction, GitHubLoopCoordinator, GitHubLoopDecision
from .github_rest import GitHubIssue, GitHubPullRequest, GitHubRestAdapter
from .preview_flow import VerifiedPreviewResult


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

    def __init__(self, github: GitHubRestAdapter, store: DeliveryStore) -> None:
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

    def commit_implementation(self, session: GitHubWorkSession, *, files: dict[str, str | None], message: str) -> str:
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
        evidence = {"pr": session.pull_request.number, "ci_state": decision.ci_state.value, "action": decision.action.value, "head_sha": session.pull_request.head_sha}
        record_evaluation = getattr(self.store, "record_evaluation", None)
        if record_evaluation is not None:
            record_evaluation(
                run_id=session.run_id,
                eval_type="github_ci",
                status=decision.ci_state.value,
                baseline_ref=session.pull_request.head_sha,
                result=evidence,
            )
        record_audit_event = getattr(self.store, "record_audit_event", None)
        if record_audit_event is not None:
            record_audit_event(
                run_id=session.run_id,
                event_type="delivery_ci_evaluated",
                payload=evidence,
                actor_ref="autonomous_github_loop",
            )
        return decision

    def finalize_verified_preview(self, session: GitHubWorkSession, preview: VerifiedPreviewResult) -> str:
        if session.pull_request is None:
            raise ValueError("pull request has not been opened")
        if preview.deployment.status != "success":
            raise ValueError("release requires successful preview deployment")
        if preview.browser_evidence.status != "success":
            raise ValueError("release requires successful browser/e2e evidence")
        if not preview.deployment.preview_url or preview.deployment.preview_url != preview.browser_evidence.preview_url:
            raise ValueError("preview deployment and browser evidence URL must match")
        self.store.update_run_status(session.run_id, "awaiting_release", candidate_commit=session.pull_request.head_sha)
        self.store.record_tool_usage(
            run_id=session.run_id,
            tool_family="github",
            operation="verified_preview_awaiting_human_merge",
            metadata={
                "pr": session.pull_request.number,
                "head_sha": session.pull_request.head_sha,
                "preview_url": preview.deployment.preview_url,
                "deployment_ref": preview.deployment.deployment_ref,
            },
        )
        record_audit_event = getattr(self.store, "record_audit_event", None)
        if record_audit_event is not None:
            record_audit_event(
                run_id=session.run_id,
                event_type="release.awaiting_human_merge",
                payload={
                    "pr": session.pull_request.number,
                    "head_sha": session.pull_request.head_sha,
                    "preview_url": preview.deployment.preview_url,
                    "deployment_ref": preview.deployment.deployment_ref,
                },
                actor_ref="autonomous_github_loop",
            )
        return "awaiting_release"

    def finalize_preview_not_required(self, session: GitHubWorkSession, *, reason: str, changed_files: tuple[str, ...]) -> str:
        if session.pull_request is None:
            raise ValueError("pull request has not been opened")
        if not reason.strip():
            raise ValueError("preview-not-required reason cannot be empty")
        self.store.update_run_status(session.run_id, "awaiting_release", candidate_commit=session.pull_request.head_sha)
        metadata={
            "pr": session.pull_request.number,
            "head_sha": session.pull_request.head_sha,
            "reason": reason,
            "changed_files": list(changed_files),
        }
        self.store.record_tool_usage(
            run_id=session.run_id,
            tool_family="github",
            operation="preview_not_required_awaiting_human_merge",
            metadata=metadata,
        )
        record_audit_event=getattr(self.store,"record_audit_event",None)
        if record_audit_event is not None:
            record_audit_event(
                run_id=session.run_id,
                event_type="release.preview_not_required",
                payload=metadata,
                actor_ref="autonomous_github_loop",
            )
        return "awaiting_release"

    def observe_manual_merge(self, session: GitHubWorkSession) -> str | None:
        if session.pull_request is None:
            raise ValueError("pull request has not been opened")
        current = self.github.get_pull_request(session.pull_request.number)
        if current.head_sha != session.pull_request.head_sha:
            raise RuntimeError("pull request head changed after verified preview")
        if not current.merged:
            self.store.update_run_status(session.run_id, "awaiting_release", candidate_commit=current.head_sha)
            return None
        if not current.merge_commit_sha:
            raise RuntimeError("merged pull request has no merge commit SHA")
        self.store.update_run_status(session.run_id, "merged", candidate_commit=current.merge_commit_sha)
        self.store.record_tool_usage(
            run_id=session.run_id,
            tool_family="github",
            operation="observe_human_merge",
            metadata={
                "pr": current.number,
                "head_sha": current.head_sha,
                "merge_sha": current.merge_commit_sha,
            },
        )
        record_audit_event = getattr(self.store, "record_audit_event", None)
        if record_audit_event is not None:
            record_audit_event(
                run_id=session.run_id,
                event_type="release.human_merge_observed",
                payload={"pr": current.number, "head_sha": current.head_sha, "merge_sha": current.merge_commit_sha},
                actor_ref="release-followup",
            )
        self.github.close_issue(session.issue.number)
        self.store.record_tool_usage(
            run_id=session.run_id,
            tool_family="github",
            operation="close_issue_after_human_merge",
            metadata={"issue": session.issue.number, "pr": current.number},
        )
        return current.merge_commit_sha
