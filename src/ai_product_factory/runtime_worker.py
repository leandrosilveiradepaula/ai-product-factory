from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from .product_stage_output_contract import (
    assert_executed_product_stage_output, PlanningNoActionableWork,
)


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
    execution_generation: int | None = None
    worker_id: str | None = None


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
    def assert_execution_epoch(self, item: WorkItem) -> None: ...


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
        if not isinstance(self.worker_id,str) or not self.worker_id.strip():
            raise ValueError("runtime worker identity is required")
        item = self.queue.claim_next(self.worker_id)
        if item is None:
            return None
        # Reject malformed claims before executing handlers or recording evidence.
        malformed = None
        if not isinstance(item.run_id,str) or not item.run_id.strip():
            malformed = "claimed run has invalid run identity"
        elif not isinstance(item.task_id,str) or not item.task_id.strip():
            malformed = "claimed run has invalid task identity"
        elif not isinstance(item.project_id,str) or not item.project_id.strip():
            malformed = "claimed run has invalid project identity"
        elif not isinstance(item.project_key,str) or not item.project_key.strip():
            malformed = "claimed run has invalid project key"
        elif not isinstance(item.stages,(tuple,list)):
            malformed = "claimed run has invalid stage container"
        elif not isinstance(item.context,dict):
            malformed = "claimed run has invalid context"
        elif item.execution_generation is not None and (
            isinstance(item.execution_generation,bool)
            or not isinstance(item.execution_generation,int)
            or item.execution_generation<0
        ):
            malformed = "claimed run has invalid execution generation"
        elif item.worker_id is not None and item.worker_id!=self.worker_id:
            malformed = "claimed run worker lease owner mismatch"
        elif item.worker_id is not None and (
            not isinstance(item.worker_id,str) or not item.worker_id.strip()
        ):
            malformed = "claimed run has invalid worker identity"
        elif not isinstance(item.stages,(tuple,list)) or not item.stages or not all(
            isinstance(stage,str) and stage.strip() for stage in item.stages
        ):
            malformed = "claimed run has no executable stages"
        elif len(item.stages)>32:
            malformed = "claimed run exceeds stage limit"
        elif any(len(stage)>128 for stage in item.stages):
            malformed = "claimed run has oversized stage name"
        elif any(stage!=stage.strip() for stage in item.stages):
            malformed = "claimed run has unnormalized stage name"
        elif len(item.stages)!=len(set(item.stages)):
            malformed = "claimed run has duplicate stages"
        if malformed is not None:
            checkpoint=getattr(self.queue,"assert_execution_epoch",None)
            if callable(checkpoint):
                try:
                    checkpoint(item)
                except Exception as exc:
                    return WorkResult(WorkStatus.FAILED,(),str(exc))
            try:
                self.queue.fail(item,malformed)
            except Exception:
                pass
            return WorkResult(WorkStatus.FAILED,(),malformed)
        evidence: list[StageEvidence] = []
        current_stage: str | None = None
        try:
            for stage in item.stages:
                current_stage = stage
                checkpoint = getattr(self.queue, "assert_execution_epoch", None)
                if callable(checkpoint):
                    checkpoint(item)
                recorder = getattr(self.queue, "record_stage_event", None)
                if callable(recorder):
                    recorder(item, stage, "started")
                output = self.handler.execute(item, stage)
                if not isinstance(output, dict):
                    raise ValueError("stage handler must return a mapping")
                if any(not isinstance(key,str) for key in output):
                    raise ValueError("stage handler output keys must be strings")
                assert_executed_product_stage_output(output)

                if callable(checkpoint):
                    checkpoint(item)
                ev = StageEvidence(stage=stage, status="completed", output=output)
                self.queue.record_stage(item, ev)
                evidence.append(ev)
                current_stage = None
            checkpoint = getattr(self.queue, "assert_execution_epoch", None)
            if callable(checkpoint):
                checkpoint(item)
            self.queue.complete(item)
            return WorkResult(WorkStatus.COMPLETED, tuple(evidence))
        except Exception as exc:
            # A revoked epoch must never be turned into a new write by error handling.
            # Check again because the project may have paused while the handler ran.
            checkpoint = getattr(self.queue, "assert_execution_epoch", None)
            if callable(checkpoint):
                try:
                    checkpoint(item)
                except Exception:
                    return WorkResult(WorkStatus.FAILED, tuple(evidence), str(exc))
            if current_stage is not None:
                recorded = False
                if current_stage == "planning" and isinstance(exc, PlanningNoActionableWork):
                    # Retain a bounded typed diagnostic without exposing the
                    # model response or converting failed work into success.
                    preserve = getattr(self.queue, "record_non_actionable_planning", None)
                    if callable(preserve):
                        try:
                            preserve(item)
                            recorded = True
                        except Exception:
                            pass
                recorder = getattr(self.queue, "record_stage_event", None)
                if not recorded and callable(recorder):
                    try:
                        recorder(item, current_stage, "failed")
                    except Exception:
                        # Do not mask the original handler failure.
                        pass
            try:
                self.queue.fail(item, str(exc))
            except Exception:
                # A concurrent pause may revoke the epoch between checks.
                pass
            return WorkResult(WorkStatus.FAILED, tuple(evidence), str(exc))
