from __future__ import annotations

from .codex_policy import classify_codex_need
from .gates import requires_human_gate
from .models import ExecutionDecision, ExecutionRoute, RiskProfile, TaskProfile


def decide_execution(
    task: TaskProfile,
    risk: RiskProfile | None = None,
    *,
    codex_minimum_level: int = 3,
) -> ExecutionDecision:
    """Return the execution route and human-gate decision independently.

    Codex answers *how* the task is best executed. The gate policy answers
    *whether* the result may proceed without human approval. Keeping these
    decisions independent prevents a complex but low-risk task from requiring
    unnecessary human approval and prevents a simple production change from
    bypassing a gate.
    """
    if codex_minimum_level not in range(0, 5):
        raise ValueError("codex_minimum_level must be between 0 and 4")

    codex = classify_codex_need(task, minimum_level=codex_minimum_level)
    gate_required, gate_reasons = requires_human_gate(risk or RiskProfile())
    route = ExecutionRoute.CODEX if codex.should_use else ExecutionRoute.DIRECT

    return ExecutionDecision(
        route=route,
        codex=codex,
        human_gate_required=gate_required,
        gate_reasons=gate_reasons,
    )
