from __future__ import annotations

import json
import os
from decimal import Decimal

from .model_executor import ModelRequest
from .models import Complexity
from .openai_provider import OpenAIModelPolicy, OpenAIResponsesProvider

MODEL = "gpt-5.6-luna"
MAX_OUTPUT_TOKENS = 32
MAX_COST_USD = Decimal("0.01")
INPUT_USD_PER_MILLION = Decimal("0.20")
OUTPUT_USD_PER_MILLION = Decimal("1.20")
EXPECTED_OUTPUT = "FACTORY_SMOKE_OK"


def estimate_cost_usd(usage: dict[str, float] | None) -> Decimal:
    usage = usage or {}
    input_tokens = Decimal(str(int(usage.get("input_tokens", 0))))
    output_tokens = Decimal(str(int(usage.get("output_tokens", 0))))
    return (
        input_tokens * INPUT_USD_PER_MILLION
        + output_tokens * OUTPUT_USD_PER_MILLION
    ) / Decimal("1000000")


def run() -> dict[str, object]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    provider = OpenAIResponsesProvider(
        access_token_provider=lambda: api_key,
        policy=OpenAIModelPolicy(
            low=MODEL,
            medium=MODEL,
            high=MODEL,
            very_high=MODEL,
            default_reasoning_effort="none",
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
    )
    result = provider.execute_for_complexity(
        ModelRequest(
            task_id="billing-smoke",
            objective=f"Return exactly {EXPECTED_OUTPUT} and nothing else.",
            context="Bounded OpenAI API billing smoke for AI Product Factory.",
        ),
        Complexity.LOW,
        reasoning_effort="none",
    )
    output = result.output.strip()
    if output != EXPECTED_OUTPUT:
        raise RuntimeError(f"Unexpected smoke output: {output[:200]!r}")

    cost = estimate_cost_usd(result.usage)
    if cost > MAX_COST_USD:
        raise RuntimeError(
            f"Smoke cost exceeded ceiling: {cost} > {MAX_COST_USD}"
        )

    return {
        "status": "ok",
        "model": MODEL,
        "provider_ref": result.provider_ref,
        "usage": result.usage or {},
        "estimated_cost_usd": format(cost, "f"),
        "cost_ceiling_usd": format(MAX_COST_USD, "f"),
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "output": output,
    }


def main() -> int:
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
