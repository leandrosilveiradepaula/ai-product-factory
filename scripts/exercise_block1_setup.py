"""Execute documented offline setup commands on the current checked-out SHA.

No provider credentials, network, models, deployment, migrations, database or
release. A successful run proves only these two local commands work.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = (
    (sys.executable, "-m", "ai_product_factory.cli", "validate", "config/factory.example.json"),
    (sys.executable, "-m", "ai_product_factory.cli", "codex-decision",
     "--complexity", "high", "--files", "20", "--deep-debug"),
)


def exercise(root: Path = ROOT) -> dict:
    root = root.resolve(strict=True)
    readme = (root / "README.md").read_text(encoding="utf-8")
    required = (
        "python -m ai_product_factory.cli validate config/factory.example.json",
        "python -m ai_product_factory.cli codex-decision --complexity high --files 20 --deep-debug",
    )
    if not all(x in readme for x in required):
        raise ValueError("README commands drifted")
    # A minimal environment prevents accidental provider/network credentials
    # from being inherited by the commands under test.
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "PYTHONPATH": str(root / "src"),
           "PYTHONDONTWRITEBYTECODE": "1"}
    results = []
    for command in COMMANDS:
        run = subprocess.run(command, cwd=root, env=env, capture_output=True,
                             text=True, timeout=30, check=False)
        results.append({"command": command[2], "exit_code": run.returncode,
                        "stdout_nonempty": bool(run.stdout.strip())})
    return {"scope": "isolated_local_setup_not_product_certification",
            "commands": results, "all_succeeded": all(x["exit_code"] == 0 for x in results),
            "product_ready": False, "paid_calls": 0, "writes_to_production": 0}


def main() -> int:
    result = exercise()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["all_succeeded"] else 1


if __name__ == "__main__":
    sys.exit(main())
