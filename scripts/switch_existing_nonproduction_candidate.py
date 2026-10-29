#!/usr/bin/env python3
"""Explicit opt-in candidate replacement; requires installed service-role RPC."""
import argparse
import json

from ai_product_factory.nonproduction_candidate_switch import switch_one


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-key", required=True)
    parser.add_argument("--candidate-pr", required=True, type=int)
    parser.add_argument("--issue-number", required=True, type=int)
    args = parser.parse_args()
    receipt = switch_one(
        args.project_key, candidate_pr_number=args.candidate_pr,
        issue_number=args.issue_number,
    )
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
