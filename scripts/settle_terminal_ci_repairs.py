#!/usr/bin/env python3
"""Schedule-safe, model-free, bounded CI repair terminal settlement."""
from __future__ import annotations

import argparse
import json

from ai_product_factory.ci_repair_source_settlement import settle_terminal_ci_repair_sources


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-items", type=int, default=3)
    args = parser.parse_args()
    try:
        receipt = settle_terminal_ci_repair_sources(max_items=args.max_items)
    except (RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:180],
                          "settled": 0, "paid_model_calls": 0,
                          "release_authorized": False}))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    # The migration is an administrative gate. An unapplied migration is
    # an inert result, not permission to mutate state by a generic RPC.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
