from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .models import ExecutionRoute


class ModelRole(StrEnum):
    PRIMARY = "primary"
    CODEX = "codex"


@dataclass(frozen=True)
class ModelRequest:
    task_id: str
    objective: str
    context: str
    run_id: str | None = None
    acceptance_criteria: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelResult:
    role: ModelRole
    output: str
    provider_ref: str | None = None
    usage: dict[str, float] | None = None
    model: str | None = None


class ModelProvider(Protocol):
    def execute(self, request: ModelRequest) -> ModelResult: ...


@dataclass(frozen=True)
class ModelBudget:
    max_primary_calls_per_task: int = 6
    max_codex_calls_per_task: int = 1


class ModelExecutor:
    """Provider-neutral model routing with explicit per-task call budgets."""

    def __init__(
        self,
        *,
        primary: ModelProvider,
        codex: ModelProvider | None = None,
        budget: ModelBudget | None = None,
    ) -> None:
        self.primary = primary
        self.codex = codex
        self.budget = budget or ModelBudget()
        self._calls: dict[tuple[str, ModelRole], int] = {}

    def _consume(self, task_id: str, role: ModelRole) -> None:
        key = (task_id, role)
        used = self._calls.get(key, 0)
        limit = (
            self.budget.max_codex_calls_per_task
            if role == ModelRole.CODEX
            else self.budget.max_primary_calls_per_task
        )
        if used >= limit:
            raise RuntimeError(f"{role.value} call budget exhausted for task {task_id}")
        self._calls[key] = used + 1

    def execute(self, route: ExecutionRoute, request: ModelRequest) -> ModelResult:
        if route == ExecutionRoute.CODEX:
            if self.codex is None:
                raise RuntimeError("Codex provider is not configured")
            self._consume(request.task_id, ModelRole.CODEX)
            result = self.codex.execute(request)
            if result.role != ModelRole.CODEX:
                raise ValueError("Codex provider returned wrong role")
            return result

        self._consume(request.task_id, ModelRole.PRIMARY)
        result = self.primary.execute(request)
        if result.role != ModelRole.PRIMARY:
            raise ValueError("primary provider returned wrong role")
        return result

    def calls_used(self, task_id: str, role: ModelRole) -> int:
        return self._calls.get((task_id, role), 0)
