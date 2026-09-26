from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AdapterReadiness:
    enabled: bool
    configured: bool
    ready: bool
    missing: tuple[str, ...]


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() == "true"


def _evaluate(enabled_name: str, required: tuple[str, ...]) -> AdapterReadiness:
    enabled = _truthy(enabled_name)
    missing = tuple(name for name in required if not os.getenv(name, "").strip())
    configured = not missing
    return AdapterReadiness(enabled=enabled, configured=configured, ready=enabled and configured, missing=missing)


def vercel_preview_readiness() -> AdapterReadiness:
    return _evaluate(
        "FACTORY_VERCEL_PREVIEW_ENABLED",
        (
            "VERCEL_TOKEN",
            "FACTORY_VERCEL_TEAM_ID",
            "FACTORY_VERCEL_PROJECT_NAME",
            "FACTORY_VERCEL_GITHUB_ORG",
            "FACTORY_VERCEL_GITHUB_REPO",
        ),
    )


def github_alerts_readiness() -> AdapterReadiness:
    return _evaluate(
        "FACTORY_GITHUB_ALERTS_ENABLED",
        ("GITHUB_TOKEN", "FACTORY_ALERTS_GITHUB_REPOSITORY"),
    )
