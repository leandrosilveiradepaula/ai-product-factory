from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ManifestError(ValueError):
    pass


_REQUIRED_TOP_LEVEL = {
    "factory_version",
    "project",
    "autonomy",
    "codex",
    "commands",
    "environments",
    "gates",
    "integrations",
}


def load_manifest(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_manifest(data)
    return data


def validate_manifest(data: dict[str, Any]) -> None:
    missing = sorted(_REQUIRED_TOP_LEVEL - data.keys())
    if missing:
        raise ManifestError(f"missing top-level keys: {', '.join(missing)}")

    project = data["project"]
    for key in ("key", "name", "repository", "kind"):
        if not project.get(key):
            raise ManifestError(f"project.{key} is required")

    codex = data["codex"]
    minimum_level = codex.get("minimum_level")
    if not isinstance(minimum_level, int) or minimum_level not in range(0, 5):
        raise ManifestError("codex.minimum_level must be an integer from 0 to 4")

    max_calls = codex.get("max_calls_per_task")
    if not isinstance(max_calls, int) or max_calls < 0:
        raise ManifestError("codex.max_calls_per_task must be a non-negative integer")

    if "prod" in data["environments"] and not data["autonomy"].get("production_requires_human", True):
        # Allowed in future versions, but v0.1 intentionally refuses silent prod autonomy.
        raise ManifestError("v0.1 requires autonomy.production_requires_human=true when prod exists")
