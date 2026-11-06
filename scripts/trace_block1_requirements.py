"""Read-only requirements-to-evidence coverage matrix, fail-closed by design.

A requirement is not complete because a source file exists or a test name
matches it. This script produces an actionable map of the 19 acceptance
criteria to exact source/test candidates and explicitly flags absent
independent runtime receipts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ai_product_factory.product_readiness import REQUIRED_COVERAGE_BY_DOMAIN

CANDIDATES = {
    "security/authn_authz": ("src/ai_product_factory/runtime_auth.py", "tests/test_block1_source_boundaries.py"),
    "security/data_access_boundaries": ("src/ai_product_factory/github_auth.py", "tests/test_block1_source_boundaries.py"),
    "security/secrets_dependencies": ("src/ai_product_factory/independent_security_evidence.py", "scripts/audit_block1_credential_exposure.py", "tests/test_independent_security_evidence.py"),
    "observability_operations/health": ("src/ai_product_factory/independent_health_evidence.py",),
    "observability_operations/traceability": ("src/ai_product_factory/native_v2_traceability_certification.py",),
    "observability_operations/recovery_alerting": ("docs/OPERATIONS.md", "src/ai_product_factory/operational_alerts.py"),
    "test_strategy/unit_integration": (".github/workflows/validate.yml", "tests/test_factory_acceptance.py"),
    "test_strategy/critical_e2e": ("docs/FINALIZATION_EXECUTION_CONTRACT.md",),
    "test_strategy/regression_gates": (".github/workflows/validate.yml", "scripts/audit_block1_effective_gates.py", "tests/test_block1_effective_gates.py"),
    "product_experience/surface_inventory": ("apps/console/package.json",),
    "product_experience/responsive": ("apps/console/package.json",),
    "product_experience/accessibility": ("apps/console/package.json",),
    "product_experience/states": ("apps/console/package.json",),
    "documentation/setup_configuration": ("README.md", "config/factory.example.json"),
    "documentation/operations": ("docs/OPERATIONS.md", "scripts/audit_certification_operations_preflight.py", "tests/test_certification_operations_and_mock_boundaries.py"),
    "documentation/release_rollback": ("docs/RELEASE_AUTONOMY.md", "tests/test_block1_release_rollback_exercise.py"),
    "functional_completeness/requirements_inventory": ("PROJECT_PLAN.md", "docs/FINAL_CERTIFICATION_MATRIX_20261026.md"),
    "functional_completeness/mock_noop_demo_inventory": ("scripts/inventory_block1_simulation_paths.py", "scripts/audit_block1_mock_runtime_reachability.py", "tests/test_block1_mock_runtime_reachability.py"),
    "functional_completeness/critical_journeys": ("docs/FINALIZATION_EXECUTION_CONTRACT.md",),
}


def matrix(root: Path) -> dict:
    root = root.resolve(strict=True)
    expected = {domain + "/" + key for domain, keys in REQUIRED_COVERAGE_BY_DOMAIN.items()
                for key in keys}
    if expected != set(CANDIDATES) or len(expected) != 19:
        raise ValueError("19-criterion contract drift")
    rows = []
    for criterion in sorted(expected):
        refs = CANDIDATES[criterion]
        if not refs:
            raise ValueError("unmapped requirement")
        present, missing = [], []
        for ref in refs:
            path = root / ref
            if path.is_file() and not path.is_symlink():
                present.append({"path": ref, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            else:
                missing.append(ref)
        rows.append({
            "criterion": criterion, "candidate_sources": present,
            "missing_sources": missing, "independent_execution_verified": False,
            "source_inventory_status": "complete" if not missing else "incomplete",
            "certification_status": "unverified",
        })
    return {"schema_version": 1, "scope": "requirements_traceability_inventory_not_certification",
            "requirements": rows, "count": len(rows), "certified": 0,
            "product_ready": False, "writes": 0, "paid_calls": 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = matrix(args.root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"requirements": result["count"], "missing_sources":
        sum(len(row["missing_sources"]) for row in result["requirements"]),
        "certified": 0, "product_ready": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
