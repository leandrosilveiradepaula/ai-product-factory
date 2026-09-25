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
    if task.user_requires_codex:
        score = max(score, minimum_level)
        reasons.append("uso explicitamente solicitado")

    level = max(0, min(4, score))
    return CodexDecision(
        level=level,
        should_use=level >= minimum_level,
        reasons=tuple(reasons) if reasons else ("execucao direta suficiente",),
    )
