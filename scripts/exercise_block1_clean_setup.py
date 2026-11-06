"""Readme setup reproduction by a non-root identity in a credential-free CI process.

No installation, network, database, deployment, model invocation, or production
state mutation. The limited receipt is a setup observation, not product readiness.
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
    (sys.executable, "scripts/check_test_collection.py"),
)
README = (
    "python -m ai_product_factory.cli validate config/factory.example.json",
    "python -m ai_product_factory.cli codex-decision --complexity high --files 20 --deep-debug",
    "python scripts/check_test_collection.py",
)
ALLOWED_ENV = frozenset({"PATH", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "HOME", "LANG", "LC_ALL", "LC_CTYPE"})


def exercise(root: Path = ROOT, environ: dict | None = None, uid: int | None = None) -> dict:
    root = root.resolve(strict=True)
    environ = dict(os.environ if environ is None else environ)
    uid = os.getuid() if uid is None else uid
    safe_env = all(name in ALLOWED_ENV for name in environ)
    non_root = uid != 0
    python_path = environ.get("PYTHONPATH") == str(root / "src")
    readme_path = root / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    commands_documented = all(s in readme for s in README)
    results = []
    if safe_env and non_root and python_path and commands_documented:
        for command in COMMANDS:
            try:
                run = subprocess.run(command, cwd=root, env=environ, capture_output=True,
                                     text=True, timeout=30, check=False)
                results.append({
                    "command": command[2] if command[1] == "-m" else command[1],
                    "exit_code": run.returncode,
                    "stdout_nonempty": bool(run.stdout.strip()),
                    "timed_out": False,
                })
            except subprocess.TimeoutExpired:
                results.append({
                    "command": command[2] if command[1] == "-m" else command[1],
                    "exit_code": None, "stdout_nonempty": False, "timed_out": True,
                })
    passed = bool(safe_env and non_root and python_path and commands_documented
                  and len(results) == len(COMMANDS)
                  and all(x["exit_code"] == 0 and not x["timed_out"] for x in results))
    return {
        "schema": "factory-block1-clean-setup-v1",
        "non_root_identity": non_root,
        "allowlisted_environment_only": safe_env,
        "source_path_exact": python_path,
        "readme_commands_present": commands_documented,
        "commands": results,
        "setup_commands_passed": passed,
        "documentation_setup_configuration_certified": False,
        "block1_certified": False,
        "release_authorized": False,
        "paid_model_calls": 0,
    }


def main() -> int:
    report = exercise()
    print(json.dumps(report, sort_keys=True))
    return 0 if report["setup_commands_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
