from __future__ import annotations

import os
from decimal import Decimal
from typing import Protocol

from .model_executor import ModelProvider, ModelRequest, ModelResult
from .openai_costs import estimate_openai_text_cost_usd
from .runtime_auth import RuntimeAuthResolver
from .supabase_store import SupabaseControlPlaneStore


class UsageStore(Protocol):
    def record_tool_usage(self, *, run_id: str, tool_family: str, operation: str | None = None, usage_units: float | None = None, estimated_cost: float | None = None, metadata: dict | None = None): ...
    def update_tool_usage(self, usage_id: str | int, *, operation: str | None = None, usage_units: float | None = None, estimated_cost: float | None = None, metadata: dict | None = None): ...


class MeteredPrimaryProvider:
    """Wraps a paid primary provider with a conservative pre-call reservation.

    The reservation is persisted before the provider call. If the call or final
    ledger update fails, the reservation remains as known spend, which is safer
    than silently losing paid usage from the Control Plane.
    """

    def __init__(
        self,
        provider: ModelProvider,
        *,
        store: UsageStore | None = None,
        reserve_usd: Decimal | None = None,
    ) -> None:
        self.provider = provider
        self.store = store or SupabaseControlPlaneStore()
        raw = os.getenv("FACTORY_MODEL_RESERVE_USD", "").strip()
        self.reserve_usd = reserve_usd if reserve_usd is not None else (Decimal(raw) if raw else None)
        if self.reserve_usd is None or self.reserve_usd <= 0:
            raise ValueError("FACTORY_MODEL_RESERVE_USD must be a positive amount")

    def execute(self, request: ModelRequest) -> ModelResult:
        if not request.run_id:
            raise ValueError("paid primary request requires run_id for cost ledger")
        auth = RuntimeAuthResolver().resolve_primary_api()
        reservation = self.store.record_tool_usage(
            run_id=request.run_id,
            tool_family="openai",
            operation="model_call_reserved",
            usage_units=0,
            estimated_cost=float(self.reserve_usd),
            metadata={
                "status": "reserved",
                "auth_kind": auth.kind.value,
                "reserve_usd": str(self.reserve_usd),
            },
        )
        try:
            result = self.provider.execute(request)
        except Exception:
            # Keep the reservation as conservative known spend if the provider
            # outcome cannot be priced reliably.
            raise

        if not result.model:
            raise RuntimeError("paid provider returned no model identity")
        cost = estimate_openai_text_cost_usd(model=result.model, usage=result.usage)
        if cost > self.reserve_usd:
            raise RuntimeError(
                f"actual provider cost exceeded reserved cost: {cost} > {self.reserve_usd}"
            )
        usage = result.usage or {}
        total_tokens = float(usage.get("total_tokens", 0))
        self.store.update_tool_usage(
            reservation.id,
            operation="model_call",
            usage_units=total_tokens,
            estimated_cost=float(cost),
            metadata={
                "status": "completed",
                "provider": "openai",
                "model": result.model,
                "auth_kind": auth.kind.value,
                "provider_ref": result.provider_ref,
                "input_tokens": int(usage.get("input_tokens", 0)),
                "cached_input_tokens": int(usage.get("cached_input_tokens", 0)),
                "output_tokens": int(usage.get("output_tokens", 0)),
                "total_tokens": int(usage.get("total_tokens", 0)),
                "reserve_usd": str(self.reserve_usd),
                "actual_cost_usd": str(cost),
            },
        )
        return result
