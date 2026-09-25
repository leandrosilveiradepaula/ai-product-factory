from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class LifecycleStage(StrEnum):
    DISCOVERY = "discovery"
    SPECIFICATION = "specification"
    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    REVIEW = "review"
    VALIDATION = "validation"
    PREVIEW = "preview"
    HUMAN_GATE = "human_gate"
    RELEASE = "release"
    OPERATIONS = "operations"
    BLOCKED = "blocked"


class Complexity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


@dataclass(frozen=True)
class TaskProfile:
    complexity: Complexity = Complexity.LOW
    estimated_files: int = 1
    deep_debug: bool = False
    large_refactor: bool = False
    broad_repo_investigation: bool = False
    direct_tools_sufficient: bool = True
    repetitive_mechanical_change: bool = False
    user_requires_codex: bool = False


@dataclass(frozen=True)
class CodexDecision:
    level: int
    should_use: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskProfile:
    production_change: bool = False
    destructive_data_change: bool = False
    expands_sensitive_access: bool = False
    new_paid_service: bool = False
    material_requirement_change: bool = False


@dataclass
class ProjectState:
    project_key: str
    stage: LifecycleStage = LifecycleStage.DISCOVERY
    metadata: dict[str, Any] = field(default_factory=dict)
