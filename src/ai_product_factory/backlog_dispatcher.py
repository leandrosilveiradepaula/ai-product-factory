from __future__ import annotations

from dataclasses import dataclass

from .models import Complexity, ExecutionDecision, RiskProfile, TaskProfile
from .orchestrator import decide_execution


@dataclass(frozen=True)
class PlannedTask:
    id: str
    project_key: str
    title: str
    description: str
    complexity: str = "medium"
    risk: dict | None = None
    metadata: dict | None = None


@dataclass(frozen=True)
class DispatchDecision:
    task: PlannedTask
    profile: TaskProfile
    risk: RiskProfile
    execution: ExecutionDecision


def _bool(data: dict, key: str) -> bool:
    return bool(data.get(key, False))


def profile_planned_task(task: PlannedTask) -> tuple[TaskProfile, RiskProfile]:
    meta=task.metadata or {}
    risk_data=task.risk or {}
    complexity=Complexity(task.complexity) if task.complexity in {x.value for x in Complexity} else Complexity.MEDIUM
    profile=TaskProfile(
        complexity=complexity,
        estimated_files=max(1,int(meta.get("estimated_files",1))),
        deep_debug=_bool(meta,"deep_debug"),
        large_refactor=_bool(meta,"large_refactor"),
        broad_repo_investigation=_bool(meta,"broad_repo_investigation"),
        direct_tools_sufficient=not _bool(meta,"direct_tools_insufficient"),
        repetitive_mechanical_change=_bool(meta,"repetitive_mechanical_change"),
        user_requires_codex=_bool(meta,"user_requires_codex"),
    )
    risk=RiskProfile(
        production_change=_bool(risk_data,"production_change"),
        destructive_data_change=_bool(risk_data,"destructive_data_change"),
        expands_sensitive_access=_bool(risk_data,"expands_sensitive_access"),
        new_paid_service=_bool(risk_data,"new_paid_service"),
        material_requirement_change=_bool(risk_data,"material_requirement_change"),
    )
    return profile,risk


class BacklogDispatcher:
    def __init__(self, *, codex_minimum_level: int = 3) -> None:
        self.codex_minimum_level=codex_minimum_level

    def decide(self, task: PlannedTask) -> DispatchDecision:
        profile,risk=profile_planned_task(task)
        execution=decide_execution(profile,risk,codex_minimum_level=self.codex_minimum_level)
        return DispatchDecision(task,profile,risk,execution)
