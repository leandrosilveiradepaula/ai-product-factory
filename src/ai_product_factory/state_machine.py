from __future__ import annotations

from .models import LifecycleStage, ProjectState


_ALLOWED: dict[LifecycleStage, set[LifecycleStage]] = {
    LifecycleStage.DISCOVERY: {LifecycleStage.SPECIFICATION, LifecycleStage.BLOCKED},
    LifecycleStage.SPECIFICATION: {LifecycleStage.DISCOVERY, LifecycleStage.PLANNING, LifecycleStage.BLOCKED},
    LifecycleStage.PLANNING: {LifecycleStage.SPECIFICATION, LifecycleStage.IMPLEMENTATION, LifecycleStage.BLOCKED},
    LifecycleStage.IMPLEMENTATION: {LifecycleStage.REVIEW, LifecycleStage.BLOCKED},
    LifecycleStage.REVIEW: {LifecycleStage.IMPLEMENTATION, LifecycleStage.VALIDATION, LifecycleStage.BLOCKED},
    LifecycleStage.VALIDATION: {LifecycleStage.IMPLEMENTATION, LifecycleStage.PREVIEW, LifecycleStage.BLOCKED},
    LifecycleStage.PREVIEW: {LifecycleStage.IMPLEMENTATION, LifecycleStage.HUMAN_GATE, LifecycleStage.RELEASE, LifecycleStage.BLOCKED},
    LifecycleStage.HUMAN_GATE: {LifecycleStage.IMPLEMENTATION, LifecycleStage.RELEASE, LifecycleStage.BLOCKED},
    LifecycleStage.RELEASE: {LifecycleStage.OPERATIONS, LifecycleStage.BLOCKED},
    LifecycleStage.OPERATIONS: {LifecycleStage.PLANNING, LifecycleStage.BLOCKED},
    LifecycleStage.BLOCKED: {
        LifecycleStage.DISCOVERY,
        LifecycleStage.SPECIFICATION,
        LifecycleStage.PLANNING,
        LifecycleStage.IMPLEMENTATION,
        LifecycleStage.REVIEW,
        LifecycleStage.VALIDATION,
        LifecycleStage.PREVIEW,
        LifecycleStage.HUMAN_GATE,
        LifecycleStage.RELEASE,
        LifecycleStage.OPERATIONS,
    },
}


class InvalidTransition(ValueError):
    pass


def transition(state: ProjectState, target: LifecycleStage) -> ProjectState:
    if target not in _ALLOWED[state.stage]:
        raise InvalidTransition(f"invalid transition: {state.stage} -> {target}")
    state.stage = target
    return state
