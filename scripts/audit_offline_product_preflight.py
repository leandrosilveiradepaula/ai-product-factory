#!/usr/bin/env python3
"""Offline source preflight of an already recorded Product Stage run."""
from __future__ import annotations

import argparse
import json
import sys

from ai_product_factory.offline_product_preflight import check_recorded_product_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only, no-model Product Stage preflight")
    parser.add_argument("--project-key", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        report = check_recorded_product_run(
            project_key=args.project_key, run_id=args.run_id,
        )
    except ValueError:
        report = {
            "project_key": "invalid", "state": "blocked",
            "source_preflight": "blocked", "reason_code": "invalid_input",
            "model_tested": False, "paid_model_calls": 0, "writes": 0,
            "budget_authorized": False, "e2e_verified": False,
        }
    print(json.dumps(report, sort_keys=True, ensure_ascii=False))
    return 0 if report["source_preflight"] == "verified" else 2


if __name__ == "__main__":
    sys.exit(main())
