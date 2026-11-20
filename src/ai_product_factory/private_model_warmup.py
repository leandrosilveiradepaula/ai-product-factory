"""Bounded on-demand warmup of the existing private IBM model.

Only before a queued Product Stage run, with approved zero marginal rates.
Never claims work or changes Factory runtime/release policy.
"""
from __future__ import annotations
import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from decimal import Decimal
from uuid import UUID

from .private_chat_provider import PrivateChatConfig
from .private_model_metering import PrivatePricing
from .private_model_vps_route import verify_existing_vps_route
from .primary_cost_config import require_primary_cost_capacity
from .supabase_server import resolve_supabase_server_config


class WarmupBlocked(RuntimeError):
    """Sanitized warmup failure; never include a secret or remote body."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _http():
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect,
    )


def has_queued_product_run(env: Mapping[str, str]) -> bool:
    """Read only the existing durable run queue. No run claim, no model."""
    cfg = resolve_supabase_server_config(
        url=env.get("SUPABASE_URL"),
        secret_key=env.get("SUPABASE_SECRET_KEY"),
        service_role_key=env.get("SUPABASE_SERVICE_ROLE_KEY"),
    )
    if (not cfg.url.startswith("https://") or
            any(x in cfg.url for x in ("@", "?", "#"))):
        raise WarmupBlocked("control-plane destination invalid")
    req = urllib.request.Request(
        cfg.url + "/rest/v1/factory_runs?select=id,task:factory_tasks!inner(status)"
        "&status=in.(created,queued)&task.status=eq.queued&limit=1",
        headers=cfg.headers, method="GET",
    )
    try:
        with _http().open(req, timeout=20) as response:
            if response.status != 200:
                raise ValueError
            raw = response.read(4097)
        if len(raw) > 4096:
            raise ValueError
        rows = json.loads(raw)
        if not isinstance(rows, list) or len(rows) > 1:
            raise ValueError
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                raise ValueError
            UUID(row["id"])
        return bool(rows)
    except Exception:
        raise WarmupBlocked("control-plane queue unavailable") from None


def _post(config: PrivateChatConfig, key: str) -> tuple[int, dict]:
    """No HTTP socket timeout. The systemd process watchdog is mandatory."""
    req = urllib.request.Request(
        config.endpoint,
        data=json.dumps({
            "model": config.model_id,
            "messages": [{"role": "user", "content": "Reply exactly OK."}],
            "temperature": 0, "max_tokens": 16, "stream": False,
        }).encode("utf-8"),
        headers={
            "Host": config.host_header or "",
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with _http().open(req, timeout=None) as response:
            code = response.status
            body = response.read(200001)
        if len(body) > 200000:
            raise WarmupBlocked("model output too large")
        return code, json.loads(body)
    except WarmupBlocked:
        raise
    except urllib.error.HTTPError as exc:
        raise WarmupBlocked(
            "model authentication denied" if exc.code in (401, 403)
            else "model endpoint unavailable"
        ) from None
    except Exception:
        raise WarmupBlocked("model warmup transport unavailable") from None


def warmup_if_pending(
    env: Mapping[str, str], *,
    pending: Callable[[Mapping[str, str]], bool] = has_queued_product_run,
    route: Callable[..., object] = verify_existing_vps_route,
    capacity: Callable[[], object] = require_primary_cost_capacity,
    request: Callable[[PrivateChatConfig, str], tuple[int, dict]] = _post,
) -> dict:
    if (
        env.get("FACTORY_PRIMARY_MODEL_PROVIDER") != "infodive_ibm_cloud"
        or env.get("FACTORY_PRIMARY_MODEL_ENABLED") != "true"
        or env.get("FACTORY_INFODIVE_VPS_WORKER_ENABLED") != "true"
    ):
        raise WarmupBlocked("private model worker disabled")
    # No warmup and no bearer access during idle scheduler polling.
    if not pending(env):
        return {"schema": "factory-ibm-vps-warmup-v1",
                "status": "idle", "model_invoked": False, "run_claimed": False}
    try:
        config = PrivateChatConfig.from_env(env)
        pricing = PrivatePricing.from_env(env)
        # Never perform an unreserved paid call just to warm a model.
        if pricing.input_rate != Decimal("0") or pricing.output_rate != Decimal("0"):
            raise WarmupBlocked("nonzero model pricing prohibits warmup")
        capacity()
        route(config.base_url,
              interface=env.get("FACTORY_SQL_INFODIVE_WG_INTERFACE", "wg-ibm"),
              tcp=True)
        key = env.get("FACTORY_SQL_INFODIVE_API_KEY")
        if (not isinstance(key, str) or not key
                or any(ord(c) < 33 or ord(c) > 126 for c in key)):
            raise WarmupBlocked("model bearer unavailable")
    except WarmupBlocked:
        raise
    except Exception:
        raise WarmupBlocked("private model readiness failed") from None
    try:
        status, body = request(config, key)
        if status != 200 or not isinstance(body, dict):
            raise ValueError
        content = body["choices"][0]["message"]["content"]
        usage = body["usage"]
        tokens_in = usage["prompt_tokens"]
        tokens_out = usage["completion_tokens"]
        if (
            not isinstance(content, str) or not content.strip()
            or type(tokens_in) is not int or tokens_in < 0
            or type(tokens_out) is not int or tokens_out < 0
        ):
            raise ValueError
    except Exception:
        raise WarmupBlocked("model warmup output unverifiable") from None
    return {
        "schema": "factory-ibm-vps-warmup-v1",
        "status": "warmed", "model_invoked": True, "run_claimed": False,
        "prompt_tokens": tokens_in, "completion_tokens": tokens_out,
        "marginal_cost_usd": "0",
    }
