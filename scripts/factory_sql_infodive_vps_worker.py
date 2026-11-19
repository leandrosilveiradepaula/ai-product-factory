"""VPS-only read-only operational preflight. No paid request or run claim."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ai_product_factory.private_model_vps_readiness import assess, local_checkout_sha


def main(argv=None):
    parser = argparse.ArgumentParser(prog="factory-sql-infodive-vps-worker")
    parser.add_argument("--preflight-only", action="store_true", required=True)
    parser.add_argument("--tcp", action="store_true")
    args = parser.parse_args(argv)
    try:
        from ai_product_factory.primary_cost_config import require_primary_cost_capacity
        receipt = assess(
            os.environ, head=local_checkout_sha(),
            capacity=require_primary_cost_capacity, tcp=args.tcp,
        ).receipt()
    except Exception:
        receipt = {
            "schema": "factory-vps-sql-infodive-readiness-v1",
            "provider": "infodive_ibm_cloud",
            "status": "blocked", "reason": "readiness_unavailable",
            "model_invoked": False, "run_claimed": False,
            "sql_executed": False,
        }
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["status"] == "preflight_ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
