from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Protocol
from uuid import uuid4


def _id() -> str:
    return str(uuid4())


@dataclass(frozen=True)
class ProjectRecord:
    id: str
    project_key: str
    name: str
    repository: str
    project_kind: str
    lifecycle_stage: str = "discovery"


@dataclass(frozen=True)
class TaskRecord:
    id: str
    project_id: str
    title: str
    description: str = ""
    status: str = "queued"
    complexity: str = "low"
    acceptance_criteria: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunRecord:
    id: str
    task_id: str
    status: str = "created"
    execution_route: str | None = None
    source_commit: str | None = None
    candidate_commit: str | None = None
    branch_name: str | None = None


@dataclass(frozen=True)
class DecisionRecord:
    id: str
    project_id: str
    task_id: str | None
    decision_type: str
    decision: dict[str, Any]
    decided_by: str
    question: str | None = None


@dataclass(frozen=True)
class ToolUsageRecord:
    id: str
    run_id: str
    tool_family: str
    operation: str | None = None
    usage_units: float | None = None
    estimated_cost: float | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class CodexUsageRecord:
    id: str
    run_id: str
    policy_level: int
    invocation_count: int
    reasons: tuple[str, ...] = ()
    reported_usage: dict[str, Any] | None = None


class ControlPlaneStore(Protocol):
    def create_project(self, *, project_key: str, name: str, repository: str, project_kind: str) -> ProjectRecord: ...
    def get_project_by_key(self, project_key: str) -> ProjectRecord | None: ...
    def create_task(self, *, project_id: str, title: str, description: str = "", complexity: str = "low", acceptance_criteria: tuple[str, ...] = ()) -> TaskRecord: ...
    def create_run(self, *, task_id: str, execution_route: str | None = None, source_commit: str | None = None, branch_name: str | None = None) -> RunRecord: ...
    def update_task_status(self, task_id: str, status: str) -> TaskRecord: ...
    def update_run_status(self, run_id: str, status: str, *, candidate_commit: str | None = None) -> RunRecord: ...
    def record_decision(self, *, project_id: str, decision_type: str, decision: dict[str, Any], decided_by: str, task_id: str | None = None, question: str | None = None) -> DecisionRecord: ...
    def record_tool_usage(self, *, run_id: str, tool_family: str, operation: str | None = None, usage_units: float | None = None, estimated_cost: float | None, metadata: dict[str, Any] | None = None) -> ToolUsageRecord: ...
    def record_codex_usage(self, *, run_id: str, policy_level: int, invocation_count: int, reasons: tuple[str, ...] = (), reported_usage: dict[str, Any] | None = None) -> CodexUsageRecord: ...


class MemoryControlPlaneStore:
    """Deterministic in-process store used for tests and local orchestration.

    The public methods intentionally mirror the future Supabase adapter so the
    orchestrator can be tested without requiring external infrastructure.
    """

    def __init__(self) -> None:
        self.projects: dict[str, ProjectRecord] = {}
        self.tasks: dict[str, TaskRecord] = {}
        self.runs: dict[str, RunRecord] = {}
        self.decisions: list[DecisionRecord] = []
        self.tool_usage: list[ToolUsageRecord] = []
        self.codex_usage: list[CodexUsageRecord] = []

    def create_project(self, *, project_key: str, name: str, repository: str, project_kind: str) -> ProjectRecord:
        if self.get_project_by_key(project_key) is not None:
            raise ValueError(f"project_key already exists: {project_key}")
        record = ProjectRecord(
            id=_id(),
            project_key=project_key,
            name=name,
            repository=repository,
            project_kind=project_kind,
        )
        self.projects[record.id] = record
        return record

    def get_project_by_key(self, project_key: str) -> ProjectRecord | None:
        return next((p for p in self.projects.values() if p.project_key == project_key), None)

    def create_task(
        self,
        *,
        project_id: str,
        title: str,
        description: str = "",
        complexity: str = "low",
        acceptance_criteria: tuple[str, ...] = (),
     ) -> TaskRecord:
        self._require_project(project_id)
        record = TaskRecord(
            id=_id(),
            project_id=project_id,
            title=title,
            description=description,
            complexity=complexity,
            acceptance_criteria=acceptance_criteria,
        )
        self.tasks[record.id] = record
        return record

    def update_task_status(self, task_id: str, status: str) -> TaskRecord:
        current = self._require_task(task_id)
        updated = replace(current, status=status)
        self.tasks[task_id] = updated
        return updated

    def create_run(
        self,
        *,
        task_id: str,
        execution_route: str | None = None,
        source_commit: str | None = None,
        branch_name: str | None = None,
    ) -> RunRecord:
        self._require_task(task_id)
        record = RunRecord(
            id=_id(),
            task_id=task_id,
            execution_route=execution_route,
            source_commit=source_commit,
            branch_name=branch_name,
        )
        self.runs[record.id] = record
        return record

    def update_run_status(self, run_id: str, status: str, *, candidate_commit: str | None = None) -> RunRecord:
        current = self._require_run(run_id)
        updated = replace(
            current,
            status=status,
            candidate_commit=candidate_commit if candidate_commit is not None else current.candidate_commit,
        )
        self.runs[run_id] = updated
        return updated

    def record_decision(
        self,
        *,
        project_id: str,
        decision_type: str,
        decision: dict[str, Any],
        decided_by: str,
        task_id: str | None = None,
        question: str | None = None,
    ) -> DecisionRecord:
        self._require_project(project_id)
        if task_id is not None:
            task = self._require_task(task_id)
            if task.project_id != project_id:
                raise ValueError("task does not belong to project")
        record = DecisionRecord(
            id=_id(),
            project_id=project_id,
            task_id=task_id,
            decision_type=decision_type,
            decision=dict(decision),
            decided_by=decided_by,
            question=question,
        )
        self.decisions.append(record)
        return record

    def record_tool_usage(
        self,
        *,
        run_id: str,
        tool_family: str,
        operation: str | None = None,
        usage_units: float | None = None,
        estimated_cost: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolUsageRecord:
        self._require_run(run_id)
        record = ToolUsageRecord(
            id=_id(),
            run_id=run_id,
            tool_family=tool_family,
            operation=operation,
            usage_units=usage_units,
            estimated_cost=estimated_cost,
            metadata=dict(metadata or {}),
        )
        self.tool_usage.append(record)
        return record

    def record_codex_usage(
        self,
        *,
        run_id: str,
        policy_level: int,
        invocation_count: int,
        reasons: tuple[str, ...] = (),
        reported_usage: dict[str, Any] | None = None,
    ) -> CodexUsageRecord:
        self._require_run(run_id)
        if policy_level not in range(0, 5):
            raise ValueError("policy_level must be between 0 and 4")
        if invocation_count < 0:
            raise ValueError("invocation_count cannot be negative")
        record = CodexUsageRecord(
            id=_id(),
            run_id=run_id,
            policy_level=policy_level,
            invocation_count=invocation_count,
            reasons=reasons,
            reported_usage=dict(reported_usage or {}),
        )
        self.codex_usage.append(record)
        return record

    def _require_project(self, project_id: str) -> ProjectRecord:
        try:
            return self.projects[project_id]
        except KeyError as exc:
            raise KeyError(f"unknown project: {project_id}") from exc

    def _require_task(self, task_id: str) -> TaskRecord:
        try:
            return self.tasks[task_id]
        except KeyError as exc:
            raise KeyError(f"unknown task: {task_id}") from exc

    def _require_run(self, run_id: str) -> RunRecord:
        try:
            return self.runs[run_id]
        except KeyError as exc:
            raise KeyError(f"unknown run: {run_id}") from exc
