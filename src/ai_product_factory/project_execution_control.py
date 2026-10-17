"""Pure project execution-control contract, independent of product lifecycle stage.

This module is not a database authorization boundary: a future versioned
service-role-only migration must enforce the same rules *at every claim*.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProjectExecutionState(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"


class ProjectCommand(StrEnum):
    START = "start"
    PAUSE = "pause"
    CONFIRM_PAUSED = "confirm_paused"
    RESUME = "resume"
    STOP = "stop"
    CONFIRM_STOPPED = "confirm_stopped"
    RESTART = "restart"


class ControlTransitionDenied(ValueError):
    pass


# Internal acknowledgements are worker/controller-only, never operator commands.
_INTERNAL = frozenset({ProjectCommand.CONFIRM_PAUSED, ProjectCommand.CONFIRM_STOPPED})
_EDGES: dict[tuple[ProjectExecutionState, ProjectCommand], ProjectExecutionState] = {
    (ProjectExecutionState.DRAFT, ProjectCommand.START): ProjectExecutionState.RUNNING,
    (ProjectExecutionState.RUNNING, ProjectCommand.PAUSE): ProjectExecutionState.PAUSING,
    (ProjectExecutionState.PAUSING, ProjectCommand.CONFIRM_PAUSED): ProjectExecutionState.PAUSED,
    (ProjectExecutionState.PAUSED, ProjectCommand.RESUME): ProjectExecutionState.RUNNING,
    (ProjectExecutionState.RUNNING, ProjectCommand.STOP): ProjectExecutionState.STOPPING,
    (ProjectExecutionState.PAUSING, ProjectCommand.STOP): ProjectExecutionState.STOPPING,
    (ProjectExecutionState.PAUSED, ProjectCommand.STOP): ProjectExecutionState.STOPPING,
    (ProjectExecutionState.STOPPING, ProjectCommand.CONFIRM_STOPPED): ProjectExecutionState.STOPPED,
    (ProjectExecutionState.STOPPED, ProjectCommand.RESTART): ProjectExecutionState.RUNNING,
}
_NO_NEW_WORK = frozenset({
    ProjectExecutionState.DRAFT,
    ProjectExecutionState.PAUSING,
    ProjectExecutionState.PAUSED,
    ProjectExecutionState.STOPPING,
    ProjectExecutionState.STOPPED,
})


@dataclass(frozen=True)
class ProjectControlSnapshot:
    state: ProjectExecutionState
    version: int
    generation: int

    def __post_init__(self) -> None:
        if type(self.version) is not int or self.version < 0:
            raise ValueError("invalid control version")
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("invalid execution generation")
        if not isinstance(self.state, ProjectExecutionState):
            raise ValueError("invalid execution state")


def can_claim_new_work(state: ProjectExecutionState | str) -> bool:
    # Unknown/garbled values must not enable execution.
    return state == ProjectExecutionState.RUNNING


def transition_control(
    snapshot: ProjectControlSnapshot,
    command: ProjectCommand,
    *,
    expected_version: int,
    actor_kind: str,
    acknowledged_quiescent: bool = False,
) -> ProjectControlSnapshot:
    """Pure fail-closed gate to be applied transactionally with durable locks.

    A successful transition does not create a task, issue, model invocation or
    release. START/RESTART and RESUME still require separate runtime readiness
    and operator authentication checks. Pending external work must quiesce
    before controller-only acknowledgement.
    """
    if type(expected_version) is not int or expected_version != snapshot.version:
        raise ControlTransitionDenied("stale project control version")
    if not isinstance(command, ProjectCommand):
        raise ControlTransitionDenied("unknown project control command")
    internal = command in _INTERNAL
    if internal:
        if actor_kind != "controller" or not acknowledged_quiescent:
            raise ControlTransitionDenied("controller acknowledgement requires verified quiescence")
    elif actor_kind != "operator":
        raise ControlTransitionDenied("explicit authenticated operator command required")
    next_state = _EDGES.get((snapshot.state, command))
    if next_state is None:
        raise ControlTransitionDenied(f"invalid control transition: {snapshot.state} -> {command}")
    new_generation = snapshot.generation + (1 if command in {
        ProjectCommand.START, ProjectCommand.RESUME, ProjectCommand.RESTART,
    } else 0)
    return ProjectControlSnapshot(next_state, snapshot.version + 1, new_generation)
