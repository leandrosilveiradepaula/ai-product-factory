from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any


_ALLOWED_FILES = {
    ".factory/product.json",
    ".factory/architecture.json",
    ".factory/current-state.json",
}


@dataclass(frozen=True)
class ProjectMemory:
    product: dict[str, Any]
    architecture: dict[str, Any]
    current_state: dict[str, Any]
    decisions: tuple[dict[str, Any], ...] = ()

    def validate(self) -> None:
        if not self.product.get("name"):
            raise ValueError("product.name is required")
        if not self.current_state.get("stage"):
            raise ValueError("current_state.stage is required")
        for decision in self.decisions:
            if not decision.get("id") or not decision.get("decision"):
                raise ValueError("each decision requires id and decision")

    def to_files(self) -> dict[str, str]:
        self.validate()
        files = {
            ".factory/product.json": _dump(self.product),
            ".factory/architecture.json": _dump(self.architecture),
            ".factory/current-state.json": _dump(self.current_state),
        }
        for decision in self.decisions:
            decision_id = _safe_id(str(decision["id"]))
            files[f".factory/decisions/{decision_id}.json"] = _dump(decision)
        return files


def _dump(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _safe_id(value: str) -> str:
    if not value or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in value):
        raise ValueError("decision id contains unsafe characters")
    return value


def parse_memory(files: dict[str, str]) -> ProjectMemory:
    unknown = [
        path for path in files
        if path not in _ALLOWED_FILES and not path.startswith(".factory/decisions/")
    ]
    if unknown:
        raise ValueError(f"unsupported memory paths: {', '.join(sorted(unknown))}")

    def load(path: str, default: dict[str, Any]) -> dict[str, Any]:
        raw = files.get(path)
        return default if raw is None else json.loads(raw)

    decisions = []
    for path, raw in sorted(files.items()):
        p = PurePosixPath(path)
        if str(p).startswith(".factory/decisions/"):
            decisions.append(json.loads(raw))

    memory = ProjectMemory(
        product=load(".factory/product.json", {}),
        architecture=load(".factory/architecture.json", {}),
        current_state=load(".factory/current-state.json", {}),
        decisions=tuple(decisions),
    )
    memory.validate()
    return memory


def update_current_state(
    memory: ProjectMemory,
    *,
    stage: str,
    head_sha: str | None = None,
    status: str | None = None,
) -> ProjectMemory:
    state = dict(memory.current_state)
    state["stage"] = stage
    if head_sha is not None:
        state["head_sha"] = head_sha
    if status is not None:
        state["status"] = status
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated = ProjectMemory(
        product=dict(memory.product),
        architecture=dict(memory.architecture),
        current_state=state,
        decisions=memory.decisions,
    )
    updated.validate()
    return updated


def latest_decision(memory: ProjectMemory, decision_type: str) -> dict[str, Any] | None:
    matches = [d for d in memory.decisions if d.get("type") == decision_type]
    if not matches:
        return None
    return sorted(matches, key=lambda d: str(d.get("created_at", "")))[-1]
