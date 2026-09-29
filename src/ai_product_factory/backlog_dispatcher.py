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


def _nonnegative_int(data:dict,key:str)->int:
    value=int(data.get(key,0) or 0)
    if value<0:raise ValueError(f"{key} must be non-negative")
    return value


def _optional_rate(data:dict,key:str)->float|None:
    if data.get(key) is None:return None
    value=float(data[key])
    if not 0<=value<=1:raise ValueError(f"{key} must be between 0 and 1")
    return value


def _optional_nonnegative(data:dict,key:str)->float|None:
    if data.get(key) is None:return None
    value=float(data[key])
    if value<0:raise ValueError(f"{key} must be non-negative")
    return value


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
        impacted_components=_nonnegative_int(meta,"impacted_components"),
        impact_unknowns=_nonnegative_int(meta,"impact_unknowns"),
        historical_repair_rate=_optional_rate(meta,"historical_repair_rate"),
        historical_conflict_rate=_optional_rate(meta,"historical_conflict_rate"),
        historical_direct_first_pass=_optional_rate(meta,"historical_direct_first_pass"),
        historical_codex_first_pass=_optional_rate(meta,"historical_codex_first_pass"),
        historical_codex_cost_ratio=_optional_nonnegative(meta,"historical_codex_cost_ratio"),
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
