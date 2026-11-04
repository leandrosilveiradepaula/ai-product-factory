#!/usr/bin/env python3
"""One exact migration-gated CRM209 native CI repair; never imports a paid model."""
from __future__ import annotations

import json
import os

from ai_product_factory.crm209_native_ci_worker import run_once


def main() -> int:
    worker_id = "nativeci-" + os.getenv("GITHUB_RUN_ID", "unknown")
    try:
        receipt = run_once(worker_id=worker_id)
    except (RuntimeError, PermissionError, ValueError, OSError) as exc:
        print(json.dumps({
            "status": "blocked",
            "error_type": type(exc).__name__,
            "claimed": False,
            "paid_model_calls": 0,
            "release_authorized": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    if receipt.get("status") not in (
        "disabled", "idle", "blocked_migration_not_applied", "work_unit_completed"
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
