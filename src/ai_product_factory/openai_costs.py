from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


LONG_CONTEXT_THRESHOLD = 272_000


@dataclass(frozen=True)
class TextTokenRates:
    input_per_million: Decimal
    cached_input_per_million: Decimal
    output_per_million: Decimal


SHORT_CONTEXT_RATES = {
    "gpt-5.6-luna": TextTokenRates(Decimal("0.20"), Decimal("0.02"), Decimal("1.20")),
    "gpt-5.6-terra": TextTokenRates(Decimal("2.00"), Decimal("0.20"), Decimal("12.00")),
    "gpt-5.6-sol": TextTokenRates(Decimal("4.00"), Decimal("0.40"), Decimal("20.00")),
}

LONG_CONTEXT_RATES = {
    "gpt-5.6-luna": TextTokenRates(Decimal("0.40"), Decimal("0.04"), Decimal("1.80")),
    "gpt-5.6-terra": TextTokenRates(Decimal("4.00"), Decimal("0.40"), Decimal("18.00")),
    "gpt-5.6-sol": TextTokenRates(Decimal("8.00"), Decimal("0.80"), Decimal("30.00")),
}


def estimate_openai_text_cost_usd(*, model: str, usage: dict[str, float] | None) -> Decimal:
    usage = usage or {}
    input_tokens = int(usage.get("input_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))
    cached_input_tokens = int(usage.get("cached_input_tokens", 0))
    if min(input_tokens, output_tokens, cached_input_tokens) < 0:
        raise ValueError("token usage cannot be negative")
    if cached_input_tokens > input_tokens:
        raise ValueError("cached input tokens cannot exceed input tokens")
    rates_by_model = LONG_CONTEXT_RATES if input_tokens > LONG_CONTEXT_THRESHOLD else SHORT_CONTEXT_RATES
    try:
        rates = rates_by_model[model]
    except KeyError as exc:
        raise ValueError(f"no approved pricing configured for model {model}") from exc

    uncached_input = input_tokens - cached_input_tokens
    return (
        Decimal(uncached_input) * rates.input_per_million
        + Decimal(cached_input_tokens) * rates.cached_input_per_million
        + Decimal(output_tokens) * rates.output_per_million
    ) / Decimal("1000000")
