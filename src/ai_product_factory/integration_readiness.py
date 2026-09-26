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
        ("VERCEL_TOKEN",),
    )


def github_vercel_preview_readiness() -> AdapterReadiness:
    return _evaluate(
        "FACTORY_VERCEL_PREVIEW_ENABLED",
        ("GITHUB_TOKEN",),
    )


def github_alerts_readiness() -> AdapterReadiness:
    return _evaluate(
        "FACTORY_GITHUB_ALERTS_ENABLED",
        ("GITHUB_TOKEN", "FACTORY_ALERTS_GITHUB_REPOSITORY"),
    )

def browser_evidence_readiness() -> AdapterReadiness:
    return _evaluate(
        "FACTORY_BROWSER_EVIDENCE_ENABLED",
        ("FACTORY_BROWSER_EVIDENCE_COMMAND_JSON",),
    )


def verified_preview_readiness(mode: str = "api") -> AdapterReadiness:
    if mode == "api":
        provider=vercel_preview_readiness()
    elif mode == "github":
        provider=github_vercel_preview_readiness()
    else:
        raise ValueError(f"unsupported preview readiness mode: {mode}")
    browser=browser_evidence_readiness()
    missing=tuple(dict.fromkeys((*provider.missing,*browser.missing)))
    enabled=provider.enabled and browser.enabled
    configured=provider.configured and browser.configured
    return AdapterReadiness(enabled=enabled,configured=configured,ready=enabled and configured,missing=missing)
