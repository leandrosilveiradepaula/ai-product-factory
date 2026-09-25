from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ModelUsage:
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cost_usd: Decimal | None = None
    auth_kind: str = "unknown"

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class UsageSummary:
    calls: int
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    known_cost_usd: Decimal
    calls_without_cost: int


def summarize_usage(entries: list[ModelUsage]) -> UsageSummary:
    return UsageSummary(
        calls=len(entries),
        input_tokens=sum(x.input_tokens for x in entries),
        output_tokens=sum(x.output_tokens for x in entries),
        cached_input_tokens=sum(x.cached_input_tokens for x in entries),
        known_cost_usd=sum(
            (x.cost_usd for x in entries if x.cost_usd is not None),
            Decimal("0"),
        ),
        calls_without_cost=sum(x.cost_usd is None for x in entries),
    )


def usage_from_openai(
    *,
    model: str,
    usage: dict[str, float] | None,
    auth_kind: str,
    cost_usd: Decimal | None = None,
) -> ModelUsage:
    usage = usage or {}
    return ModelUsage(
        provider="openai",
        model=model,
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
        cached_input_tokens=int(usage.get("cached_input_tokens", 0)),
        cost_usd=cost_usd,
        auth_kind=auth_kind,
    )
