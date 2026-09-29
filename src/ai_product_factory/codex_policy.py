from __future__ import annotations

from .models import CodexDecision, Complexity, TaskProfile


_COMPLEXITY_SCORE = {
    Complexity.LOW: 0,
    Complexity.MEDIUM: 1,
    Complexity.HIGH: 2,
    Complexity.VERY_HIGH: 3,
}


def classify_codex_need(task: TaskProfile, minimum_level: int = 3) -> CodexDecision:
    """Classify Codex need from 0 (do not use) to 4 (specialized/essential).

    The policy intentionally biases toward direct execution. A high score means
    Codex is likely to have enough marginal value to justify scarce usage.
    """
    score = _COMPLEXITY_SCORE[task.complexity]
    reasons: list[str] = []

    if task.estimated_files >= 25:
        score += 2
        reasons.append("mudanca muito ampla em arquivos")
    elif task.estimated_files >= 10:
        score += 1
        reasons.append("mudanca multifile relevante")

    if task.deep_debug:
        score += 2
        reasons.append("debug profundo")
    if task.large_refactor:
        score += 2
        reasons.append("refatoracao ampla")
    if task.broad_repo_investigation:
        score += 1
        reasons.append("investigacao ampla do repositorio")
    if task.repetitive_mechanical_change:
        score += 1
        reasons.append("alteracao mecanica extensa")
    if not task.direct_tools_sufficient:
        score += 1
        reasons.append("ferramentas diretas insuficientes")
    if task.impacted_components >= 8:
        score += 1
        reasons.append("impacto confirmado em muitos componentes")

    if task.impact_unknowns >= 3:
        score += 1
        reasons.append("impact analysis com unknowns relevantes")

    if task.historical_repair_rate is not None and task.historical_repair_rate >= 0.40:
        score += 1
        reasons.append("taxa historica de repair elevada")

    if task.historical_conflict_rate is not None and task.historical_conflict_rate >= 0.30:
        reasons.append("conflito historico elevado; concorrencia adaptativa deve reduzir contention")

    if task.historical_direct_first_pass is not None and task.historical_codex_first_pass is not None:
        advantage=task.historical_codex_first_pass-task.historical_direct_first_pass
        if advantage >= 0.15:
            score += 1
            reasons.append("Codex tem vantagem historica relevante de first-pass")
        elif advantage <= -0.10:
            score -= 1
            reasons.append("Direct tem vantagem historica relevante de first-pass")

    if task.historical_codex_cost_ratio is not None and task.historical_codex_cost_ratio >= 3 and not task.user_requires_codex:
        score -= 1
        reasons.append("custo historico do Codex e alto versus Direct")

    if task.user_requires_codex:
        score = max(score, minimum_level)
        reasons.append("uso explicitamente solicitado")

    level = max(0, min(4, score))
    return CodexDecision(
        level=level,
        should_use=level >= minimum_level,
        reasons=tuple(reasons) if reasons else ("execucao direta suficiente",),
        policy_version="v2",
    )
