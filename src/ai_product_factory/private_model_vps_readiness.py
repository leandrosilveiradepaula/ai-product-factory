"""No-model VPS readiness for Factory -> wg-ibm -> SQL-InfoDive.

Never claims a run, executes SQL, reads a bearer value, or calls a model.
An explicit SQL work queue with durable CAS is NOT yet provisioned.
"""
from __future__ import annotations
import os
import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from .private_chat_provider import PrivateChatConfig, PrivateModelError, SECRET_ENV
from .private_model_metering import PrivatePricing
from .private_model_vps_route import PrivateVpsRouteError, verify_existing_vps_route

_SHA = re.compile(r"[a-f0-9]{40}\Z")


@dataclass(frozen=True)
class VpsSqlReadiness:
    code: str
    network: str
    secret: str
    price: str
    budget: str
    worker: str = "not_provisioned"

    def receipt(self) -> dict:
        return {
            "schema": "factory-vps-sql-infodive-readiness-v1",
            "provider": "infodive_ibm_cloud",
            "status": "blocked",
            "code": self.code,
            "network": self.network,
            "secret": self.secret,
            "price": self.price,
            "budget": self.budget,
            "worker": self.worker,
            "model_invoked": False,
            "run_claimed": False,
            "sql_executed": False,
        }


def local_checkout_sha() -> str | None:
    try:
        p = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        result = p.stdout.strip()
        if p.returncode == 0 and _SHA.fullmatch(result):
            return result
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def assess(
    env: Mapping[str, str] | None = None, *,
    head: str | None = None,
    route: Callable[..., object] = verify_existing_vps_route,
    capacity: Callable[[], object] | None = None,
    tcp: bool = False,
) -> VpsSqlReadiness:
    src = os.environ if env is None else env
    expected = src.get("FACTORY_SQL_INFODIVE_WORKER_SHA", "")
    code = "verified" if _SHA.fullmatch(expected) and expected == head else "blocked"
    network = "blocked"
    if src.get("FACTORY_SQL_INFODIVE_BASE_URL"):
        try:
            config = PrivateChatConfig(
                base_url=src["FACTORY_SQL_INFODIVE_BASE_URL"],
                model_id=src.get("FACTORY_SQL_INFODIVE_MODEL", ""),
                host_header=src.get("FACTORY_SQL_INFODIVE_HTTP_HOST") or None,
                allow_private_http=src.get("FACTORY_SQL_INFODIVE_ALLOW_PRIVATE_HTTP") == "true",
            )
            route(config.base_url,
                  interface=src.get("FACTORY_SQL_INFODIVE_WG_INTERFACE", "wg-ibm"),
                  tcp=tcp)
            network = "verified"
        except (PrivateModelError, PrivateVpsRouteError, OSError):
            pass

    # Presence is not remote authentication validation. Never return a value.
    secret = "configured" if bool(src.get(SECRET_ENV)) else "missing"
    try:
        PrivatePricing.from_env(src)
        price = "approved"
    except (PrivateModelError, TypeError, ValueError):
        price = "unapproved"
    budget = "unverified"
    if capacity is not None and code == "verified" and network == "verified" and price == "approved":
        try:
            policy = capacity()
            reserve = getattr(policy, "reserve_usd", None)
            if not isinstance(reserve, Decimal) or reserve <= 0:
                raise ValueError
            budget = "available"
        except (PermissionError, RuntimeError, ValueError, OSError):
            budget = "blocked"
    # The lane MUST remain unprovisioned: no service-role-only SQL claim RPC,
    # lineage-bound authorization, durable lease and completion receipts yet.
    return VpsSqlReadiness(code, network, secret, price, budget)
