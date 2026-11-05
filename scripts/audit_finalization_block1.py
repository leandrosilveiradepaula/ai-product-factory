"""Read-only Block 1 evidence inventory. Never grants readiness or release.

Source checks are NOT independent security/functional certification. The
report deliberately uses 'partial' for inspected surfaces, never 'passed'.
No GitHub/Supabase credentials, model calls, migrations or writes outside
the optional local report file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

BLOCK = {
    "security": ("authn_authz", "data_access_boundaries", "secrets_dependencies"),
    "test_strategy": ("regression_gates",),
    "documentation": ("setup_configuration", "operations", "release_rollback"),
    "functional_completeness": ("requirements_inventory", "mock_noop_demo_inventory"),
}
DOCUMENTS = {
    "README.md": ("PYTHONPATH=src", "python -m ai_product_factory.cli validate"),
    "AGENTS.md": ("docs/FINALIZATION_EXECUTION_CONTRACT.md", "product_ready=false"),
    "PROJECT_PLAN.md": ("FINALIZATION_EXECUTION_CONTRACT.md", "product_ready=false"),
    "docs/STATUS.md": ("FINALIZATION_EXECUTION_CONTRACT.md", "product_ready=false"),
    "docs/OPERATIONS.md": ("FINALIZATION_EXECUTION_CONTRACT.md", "product_ready=false"),
    "docs/FINALIZATION_EXECUTION_CONTRACT.md": ("CRM", "Service Desk", "product_ready=false"),
    "docs/FINAL_CERTIFICATION_MATRIX_20261026.md": ("authn_authz", "mock_noop_demo_inventory"),
    "docs/RELEASE_AUTONOMY.md": ("awaiting_release", "rollback", "humano"),
}
SOURCE = (
    "src/ai_product_factory/product_readiness.py",
    "src/ai_product_factory/product_readiness_certification.py",
    "src/ai_product_factory/github_rest.py",
    "src/ai_product_factory/release_policy.py",
    "src/ai_product_factory/runtime_auth.py",
    "src/ai_product_factory/github_auth.py",
    ".github/workflows/validate.yml",
    ".github/workflows/autonomous-runner.yml",
    "config/factory.example.json",
)
SIMULATION = re.compile(r"(?i)(?<![a-z0-9_])(dry_run|dry-run|mock|noop|no_op|fixture|demo)(?![a-z0-9_])")
HEX_SHA = re.compile(r"[a-f0-9]{40}\Z")


def _read(root: Path, path: str) -> str:
    target = root / path
    if not target.is_file() or target.is_symlink():
        raise ValueError("required source missing or symlink: " + path)
    return target.read_text(encoding="utf-8")


def _source_tree(root: Path) -> list[Path]:
    src = root / "src" / "ai_product_factory"
    if not src.is_dir() or src.is_symlink():
        raise ValueError("source directory unavailable")
    return sorted(p for p in src.rglob("*.py") if p.is_file() and not p.is_symlink())


def _git_sha(root: Path) -> str:
    p = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"], cwd=root,
        capture_output=True, text=True, check=True, timeout=10,
    )
    sha = p.stdout.strip()
    if HEX_SHA.fullmatch(sha) is None:
        raise ValueError("not an exact Git SHA")
    return sha


def _criterion(status: str, findings: list[str], evidence: list[str]) -> dict:
    if status not in ("partial", "missing"):
        raise ValueError("source inventory cannot certify PASS")
    return {"status": status, "findings": sorted(set(findings)),
            "evidence": sorted(set(evidence)), "independent_pass": False}


def audit(root: Path, *, sha: str) -> dict:
    if HEX_SHA.fullmatch(sha) is None:
        raise ValueError("invalid source SHA")
    root = root.resolve(strict=True)
    findings = {}
    hashes = {}
    for path, markers in DOCUMENTS.items():
        try:
            body = _read(root, path)
            hashes[path] = hashlib.sha256(body.encode("utf-8")).hexdigest()
            absent = [marker for marker in markers if marker not in body]
            findings[path] = [] if not absent else ["required_contract_marker_missing"]
        except (ValueError, OSError, UnicodeError):
            findings[path] = ["document_missing_or_unreadable"]
    for path in SOURCE:
        try:
            body = _read(root, path)
            hashes[path] = hashlib.sha256(body.encode("utf-8")).hexdigest()
        except (ValueError, OSError, UnicodeError):
            findings[path] = ["source_missing_or_unreadable"]
    docs = {
        "setup_configuration": ("README.md", "config/factory.example.json"),
        "operations": ("docs/OPERATIONS.md", "docs/STATUS.md", "AGENTS.md"),
        "release_rollback": ("docs/RELEASE_AUTONOMY.md", "docs/FINALIZATION_EXECUTION_CONTRACT.md"),
    }
    checks = {}
    for criterion, paths in docs.items():
        issues = [p + ":" + ",".join(findings.get(p, ["not_scanned"]))
                  for p in paths if findings.get(p, ["not_scanned"])]
        checks["documentation/" + criterion] = _criterion(
            "partial" if not issues else "missing", issues or
            ["source contract inspected; executable independent runbook review still required"],
            [p + "@sha256:" + hashes[p] for p in paths if p in hashes],
        )
    security_sources = {
        "authn_authz": ("src/ai_product_factory/runtime_auth.py",
                       "src/ai_product_factory/github_auth.py"),
        "data_access_boundaries": ("src/ai_product_factory/runtime_auth.py",
                                   "src/ai_product_factory/github_rest.py"),
        "secrets_dependencies": ("src/ai_product_factory/github_auth.py",
                                 ".github/workflows/autonomous-runner.yml"),
    }
    for criterion, paths in security_sources.items():
        issues = [p + ":unavailable" for p in paths if p not in hashes]
        checks["security/" + criterion] = _criterion(
            "partial" if not issues else "missing",
            issues or ["source-only inventory; authenticated adversarial and live RLS/secret review required"],
            [p + "@sha256:" + hashes[p] for p in paths if p in hashes],
        )
    gates = (".github/workflows/validate.yml",
             "src/ai_product_factory/release_policy.py")
    issues = [p + ":unavailable" for p in gates if p not in hashes]
    checks["test_strategy/regression_gates"] = _criterion(
        "partial" if not issues else "missing",
        issues or ["branch ruleset, required PostgreSQL QA and preview enforcement require live independent verification"],
        [p + "@sha256:" + hashes[p] for p in gates if p in hashes],
    )
    requirements = ("PROJECT_PLAN.md", "docs/FINAL_CERTIFICATION_MATRIX_20261026.md",
                    "src/ai_product_factory/product_readiness.py")
    issues = [p + ":unavailable" for p in requirements if p not in hashes]
    checks["functional_completeness/requirements_inventory"] = _criterion(
        "partial" if not issues else "missing",
        issues or ["requirements mapped by source inventory only; journey-level proof still required"],
        [p + "@sha256:" + hashes[p] for p in requirements if p in hashes],
    )
    source_files = _source_tree(root)
    hits = []
    for file in source_files:
        relative = file.relative_to(root).as_posix()
        body = file.read_text(encoding="utf-8")
        if SIMULATION.search(body):
            hits.append(relative)
    # Inventory file paths only; never print code or secret values.
    checks["functional_completeness/mock_noop_demo_inventory"] = _criterion(
        "partial",
        ["simulation markers need per-path negative runtime reachability verification"],
        ["source_files_scanned:" + str(len(source_files)),
         "simulation_marker_files:" + str(len(hits))],
    )
    if set(checks) != {d + "/" + k for d, ks in BLOCK.items() for k in ks}:
        raise ValueError("block1 coverage drift")
    return {
        "schema_version": 1,
        "scope": "block1_source_inventory_not_certification",
        "repository": "leandrosilveiradepaula/ai-product-factory",
        "assessed_commit": sha,
        "criteria": checks,
        "source_file_count": len(source_files),
        "simulation_marker_paths": hits,
        "source_digests": dict(sorted(hashes.items())),
        "writes_to_production": 0,
        "paid_calls": 0,
        "product_ready": False,
        "certified_criteria": 0,
        "independent_execution_proof": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = audit(args.root, sha=_git_sha(args.root))
    serialized = json.dumps(report, sort_keys=True, ensure_ascii=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(json.dumps({"sha": report["assessed_commit"],
                      "block1_criteria": len(report["criteria"]),
                      "source_files": report["source_file_count"],
                      "certified_criteria": 0, "product_ready": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
