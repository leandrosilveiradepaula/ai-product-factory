"""Offline supply-chain and credential-exposure preflight for Block 1.

Inspects checked-out lockfile, manifests and workflow sources only. Never
reads environment variables or credential values. This is not a CVE scanner:
a dependency advisory service and independent secret scanner remain required
before secrets_dependencies can be certified.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT_FILES = ("pyproject.toml", "apps/console/package.json",
              "apps/console/package-lock.json")
ACTION = re.compile(r"^\s*-\s*uses:\s*([^\s#]+)", re.MULTILINE)
PIN = re.compile(r"^[a-f0-9]{40}$")
SECRET_ASSIGN = re.compile(r"(?im)^\s*(?:OPENAI_API_KEY|SUPABASE_SECRET_KEY|SUPABASE_SERVICE_ROLE_KEY|FACTORY_GITHUB_TOKEN)\s*[:=]\s*[^\s$][^\r\n]*")
WORKFLOW_IGNORE = {"actions/checkout", "actions/setup-node", "actions/setup-python"}


def audit(root: Path) -> dict:
    root = root.resolve(strict=True)
    manifest_path = root / ROOT_FILES[1]
    lock_path = root / ROOT_FILES[2]
    pyproject_path = root / ROOT_FILES[0]
    for p in (manifest_path, lock_path, pyproject_path):
        if not p.is_file() or p.is_symlink():
            raise ValueError("required dependency manifest missing or symlinked")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("lockfileVersion") != 3:
        raise ValueError("unsupported npm lockfile")
    root_pkg = lock.get("packages", {}).get("", {})
    drift = []
    for group in ("dependencies", "devDependencies"):
        for name, version in manifest.get(group, {}).items():
            if root_pkg.get(group, {}).get(name) != version:
                drift.append(name + ":lock_root_mismatch")
            locked = lock.get("packages", {}).get("node_modules/" + name)
            if not isinstance(locked, dict) or not locked.get("version"):
                drift.append(name + ":lock_resolution_missing")
            elif version[0].isdigit() and locked["version"] != version:
                drift.append(name + ":lock_version_mismatch")
    workflows = root / ".github" / "workflows"
    if not workflows.is_dir() or workflows.is_symlink():
        raise ValueError("workflow tree missing")
    unpinned = []
    sensitive_literals = []
    scanned = 0
    for path in sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")]):
        if path.is_symlink():
            raise ValueError("symlinked workflow")
        body = path.read_text(encoding="utf-8")
        scanned += 1
        for action in ACTION.findall(body):
            if action.startswith("./") or action.startswith("docker://"):
                continue
            ref = action.rsplit("@", 1)[-1] if "@" in action else ""
            if not PIN.fullmatch(ref):
                unpinned.append(path.name + ":" + action.split("@")[0])
        if SECRET_ASSIGN.search(body):
            sensitive_literals.append(path.name)
    return {
        "scope": "offline_supply_chain_source_preflight_not_security_certification",
        "manifest_lock_drift": sorted(set(drift)),
        "unpinned_actions": sorted(set(unpinned)),
        "credential_assignment_candidates": sorted(set(sensitive_literals)),
        "workflow_files_scanned": scanned,
        "npm_dependency_advisory_verified": False,
        "independent_secret_scan_verified": False,
        "source_contracts_ok": not (drift or unpinned or sensitive_literals),
        "security_certified": False,
        "writes": 0,
        "paid_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = audit(args.root)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["source_contracts_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
