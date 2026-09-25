from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .autonomous_github import GitHubWorkSession
from .direct_executor import ChangeSet, DirectExecutionResult, DirectExecutor
from .github_loop import CIState


@dataclass(frozen=True)
class CIFailure:
    name: str
    conclusion: str
    details_url: str | None = None
    summary: str | None = None


@dataclass(frozen=True)
class RepairPolicy:
    max_attempts: int = 2


@dataclass(frozen=True)
class RepairAttempt:
    number: int
    failures: tuple[CIFailure, ...]
    result: DirectExecutionResult


class RepairPlanner(Protocol):
    def propose(self, failures: tuple[CIFailure, ...], *, attempt: int) -> ChangeSet: ...


class CIRepairController:
    """Bounded repair loop. It never repairs indefinitely."""

    def __init__(self, executor: DirectExecutor, store, *, policy: RepairPolicy | None = None) -> None:
        self.executor = executor
        self.store = store
        self.policy = policy or RepairPolicy()
        if self.policy.max_attempts < 0:
            raise ValueError("max_attempts cannot be negative")

    def repair(
        self,
        session: GitHubWorkSession,
        *,
        failures: tuple[CIFailure, ...],
        planner: RepairPlanner,
        attempt: int,
    ) -> RepairAttempt:
        if attempt < 1:
            raise ValueError("attempt must start at 1")
        if attempt > self.policy.max_attempts:
            self.store.update_run_status(session.run_id, "failed_gate")
            raise RuntimeError("repair attempts exhausted")
        if not failures:
            raise ValueError("repair requires at least one CI failure")

        changeset = planner.propose(failures, attempt=attempt)
        result = self.executor.execute(session, changeset)
        self.store.record_tool_usage(
            run_id=session.run_id,
            tool_family="ci_repair",
            operation="repair_attempt",
            metadata={
                "attempt": attempt,
                "failures": [
                    {"name": f.name, "conclusion": f.conclusion, "details_url": f.details_url}
                    for f in failures
                ],
                "commit": result.commit_sha,
            },
        )
        self.store.update_run_status(session.run_id, "ci_pending", candidate_commit=result.commit_sha)
        return RepairAttempt(attempt, failures, result)

    def next_action(self, *, ci_state: CIState, attempts_used: int) -> str:
        if ci_state == CIState.SUCCESS:
            return "continue"
        if ci_state == CIState.PENDING:
            return "wait"
        if attempts_used >= self.policy.max_attempts:
            return "failed_gate"
        return "repair"
