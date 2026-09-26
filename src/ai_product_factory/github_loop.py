from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .delivery_store import DeliveryStore


class CIState(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILURE = "failure"


class GitHubLoopAction(StrEnum):
    WAIT_CI = "wait_ci"
    RETURN_TO_IMPLEMENTATION = "return_to_implementation"
    WAIT_HUMAN = "wait_human"
    PREVIEW_READY = "preview_ready"


@dataclass(frozen=True)
class GitHubLoopDecision:
    ci_state: CIState
    action: GitHubLoopAction
    reason: str


class GitHubAdapter(Protocol):
    def get_ci_state(self, pr_number: int) -> CIState: ...
    def merge_pull_request(self, pr_number: int) -> str: ...


def decide_after_ci(ci_state: CIState, *, human_gate_required: bool) -> GitHubLoopDecision:
    if ci_state == CIState.PENDING:
        return GitHubLoopDecision(ci_state, GitHubLoopAction.WAIT_CI, "CI ainda em execucao")
    if ci_state == CIState.FAILURE:
        return GitHubLoopDecision(ci_state, GitHubLoopAction.RETURN_TO_IMPLEMENTATION, "CI falhou")
    if human_gate_required:
        return GitHubLoopDecision(ci_state, GitHubLoopAction.WAIT_HUMAN, "CI verde, mas existe gate humano")
    return GitHubLoopDecision(ci_state, GitHubLoopAction.PREVIEW_READY, "CI verde; preview verificável é obrigatório antes do merge")


class GitHubLoopCoordinator:
    """Coordinates CI feedback and merge without embedding GitHub transport details."""

    def __init__(self, github: GitHubAdapter, store: DeliveryStore) -> None:
        self.github = github
        self.store = store

    def evaluate(self, *, pr_number: int, run_id: str, human_gate_required: bool) -> GitHubLoopDecision:
        ci_state = self.github.get_ci_state(pr_number)
        decision = decide_after_ci(ci_state, human_gate_required=human_gate_required)

        if decision.action == GitHubLoopAction.WAIT_CI:
            self.store.update_run_status(run_id, "ci_pending")
        elif decision.action == GitHubLoopAction.RETURN_TO_IMPLEMENTATION:
            self.store.update_run_status(run_id, "needs_correction")
        elif decision.action == GitHubLoopAction.WAIT_HUMAN:
            self.store.update_run_status(run_id, "awaiting_human")
        elif decision.action == GitHubLoopAction.PREVIEW_READY:
            self.store.update_run_status(run_id, "preview_ready")

        return decision
