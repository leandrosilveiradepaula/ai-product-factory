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
import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path

from ai_product_factory.product_readiness_certification import VerifiedCriterionEvidence

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
    "functional_completeness/requirements_inventory": (
        "PROJECT_PLAN.md", "docs/FINAL_CERTIFICATION_MATRIX_20261026.md",
        "docs/FINALIZATION_EXECUTION_CONTRACT.md",
        "scripts/trace_block1_requirements.py", "tests/test_block1_requirements_trace.py",
    ),
    "functional_completeness/mock_noop_demo_inventory": ("scripts/inventory_block1_simulation_paths.py", "scripts/audit_block1_mock_runtime_reachability.py", "tests/test_block1_mock_runtime_reachability.py"),
    "functional_completeness/critical_journeys": ("docs/FINALIZATION_EXECUTION_CONTRACT.md",),
}


# Stages of the actual Factory flow; they describe where the requirement
# applies, not whether the stage is implemented or independently proven.
JOURNEY_STAGES = {
    "security/authn_authz": ("idea", "awaiting_release", "operation"),
    "security/data_access_boundaries": ("implementation", "operation"),
    "security/secrets_dependencies": ("routing", "implementation"),
    "observability_operations/health": ("operation",),
    "observability_operations/traceability": ("idea", "preview_verified", "release_observed"),
    "observability_operations/recovery_alerting": ("operation",),
    "test_strategy/unit_integration": ("tests_evals",),
    "test_strategy/critical_e2e": ("preview_verified", "release_observed"),
    "test_strategy/regression_gates": ("tests_evals", "awaiting_release"),
    "product_experience/surface_inventory": ("preview_verified",),
    "product_experience/responsive": ("preview_verified",),
    "product_experience/accessibility": ("preview_verified",),
    "product_experience/states": ("preview_verified", "operation"),
    "documentation/setup_configuration": ("plan", "implementation"),
    "documentation/operations": ("operation",),
    "documentation/release_rollback": ("awaiting_release", "release_observed"),
    "functional_completeness/requirements_inventory": ("product_spec", "plan", "backlog"),
    "functional_completeness/mock_noop_demo_inventory": ("routing", "implementation", "release_observed"),
    "functional_completeness/critical_journeys": ("idea", "release_observed", "operation"),
}
VALID_STAGES = frozenset({
    "idea", "discovery", "product_spec", "plan", "backlog", "routing",
    "implementation", "review", "tests_evals", "preview_verified",
    "awaiting_release", "release_observed", "operation",
})
REPO = "leandrosilveiradepaula/ai-product-factory"
OWNER_WORKFLOW = ".github/workflows/autonomous-runner.yml"
SHA = re.compile(r"[0-9a-f]{40}\Z")


