from __future__ import annotations

from dataclasses import dataclass

from .control_plane import ControlPlaneStore, ProjectRecord, RunRecord, TaskRecord
from .models import ExecutionDecision, RiskProfile, TaskProfile
from .orchestrator import decide_execution


@dataclass(frozen=True)
class StartedExecution:
    project: ProjectRecord
    task: TaskRecord
    run: RunRecord
    decision: ExecutionDecision


class FactoryRuntime:
    """Coordinates task routing and persists the resulting execution evidence."""

    def __init__(self, store: ControlPlaneStore, *, codex_minimum_level: int = 3) -> None:
        self.store = store
        self.codex_minimum_level = codex_minimum_level

    def start_task(
        self,
        *,
        project_key: str,
        title: str,
        task_profile: TaskProfile,
        risk: RiskProfile | None = None,
        description: str = "",
        acceptance_criteria: tuple[str, ...] = (),
        source_commit: str | None = None,
        branch_name: str | None = None,
    ) -> StartedExecution:
        project = self.store.get_project_by_key(project_key)
        if project is None:
            raise KeyError(f"unknown project_key: {project_key}")

        decision = decide_execution(
            task_profile,
            risk,
            codex_minimum_level=self.codex_minimum_level,
        )
        task = self.store.create_task(
            project_id=project.id,
            title=title,
            description=description,
            complexity=task_profile.complexity.value,
            acceptance_criteria=acceptance_criteria,
        )
        self.store.update_task_status(task.id, "in_progress")
        run = self.store.create_run(
            task_id=task.id,
            execution_route=decision.route.value,
            source_commit=source_commit,
            branch_name=branch_name,
        )
        run = self.store.update_run_status(run.id, "in_progress")

        self.store.record_decision(
            project_id=project.id,
            task_id=task.id,
            decision_type="execution_route",
            decision={
                "route": decision.route.value,
                "codex_level": decision.codex.level,
                "codex_used": decision.codex.should_use,
                "human_gate_required": decision.human_gate_required,
                "gate_reasons": list(decision.gate_reasons),
            },
            decided_by="ai-product-factory",
        )
        self.store.record_codex_usage(
            run_id=run.id,
            policy_level=decision.codex.level,
            invocation_count=0,
            reasons=decision.codex.reasons,
        )

        return StartedExecution(project=project, task=task, run=run, decision=decision)

    def record_tool(
        self,
        run_id: str,
        *,
        tool_family: str,
        operation: str,
        usage_units: float | None = None,
        estimated_cost: float | None = None,
    ) -> None:
        self.store.record_tool_usage(
            run_id=run_id,
            tool_family=tool_family,
            operation=operation,
            usage_units=usage_units,
            estimated_cost=estimated_cost,
        )

    def finish_task(
        self,
        execution: StartedExecution,
        *,
        status: str,
        candidate_commit: str | None = None,
    ) -> None:
        self.store.update_run_status(execution.run.id, status, candidate_commit=candidate_commit)
        task_status = "completed" if status in {"merged", "released", "completed"} else status
        self.store.update_task_status(execution.task.id, task_status)
