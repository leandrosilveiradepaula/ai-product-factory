#!/usr/bin/env python3
"""Recover proven exact-scope errors only; one bounded Control Plane RPC."""
from __future__ import annotations

import argparse
import json

from ai_product_factory.literal_scope_recovery import resume_blocked_literal_scope


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-items", type=int, default=2)
    args = parser.parse_args()
    try:
        receipt = resume_blocked_literal_scope(max_items=args.max_items)
    except (RuntimeError, ValueError) as exc:
        print(json.dumps({
            "status": "blocked", "reason": str(exc)[:160],
            "requeued": 0, "product_stage_replayed": False,
            "release_authorized": False, "paid_model_calls": 0,
        }))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    # The separately human-gated migration must be applied first.
    # Keep other scheduler lanes available without pretending requeue.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
