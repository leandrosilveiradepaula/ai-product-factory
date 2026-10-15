"""Authoritative Primary cost policy loaded from the privileged Control Plane.

There is no environment-variable budget fallback. A missing migration, bad
record, expired broker token or unmeterable paid ledger fails closed before
paid work can be claimed. Do not cache the policy across paid calls: an admin
may lower the ceiling while a worker is running.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import urllib.error
import urllib.request

from .cost_policy import require_cost_ceiling
from .supabase_server import resolve_supabase_server_config


@dataclass(frozen=True)
class PrimaryCostPolicy:
    budget_usd: Decimal
    reserve_usd: Decimal
    version: int


def _amount(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise RuntimeError("invalid primary cost policy " + field)
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise RuntimeError("invalid primary cost policy " + field) from None
    if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal("0.0001")):
        raise RuntimeError("invalid primary cost policy " + field)
    return amount


def parse_primary_cost_policy(payload: object) -> PrimaryCostPolicy:
    if not isinstance(payload, list) or len(payload) != 1:
        raise RuntimeError("primary cost policy missing or duplicated")
    row = payload[0]
    if not isinstance(row, dict) or row.get("policy_key") != "primary":
        raise RuntimeError("primary cost policy identity mismatch")
    budget = _amount(row.get("budget_usd"), field="budget")
    reserve = _amount(row.get("reserve_usd"), field="reserve")
    version = row.get("version")
    if (not isinstance(version, int) or isinstance(version, bool)
            or version < 1 or budget > Decimal("100000") or reserve > budget):
        raise RuntimeError("primary cost policy out of range")
    return PrimaryCostPolicy(budget, reserve, version)


class SupabasePrimaryCostPolicyReader:
    def __init__(self, *, url: str | None = None,
                 secret_key: str | None = None,
                 service_role_key: str | None = None) -> None:
        config = resolve_supabase_server_config(
            url=url, secret_key=secret_key, service_role_key=service_role_key,
        )
        self.url, self.headers = config.url, config.headers

    def read(self) -> PrimaryCostPolicy:
        request = urllib.request.Request(
            self.url + "/rest/v1/factory_primary_cost_policy"
            "?select=policy_key,budget_usd,reserve_usd,version"
            "&policy_key=eq.primary&limit=2",
            headers=self.headers,
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError("primary cost policy read unavailable") from exc
        try:
            return parse_primary_cost_policy(json.loads(raw))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("primary cost policy response malformed") from exc


def require_primary_cost_capacity(*, policy_reader=None, health_reader=None) -> PrimaryCostPolicy:
    """Check current persisted policy and complete paid ledger, before claiming.

    This is not an atomic reservation across concurrent workers. Existing
    metered provider ledger writes remain mandatory and concurrency hardening
    must not be inferred from this preflight.
    """
    from .supabase_operational_health import SupabaseOperationalHealthReader
    policy = (policy_reader or SupabasePrimaryCostPolicyReader()).read()
    health = (health_reader or SupabaseOperationalHealthReader()).read(budget=policy.budget_usd)
    if health.unknown_cost_events > 0:
        raise PermissionError("paid usage ledger contains unknown-cost events")
    require_cost_ceiling(
        budget=policy.budget_usd,
        known_spend=health.known_cost,
        reserved_cost=policy.reserve_usd,
        strict=True,
    )
    return policy
