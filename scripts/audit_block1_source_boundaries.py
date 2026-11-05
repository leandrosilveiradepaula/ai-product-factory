"""Read-only source boundary audit for Block 1.

Checks executable structural invariants rather than promoting a security PASS.
The caller supplies bytes from a checked-out SHA; no tokens, provider requests,
secrets, deployment or database are read.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

REQUIRED = {
    "src/ai_product_factory/github_auth.py",
    "src/ai_product_factory/runtime_auth.py",
    "src/ai_product_factory/product_readiness_certification.py",
    "scripts/certify_product_readiness.py",
    ".github/workflows/validate.yml",
    ".github/workflows/autonomous-runner.yml",
}


def _function(module: ast.Module, name: str) -> ast.FunctionDef:
    matches = [n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(matches) != 1:
        raise ValueError("required function unavailable or duplicated")
    return matches[0]


def inspect_boundaries(files: dict[str, str]) -> dict:
    if not isinstance(files, dict) or set(files) != REQUIRED:
        raise ValueError("incomplete source inventory")
    if any(not isinstance(v, str) or not v for v in files.values()):
        raise ValueError("source bytes missing")
    github = ast.parse(files["src/ai_product_factory/github_auth.py"])
    resolve = _function(github, "resolve_github_token")
    source = ast.get_source_segment(files["src/ai_product_factory/github_auth.py"], resolve) or ""
    # Require both scoped Actions token branch and fail-closed cross-repo path.
    checks = {
        "cross_repo_rejection": "raise PermissionError(" in source,
        "actions_repository_identity": 'GITHUB_REPOSITORY' in source,
        "factory_token_is_explicit": 'FACTORY_GITHUB_TOKEN' in source,
        "native_token_scoped": 'GITHUB_ACTIONS' in source,
        "independent_certifier": "trusted_verifier" in files["src/ai_product_factory/product_readiness_certification.py"],
        "human_release_gate": "awaiting_release" in files[".github/workflows/autonomous-runner.yml"],
        "ci_has_unit_and_acceptance": (
            "  test:" in files[".github/workflows/validate.yml"]
            and "  factory-acceptance:" in files[".github/workflows/validate.yml"]
        ),
        "certifier_baseline_required": (
            "--require-verified-baseline" in files[".github/workflows/autonomous-runner.yml"]
            and "require_verified_baseline" in files["scripts/certify_product_readiness.py"]
        ),
    }
    return {
        "scope": "block1_source_boundary_negative_contract_not_security_certification",
        "checks": checks,
        "all_source_contracts_present": all(checks.values()),
        "security_certified": False,
        "release_authorized": False,
        "paid_calls": 0,
    }


def audit_root(root: Path) -> dict:
    root = root.resolve(strict=True)
    files = {}
    for path in sorted(REQUIRED):
        file = root / path
        if not file.is_file() or file.is_symlink():
            raise ValueError("source missing or symlinked: " + path)
        files[path] = file.read_text(encoding="utf-8")
    return inspect_boundaries(files)


def main() -> int:
    result = audit_root(Path(__file__).resolve().parents[1])
    print(json.dumps(result, sort_keys=True))
    return 0 if result["all_source_contracts_present"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
