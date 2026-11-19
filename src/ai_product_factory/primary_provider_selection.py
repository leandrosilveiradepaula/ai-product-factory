"""Optional GENERAL IBM Cloud model over the existing native Factory VPS.

SQL-InfoDive is a historical DISPLAY NAME, not SQL-only specialization.
Model requests may be discovery, planning or implementation. As with OpenAI,
Factory governance, prompts, quality evaluations, paid ledger and human release
rules remain applicable. This never uses n8n, LangGraph or GitHub-hosted VPN.
"""
from __future__ import annotations
import os
from collections.abc import Mapping
from typing import Callable

from .model_executor import ModelExecutor

OPENAI = "openai"
INFODIVE = "infodive_ibm_cloud"


def selected_primary_provider(env: Mapping[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    value = source.get("FACTORY_PRIMARY_MODEL_PROVIDER", OPENAI)
    if value not in (OPENAI, INFODIVE):
        raise PermissionError("unknown primary model provider")
    return value


def require_agent_provider_policy(profile: object, provider: str) -> None:
    """Reject a private-LLM Direct assignment owned by another provider."""
    if provider == OPENAI:
        return
    policy = getattr(profile, "model_policy", None)
    if (not isinstance(policy, dict) or policy.get("provider") != INFODIVE
            or policy.get("enabled") is not True):
        raise PermissionError("agent model policy does not authorize private provider")


def require_primary_provider_ready(
    env: Mapping[str, str] | None = None, *,
    local_head: Callable[[], str | None] | None = None,
    route_check: Callable[..., object] | None = None,
) -> str:
    """Fail before claim, reading a bearer, paid ledger write or model call."""
    source = os.environ if env is None else env
    provider = selected_primary_provider(source)
    if source.get("FACTORY_PRIMARY_MODEL_ENABLED") != "true":
        raise PermissionError("primary model disabled")
    if provider == OPENAI:
        from .runtime_auth import RuntimeAuthResolver, AuthKind
        auth = RuntimeAuthResolver().resolve_primary_api()
        if auth.kind not in (AuthKind.OPENAI_API_KEY, AuthKind.OPENAI_API_WIF):
            raise RuntimeError("official OpenAI API authentication unavailable")
        return provider

    if (source.get("GITHUB_ACTIONS", "").lower() == "true"
            or source.get("FACTORY_INFODIVE_VPS_WORKER_ENABLED") != "true"):
        raise PermissionError("private IBM model requires an enabled native VPS worker")
    from .private_chat_provider import PrivateChatConfig, SECRET_ENV
    from .private_model_metering import PrivatePricing
    from .private_model_vps_readiness import local_checkout_sha
    from .private_model_vps_route import PrivateVpsRouteError, verify_existing_vps_route
    expected = source.get("FACTORY_SQL_INFODIVE_WORKER_SHA", "")
    actual = (local_head or local_checkout_sha)()
    if (not isinstance(expected, str) or len(expected) != 40
            or any(c not in "0123456789abcdef" for c in expected)
            or expected != actual):
        raise PermissionError("native VPS model worker source SHA not verified")
    config = PrivateChatConfig.from_env(source)
    PrivatePricing.from_env(source)
    if not source.get(SECRET_ENV):
        raise PermissionError("dedicated Factory IBM Cloud credential missing")
    try:
        (route_check or verify_existing_vps_route)(
            config.base_url,
            interface=source.get("FACTORY_SQL_INFODIVE_WG_INTERFACE", "wg-ibm"),
            tcp=True,
        )
    except PrivateVpsRouteError:
        raise PermissionError("private IBM Cloud VPS route unavailable") from None
    return provider


def build_primary_model_executor() -> ModelExecutor:
    """Select one provider explicitly, never change it as a fallback."""
    provider = selected_primary_provider()
    if provider == OPENAI:
        from .metered_provider import MeteredPrimaryProvider
        from .openai_provider import OpenAIResponsesProvider
        return ModelExecutor(primary=MeteredPrimaryProvider(OpenAIResponsesProvider()))
    from .private_model_metering import build_guarded_sql_infodive_executor
    return build_guarded_sql_infodive_executor()
