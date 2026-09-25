from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .autonomous_github import AutonomousGitHubLoop, GitHubWorkSession
from .ci_repair import CIRepairController, RepairPlanner
from .direct_executor import ChangeSet, DirectExecutor
from .github_loop import CIState, GitHubLoopAction
from .review_gate import EvalResult, ReviewFinding, evaluate_quality_gate


class PipelineStatus(StrEnum):
    IMPLEMENTING = "implementing"
    QUALITY_FAILED = "quality_failed"
    CI_PENDING = "ci_pending"
    REPAIRING = "repairing"
    AWAITING_HUMAN = "awaiting_human"
    FAILED_GATE = "failed_gate"
    MERGED = "merged"


@dataclass(frozen=True)
class PipelineOutcome:
    status: PipelineStatus
    reason: str
    repair_attempts: int = 0


class PipelineEngine:
    """Composes implementation, quality, CI, repair and merge into one bounded flow."""

    def __init__(
        self,
        *,
        github_loop: AutonomousGitHubLoop,
        direct_executor: DirectExecutor,
        repair_controller: CIRepairController,
        store,
    ) -> None:
        self.github_loop = github_loop
        self.direct_executor = direct_executor
        self.repair_controller = repair_controller
        self.store = store

    def implement(
        self,
        session: GitHubWorkSession,
        *,
        changeset: ChangeSet,
        pr_title: str,
        pr_body: str,
    ) -> GitHubWorkSession:
        self.direct_executor.execute(session, changeset)
        return self.github_loop.open_pull_request(
            session,
            title=pr_title,
            body=pr_body,
        )

    def evaluate_quality(
        self,
        session: GitHubWorkSession,
        *,
        findings: tuple[ReviewFinding, ...] = (),
        evals: tuple[EvalResult, ...] = (),
    ) -> PipelineOutcome:
        decision = evaluate_quality_gate(findings=findings, evals=evals)
        self.store.record_tool_usage(
            run_id=session.run_id,
            tool_family="quality_gate",
            operation="evaluate",
            metadata={
                "passed": decision.passed,
                "reasons": list(decision.reasons),
                "critical_findings": len(decision.critical_findings),
                "failed_required_evals": len(decision.failed_required_evals),
            },
        )
        if not decision.passed:
            self.store.update_run_status(session.run_id, "quality_failed")
            return PipelineOutcome(PipelineStatus.QUALITY_FAILED, "; ".join(decision.reasons))
        return PipelineOutcome(PipelineStatus.CI_PENDING, "quality gates passed")

    def evaluate_ci(
        self,
        session: GitHubWorkSession,
        *,
        human_gate_required: bool,
        repair_planner: RepairPlanner | None = None,
        repair_attempts: int = 0,
    ) -> PipelineOutcome:
        if session.pull_request is None:
            raise ValueError("pull request has not been opened")

        decision = self.github_loop.evaluate(
            session,
            human_gate_required=human_gate_required,
        )

        if decision.action == GitHubLoopAction.MERGE:
            return PipelineOutcome(PipelineStatus.MERGED, decision.reason, repair_attempts)
        if decision.action == GitHubLoopAction.WAIT_HUMAN:
            return PipelineOutcome(PipelineStatus.AWAITING_HUMAN, decision.reason, repair_attempts)
        if decision.action == GitHubLoopAction.WAIT_CI:
            return PipelineOutcome(PipelineStatus.CI_PENDING, decision.reason, repair_attempts)

        if repair_planner is None:
            self.store.update_run_status(session.run_id, "failed_gate")
            return PipelineOutcome(
                PipelineStatus.FAILED_GATE,
                "CI failed and no repair planner is available",
                repair_attempts,
            )

        failures = tuple(
            self.repair_controller.executor.github_loop.github.get_failed_checks(
                session.pull_request.number
            )
        )
        if not failures:
            self.store.update_run_status(session.run_id, "failed_gate")
            return PipelineOutcome(
                PipelineStatus.FAILED_GATE,
                "CI failed but no structured failure evidence was available",
                repair_attempts,
            )

        next_attempt = repair_attempts + 1
        try:
            self.repair_controller.repair(
                session,
                failures=tuple(
                    __import__("ai_product_factory.ci_repair", fromlist=["CIFailure"]).CIFailure(
                        name=f.name,
                        conclusion=f.conclusion,
                        details_url=f.details_url,
                        summary=f.summary,
                    )
                    for f in failures
                ),
                planner=repair_planner,
                attempt=next_attempt,
            )
        except RuntimeError:
            return PipelineOutcome(
                PipelineStatus.FAILED_GATE,
                "repair attempts exhausted",
                repair_attempts,
            )

        return PipelineOutcome(
            PipelineStatus.REPAIRING,
            f"repair attempt {next_attempt} committed",
            next_attempt,
        )
