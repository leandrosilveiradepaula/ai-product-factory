from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class WorkStatus(StrEnum):
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class WorkItem:
    run_id: str
    task_id: str
    project_id: str
    project_key: str
    stages: tuple[str, ...]
    context: dict = field(default_factory=dict)


@dataclass(frozen=True)
class StageEvidence:
    stage: str
    status: str
    output: dict


@dataclass(frozen=True)
class WorkResult:
    status: WorkStatus
    evidence: tuple[StageEvidence, ...]
    error: str | None = None


class RuntimeQueue(Protocol):
    def claim_next(self, worker_id: str) -> WorkItem | None: ...
    def record_stage(self, item: WorkItem, evidence: StageEvidence) -> None: ...
    def complete(self, item: WorkItem) -> None: ...
    def fail(self, item: WorkItem, error: str) -> None: ...


class StageHandler(Protocol):
    def execute(self, item: WorkItem, stage: str) -> dict: ...


class DeterministicBootstrapHandler:
    """Offline bootstrap handler used until a model-backed stage is configured."""
    def execute(self, item: WorkItem, stage: str) -> dict:
        if stage not in {"discovery", "specification", "planning"}:
            raise ValueError(f"unsupported bootstrap stage: {stage}")
        return {"stage": stage, "project_key": item.project_key, "mode": "deterministic", "requires_model": True}


class RuntimeWorker:
    def __init__(self, *, queue: RuntimeQueue, handler: StageHandler, worker_id: str) -> None:
        self.queue = queue
        self.handler = handler
        self.worker_id = worker_id

    def run_once(self) -> WorkResult | None:
        item = self.queue.claim_next(self.worker_id)
        if item is None:
            return None
        evidence: list[StageEvidence] = []
        try:
            for stage in item.stages:
                output = self.handler.execute(item, stage)
                ev = StageEvidence(stage=stage, status="completed", output=output)
                self.queue.record_stage(item, ev)
                evidence.append(ev)
            self.queue.complete(item)
            return WorkResult(WorkStatus.COMPLETED, tuple(evidence))
        except Exception as exc:
            self.queue.fail(item, str(exc))
            return WorkResult(WorkStatus.FAILED, tuple(evidence), str(exc))
