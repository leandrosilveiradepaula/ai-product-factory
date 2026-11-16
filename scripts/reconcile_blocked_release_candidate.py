#!/usr/bin/env python3
"""Reconcile a blocked development candidate; dry-run unless --apply.

The database RPC is deliberately not installed before the human migration gate.
This command never merges, deploys, modifies RLS, or runs paid models.
"""
import argparse
import json

from ai_product_factory.blocked_release_candidate_reconciliation import reconcile_one


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--change-set-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--apply", action="store_true", help="execute authorized one-shot Control Plane RPC")
    args = parser.parse_args()
    receipt = reconcile_one(args.change_set_id, args.run_id, apply=args.apply)
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
