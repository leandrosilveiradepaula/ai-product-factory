"""Explicitly metered SQL-InfoDive adapter.

Unconfigured models are NOT free by default. An independently approved cost
basis, Control Plane capacity and durable reservation are mandatory. This is
not activated by Product Stage, Direct or Codex entrypoints.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Protocol

from .model_executor import ModelExecutor, ModelProvider, ModelRequest, ModelResult
from .private_chat_provider import build_sql_infodive_provider, PrivateModelError

FAMILY = "model"
PROVIDER = "infodive_ibm_cloud"


class UsageLedger(Protocol):
    def record_tool_usage(self, *, run_id: str, tool_family: str, operation: str,
                          usage_units: float, estimated_cost: float, metadata: dict): ...
    def update_tool_usage(self, usage_id, *, operation: str, usage_units: float,
                          estimated_cost: float | None, metadata: dict): ...


class PrivatePricing:
    def __init__(self, input_usd_per_million: Decimal,
                 output_usd_per_million: Decimal) -> None:
        for value in (input_usd_per_million, output_usd_per_million):
            if not value.is_finite() or value < 0 or value > 10000:
                raise PrivateModelError("private model price invalid")
        self.input_rate = input_usd_per_million
        self.output_rate = output_usd_per_million

    @classmethod
    def from_env(cls, source: Mapping[str, str] | None = None) -> "PrivatePricing":
        env = os.environ if source is None else source
        if env.get("FACTORY_SQL_INFODIVE_PRICING_APPROVED") != "true":
            raise PrivateModelError("private model pricing not approved")
        rates = []
        for name in ("FACTORY_SQL_INFODIVE_INPUT_USD_PER_MILLION",
                     "FACTORY_SQL_INFODIVE_OUTPUT_USD_PER_MILLION"):
            raw = env.get(name)
            try:
                if raw is None or raw.strip() == "":
                    raise ValueError
                value = Decimal(raw)
            except (ValueError, InvalidOperation, AttributeError):
                raise PrivateModelError("private model pricing incomplete") from None
            rates.append(value)
        return cls(*rates)

    def cost(self, prompt_tokens: int, completion_tokens: int) -> Decimal:
        if not all(isinstance(n, int) and not isinstance(n, bool) and n >= 0
                   for n in (prompt_tokens, completion_tokens)):
            raise PrivateModelError("private model token usage unavailable")
        return (self.input_rate * prompt_tokens +
                self.output_rate * completion_tokens) / Decimal(1_000_000)


class MeteredPrivateProvider:
    """One call, one pre-reservation, exactly one final status receipt."""

    def __init__(self, underlying: ModelProvider, pricing: PrivatePricing,
                 *, store: UsageLedger | None = None,
                 reserve: Decimal | None = None) -> None:
        self.underlying = underlying
        self.pricing = pricing
        self.store = store
        self.reserve = reserve

    def execute(self, req: ModelRequest) -> ModelResult:
        if not req.run_id:
            raise PrivateModelError("private model requires durable run_id")
        # A failed local route is not a model call. Fail before creating
        # a paid-cost reservation or marking exposure as unknown.
        verify_route = getattr(self.underlying, "verify_route", None)
        if callable(verify_route):
            verify_route()
        if self.reserve is None:
            from .primary_cost_config import require_primary_cost_capacity
            amount = require_primary_cost_capacity().reserve_usd
        else:
            # Injection is intended for offline tests only. Production callers
            # must not set reserve and must use the live primary policy.
            amount = self.reserve
        if amount <= 0:
            raise PrivateModelError("private model reservation invalid")
        if self.store is None:
            from .supabase_store import SupabaseControlPlaneStore
            ledger = SupabaseControlPlaneStore()
        else:
            ledger = self.store
        receipt = ledger.record_tool_usage(
            run_id=req.run_id, tool_family=FAMILY,
            operation="private_sql_reserved", usage_units=0.0,
            estimated_cost=float(amount),
            metadata={"provider": PROVIDER, "status": "reserved",
                      "reserve_usd": str(amount)},
        )
        try:
            result = self.underlying.execute(req)
            usage = result.usage
            if not isinstance(usage, dict) or not result.model:
                raise PrivateModelError("private model token usage unavailable")
            input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
            if (not isinstance(input_tokens, (float, int)) or
                    not isinstance(output_tokens, (float, int)) or
                    not float(input_tokens).is_integer() or
                    not float(output_tokens).is_integer() or
                    min(input_tokens, output_tokens) < 0):
                raise PrivateModelError("private model token usage unavailable")
            total = int(input_tokens) + int(output_tokens)
            actual = self.pricing.cost(int(input_tokens), int(output_tokens))
        except Exception:
            # Unknown financial exposure blocks future paid claims.
            ledger.update_tool_usage(
                receipt.id, operation="private_sql_cost_unknown",
                usage_units=0.0, estimated_cost=None,
                metadata={"provider": PROVIDER, "status": "cost_unknown"},
            )
            raise
        if actual > amount:
            ledger.update_tool_usage(
                receipt.id, operation="private_sql_over_reserve",
                usage_units=float(total), estimated_cost=float(actual),
                metadata={"provider": PROVIDER, "model": result.model,
                          "status": "over_reserve"},
            )
            raise PrivateModelError("private model cost exceeded reservation")
        ledger.update_tool_usage(
            receipt.id, operation="private_sql_completed",
            usage_units=float(total), estimated_cost=float(actual),
            metadata={"provider": PROVIDER, "model": result.model,
                      "status": "completed", "input_tokens": int(input_tokens),
                      "output_tokens": int(output_tokens),
                      "cost_usd": str(actual),
                      "output_limit_reached": result.output_limit_reached,
                      "output_truncated": result.output_truncated},
        )
        return result


def build_guarded_sql_infodive_executor(*, env: Mapping[str, str] | None = None,
                                       transport=None, ledger=None,
                                       test_reserve: Decimal | None = None) -> ModelExecutor:
    """Construct a SQL-specialist executor only after explicit enablement.

    Does not register or activate any Factory job. No network/model call here.
    A SQL-specific authorized caller must still be developed and verified.
    """
    pricing = PrivatePricing.from_env(env)
    provider = build_sql_infodive_provider(env=env, transport=transport)
    return ModelExecutor(primary=MeteredPrivateProvider(
        provider, pricing, store=ledger, reserve=test_reserve,
    ))