class RequirementsInventoryBlocked(RuntimeError):
    """Sanitized source-verifier code; never contains credential/provider data."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise RequirementsInventoryBlocked(code)


def _git_blob_oid(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def _status_fingerprint(criteria: object) -> tuple[str, list[str]]:
    """Bind inventory to all other exact-SHA acceptance states, including gaps."""
    require(isinstance(criteria, dict), "requirements_criteria_missing")
    observed: dict[str, str] = {}
    gaps = []
    for domain, keys in REQUIRED_COVERAGE_BY_DOMAIN.items():
        rows = criteria.get(domain)
        require(isinstance(rows, dict) and set(rows) == set(keys),
                "requirements_criteria_contract_drift")
        for key in keys:
            name = domain + "/" + key
            row = rows.get(key)
            require(isinstance(row, dict)
                    and row.get("status") in ("passed", "partial", "missing", "failed", "external_gate"),
                    "requirements_criterion_state_invalid")
            if name == "functional_completeness/requirements_inventory":
                continue  # Never use the self-asserted PASS as evidence.
            observed[name] = row["status"]
            if row["status"] != "passed":
                gaps.append(name)
    require(len(observed) == 18, "requirements_criteria_contract_drift")
    digest = hashlib.sha256(json.dumps(
        observed, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return digest, sorted(gaps)


def _require_runner(*, repository: str, assessed_commit: str,
                    github_get: Callable[[str], object],
                    environment: Mapping[str, str], event_payload: Mapping | None) -> tuple[str, int, int]:
    require(repository == REPO and isinstance(assessed_commit, str)
            and SHA.fullmatch(assessed_commit) is not None,
            "requirements_repository_or_sha_invalid")
    env = environment
    require(env.get("GITHUB_ACTIONS") == "true"
            and env.get("GITHUB_REPOSITORY") == REPO
            and env.get("GITHUB_EVENT_NAME") == "workflow_run"
            and env.get("GITHUB_REF") == "refs/heads/main"
            and env.get("GITHUB_WORKFLOW_REF") == REPO + "/" + OWNER_WORKFLOW + "@refs/heads/main"
            and isinstance(env.get("GITHUB_RUN_ID"), str)
            and env["GITHUB_RUN_ID"].isdecimal(),
            "requirements_runner_identity_invalid")
    if event_payload is None:
        event_path = env.get("GITHUB_EVENT_PATH", "")
        require(isinstance(event_path, str) and event_path,
                "requirements_event_unavailable")
        raw = Path(event_path).read_bytes()
        require(0 < len(raw) <= 256000, "requirements_event_size_invalid")
        event_payload = json.loads(raw)
    require(isinstance(event_payload, Mapping), "requirements_event_invalid")
    source = event_payload.get("workflow_run")
    require(isinstance(source, dict)
            and source.get("name") == "validate"
            and source.get("path") == ".github/workflows/validate.yml"
            and source.get("event") == "push"
            and source.get("status") == "completed"
            and source.get("conclusion") == "success"
            and source.get("head_sha") == assessed_commit
            and source.get("head_branch") == "main"
            and source.get("run_attempt") == 1
            and isinstance(source.get("repository"), dict)
            and source["repository"].get("full_name") == REPO
            and type(source.get("id")) is int and source["id"] > 0,
            "requirements_upstream_validate_unbound")
    prefix = "/repos/" + REPO
    current_id, source_id = int(env["GITHUB_RUN_ID"]), source["id"]
    current = github_get(prefix + "/actions/runs/" + str(current_id))
    require(isinstance(current, dict) and current.get("id") == current_id
            and current.get("name") == "Factory autonomous runner"
            and current.get("path") == OWNER_WORKFLOW
            and current.get("event") == "workflow_run"
            and current.get("head_sha") == assessed_commit
            and current.get("head_branch") == "main"
            and current.get("run_attempt") == 1
            and current.get("status") in ("queued", "in_progress", "completed")
            and (current.get("status") != "completed" or current.get("conclusion") == "success"),
            "requirements_current_runner_unbound")
    head = github_get(prefix + "/git/ref/heads/main")
    require(isinstance(head, dict) and isinstance(head.get("object"), dict)
            and head["object"].get("sha") == assessed_commit,
            "requirements_main_head_mismatch")
    jobs = github_get(prefix + "/actions/runs/" + str(source_id) + "/jobs?per_page=100")
    rows = jobs.get("jobs") if isinstance(jobs, dict) else None
    require(isinstance(rows, list) and type(jobs.get("total_count")) is int
            and len(rows) == jobs["total_count"] and 0 < len(rows) <= 100,
            "requirements_ci_jobs_incomplete")
    passed = {job.get("name") for job in rows if isinstance(job, dict)
              and job.get("run_id") == source_id
              and job.get("head_sha") == assessed_commit
              and job.get("status") == "completed" and job.get("conclusion") == "success"}
    require({"test", "factory-acceptance"}.issubset(passed)
            and len(passed) == len(rows), "requirements_ci_jobs_unverified")
    return prefix, current_id, source_id


def verify_requirements_inventory(*, repository: str, assessed_commit: str,
                                  github_get: Callable[[str], object],
                                  criteria: dict, root: Path | None = None,
                                  environment: Mapping[str, str] | None = None,
                                  event_payload: Mapping | None = None) -> VerifiedCriterionEvidence:
    """Independently verify a COMPLETE INVENTORY, not requirement delivery."""
    prefix, run_id, source_id = _require_runner(
        repository=repository, assessed_commit=assessed_commit, github_get=github_get,
        environment=os.environ if environment is None else environment,
        event_payload=event_payload,
    )
    checkout = Path.cwd() if root is None else root
    require(checkout.is_dir() and not checkout.is_symlink(),
            "requirements_checkout_unavailable")
    report = matrix(checkout)
    require(report["count"] == 19 and report["certified"] == 0
            and report["product_ready"] is False
            and report["writes"] == 0 and report["paid_calls"] == 0
            and all(row["source_inventory_status"] == "complete"
                    and not row["missing_sources"]
                    and row["independent_execution_verified"] is False
                    and row["certification_status"] == "unverified"
                    and row["journey_stages"]
                    and set(row["journey_stages"]).issubset(VALID_STAGES)
                    for row in report["requirements"]),
            "requirements_inventory_incomplete")
    tree = github_get(prefix + "/git/trees/" + assessed_commit + "?recursive=1")
    entries = tree.get("tree") if isinstance(tree, dict) else None
    require(isinstance(tree, dict) and tree.get("truncated") is False
            and isinstance(entries, list) and 0 < len(entries) <= 20000,
            "requirements_source_tree_incomplete")
    expected = set(path for refs in CANDIDATES.values() for path in refs)
    remote: dict[str, str] = {}
    for item in entries:
        require(isinstance(item, dict), "requirements_tree_entry_invalid")
        path = item.get("path")
        if path not in expected:
            continue
        value = item.get("sha")
        require(path not in remote and item.get("type") == "blob"
                and item.get("mode") in ("100644", "100755")
                and isinstance(value, str) and SHA.fullmatch(value) is not None,
                "requirements_source_blob_invalid")
        remote[path] = value
    require(set(remote) == expected, "requirements_source_blob_missing")
    hashes = {}
    for path in expected:
        pieces = Path(path).parts
        require(Path(path).as_posix() == path
                and all(part not in ("", ".", "..") for part in pieces),
                "requirements_source_path_invalid")
        source = checkout
        for part in pieces:
            source = source / part
            require(not source.is_symlink(), "requirements_source_symlink_forbidden")
        require(source.is_file(), "requirements_source_missing")
        raw = source.read_bytes()
        require(0 < len(raw) <= 1000000 and _git_blob_oid(raw) == remote[path],
                "requirements_checkout_blob_drift")
        hashes[path] = hashlib.sha256(raw).hexdigest()
    for row in report["requirements"]:
        for ref in row["candidate_sources"]:
            require(ref["sha256"] == hashes[ref["path"]],
                    "requirements_source_digest_drift")
    require({row["criterion"] for row in report["requirements"]}
            == set(CANDIDATES) == set(JOURNEY_STAGES),
            "requirements_criteria_contract_drift")
    statuses_digest, gaps = _status_fingerprint(criteria)
    latest = github_get(prefix + "/git/ref/heads/main")
    require(isinstance(latest, dict) and isinstance(latest.get("object"), dict)
            and latest["object"].get("sha") == assessed_commit,
            "requirements_main_changed_during_audit")
    source_digest = hashlib.sha256(json.dumps(
        remote, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return VerifiedCriterionEvidence(
        domain="functional_completeness", criterion="requirements_inventory",
        repository=repository, assessed_commit=assessed_commit,
        verification_state="reviewed",
        source="github-exact-sha-requirements-inventory:" + source_digest + ":" + statuses_digest,
        evidence=("https://github.com/" + repository + "/actions/runs/" + str(run_id)
                  + "#sha=" + assessed_commit,),
        retained_receipt={
            "scope": "all_19_requirements_and_gaps_not_implementation_or_e2e",
            "mapped_criteria": 19,
            "source_blobs_verified": len(remote),
            "source_blob_digest": source_digest,
            "other_criteria_status_digest": statuses_digest,
            "unverified_other_criteria": gaps,
            "upstream_validate_run_id": source_id,
            "production_writes": 0, "paid_calls": 0, "product_ready": False,
        },
    )


def matrix(root: Path) -> dict:
    root = root.resolve(strict=True)
    expected = {domain + "/" + key for domain, keys in REQUIRED_COVERAGE_BY_DOMAIN.items()
                for key in keys}
    if expected != set(CANDIDATES) or expected != set(JOURNEY_STAGES) or len(expected) != 19:
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
            "criterion": criterion, "journey_stages": list(JOURNEY_STAGES[criterion]),
            "candidate_sources": present,
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
