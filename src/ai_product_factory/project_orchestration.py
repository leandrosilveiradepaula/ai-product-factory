from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .control_plane import ControlPlaneStore, ProjectRecord, RunRecord, TaskRecord


class BootstrapStage(StrEnum):
    DISCOVERY = "discovery"
    SPECIFICATION = "specification"
    PLANNING = "planning"


@dataclass(frozen=True)
class BootstrapResult:
    project: ProjectRecord
    task: TaskRecord
    run: RunRecord
    stages: tuple[BootstrapStage, ...]


class ProjectBootstrapOrchestrator:
    """Creates the durable command boundary for the first autonomous product cycle.

    This intentionally does not call an LLM. It records the work to be executed so
    a runtime worker can claim it later without tying the Console request to a
    long-running model call.
    """

    def __init__(self, store: ControlPlaneStore) -> None:
        self.store = store

    def enqueue(self, project_key: str) -> BootstrapResult:
        project = self.store.get_project_by_key(project_key)
        if project is None:
            raise KeyError(f"unknown project: {project_key}")
        stages = (
            BootstrapStage.DISCOVERY,
            BootstrapStage.SPECIFICATION,
            BootstrapStage.PLANNING,
        )
        task = self.store.create_task(
            project_id=project.id,
            title="Bootstrap product discovery and planning",
            description="Execute discovery, product specification and implementation planning from the approved intake.",
            complexity="medium",
            acceptance_criteria=(
                "discovery context is structured",
                "product specification is versioned",
                "implementation plan is actionable",
            ),
        )
        run = self.store.create_run(task_id=task.id, execution_route="direct")
        self.store.record_tool_usage(
            run_id=run.id,
            tool_family="orchestrator",
            operation="enqueue_product_bootstrap",
            estimated_cost=0,
            metadata={"project_key": project_key, "stages": [s.value for s in stages]},
        )
        return BootstrapResult(project=project, task=task, run=run, stages=stages)
