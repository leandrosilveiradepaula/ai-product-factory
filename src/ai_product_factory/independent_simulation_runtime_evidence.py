"""Independent exact-SHA runtime simulation evidence, fail closed.

A pinned executable test source must be present in the *committed* Git tree.
The current-SHA main validation must have executed both required jobs, and
the bounded static inventory must have no unclassified runtime marker.
No caller-supplied manifest may manufacture an additional PASS.
"""
from __future__ import annotations

import re
from typing import Callable

from .product_readiness_certification import VerifiedCriterionEvidence

REPO = "leandrosilveiradepaula/ai-product-factory"
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
REQUIRED_EXECUTED_TEST = "tests/test_block1_simulation_runtime_admission_evidence.py"
# Immutable source reviewed in this PR: unexpected changes to the test are
# rejected until independently re-reviewed and re-pinned with a new commit.
TRUSTED_EXECUTED_TEST_BLOB = "70f676c8aa4ddc65ea4ce354b042dd405c57f71c"
REQUIRED_MODULES = {
    "src/ai_product_factory/runtime_cli.py",
    "src/ai_product_factory/runtime_auth.py",
    "src/ai_product_factory/execution_worker.py",
    "scripts/inventory_block1_simulation_paths.py",
    "scripts/audit_block1_mock_runtime_reachability.py",
    REQUIRED_EXECUTED_TEST,
}


class RuntimeSimulationEvidenceBlocked(RuntimeError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise RuntimeSimulationEvidenceBlocked(reason)


def verify_executed_simulation_inventory(
    *, repository: str, assessed_commit: str,
    github_get: Callable[[str], object],
    source_inventory: object, runtime_reachability: object,
) -> VerifiedCriterionEvidence:
    require(repository == REPO and isinstance(assessed_commit, str)
            and SHA.fullmatch(assessed_commit) is not None,
            "simulation_repository_or_sha_invalid")
    require(isinstance(source_inventory, dict)
            and source_inventory.get("scope") == "source_markers_not_runtime_reachability"
            and type(source_inventory.get("source_files")) is int
            and source_inventory["source_files"] >= 1
            and type(source_inventory.get("marker_occurrences_by_line")) is int
            and source_inventory["marker_occurrences_by_line"] > 0
            and isinstance(source_inventory.get("fingerprint"), str)
            and DIGEST.fullmatch(source_inventory["fingerprint"]) is not None
            and source_inventory.get("paid_calls") == 0
            and source_inventory.get("writes_to_production") == 0
            and source_inventory.get("independent_pass") is False
            and isinstance(source_inventory.get("locations"), list)
            and len(source_inventory["locations"]) ==
                source_inventory["marker_occurrences_by_line"],
            "simulation_marker_inventory_not_verified")
    require(isinstance(runtime_reachability, dict)
            and runtime_reachability.get("scope") ==
                "static-runtime-cli-import-closure-and-guard-classification-not-runtime-proof"
            and runtime_reachability.get("entrypoint") ==
                "src/ai_product_factory/runtime_cli.py"
            and runtime_reachability.get("unclassified_runtime_markers") == []
            and isinstance(runtime_reachability.get("reachable_modules"), list)
            and "runtime_cli" in runtime_reachability["reachable_modules"]
            and runtime_reachability.get("simulation_can_authorize_release") is False
            and runtime_reachability.get("independent_pass") is False
            and runtime_reachability.get("paid_calls") == 0
            and runtime_reachability.get("writes") == 0,
            "simulation_runtime_reachability_unverified")
    prefix = "/repos/" + REPO
    data = github_get(prefix + "/git/trees/" + assessed_commit + "?recursive=1")
    require(isinstance(data, dict) and data.get("truncated") is False
            and isinstance(data.get("tree"), list)
            and len(data["tree"]) <= 10000,
            "simulation_exact_git_tree_unavailable")
    blobs = {}
    for node in data["tree"]:
        if (not isinstance(node, dict)
            or not isinstance(node.get("path"), str)
            or not isinstance(node.get("sha"), str)):
            raise RuntimeSimulationEvidenceBlocked("simulation_invalid_tree_entry")
        if node["path"] in REQUIRED_MODULES:
            require(node.get("type") == "blob" and
                    SHA.fullmatch(node["sha"]) is not None and
                    node["path"] not in blobs,
                    "simulation_runtime_blob_invalid")
            blobs[node["path"]] = node["sha"]
    require(set(blobs) == REQUIRED_MODULES,
            "simulation_required_entrypoint_source_missing")
    require(blobs[REQUIRED_EXECUTED_TEST] == TRUSTED_EXECUTED_TEST_BLOB,
            "simulation_executed_test_source_changed")
    runs = github_get(prefix + "/actions/runs?head_sha=" +
                      assessed_commit + "&per_page=100")
    require(isinstance(runs, dict)
            and type(runs.get("total_count")) is int
            and 1 <= runs["total_count"] <= 100
            and isinstance(runs.get("workflow_runs"), list),
            "simulation_validate_runs_unavailable")
    matches = [run for run in runs["workflow_runs"]
               if isinstance(run, dict)
               and run.get("name") == "validate"
               and run.get("event") == "push"
               and run.get("head_branch") == "main"
               and run.get("head_sha") == assessed_commit
               and run.get("status") == "completed"
               and run.get("conclusion") == "success"
               and type(run.get("id")) is int]
    require(len(matches) == 1, "simulation_exact_main_validate_missing")
    run = matches[0]
    jobs = github_get(prefix + "/actions/runs/" + str(run["id"]) +
                      "/jobs?per_page=100")
    require(isinstance(jobs, dict) and isinstance(jobs.get("jobs"), list)
            and len(jobs["jobs"]) <= 100,
            "simulation_validate_jobs_unavailable")
    completed = {}
    for job in jobs["jobs"]:
        if not isinstance(job, dict):
            raise RuntimeSimulationEvidenceBlocked("simulation_validate_job_invalid")
        if job.get("name") in ("test", "factory-acceptance"):
            require(job["name"] not in completed and
                    job.get("status") == "completed" and
                    job.get("conclusion") == "success",
                    "simulation_required_job_failed")
            completed[job["name"]] = True
    require(set(completed) == {"test", "factory-acceptance"},
            "simulation_required_validate_job_missing")
    receipt = {
        "schema": "factory-block1-executed-simulation-denial-v1",
        "scope": "bounded_runtime_entrypoint_denials_and_static_marker_closure_not_live_provider_or_tenant_e2e",
        "assessed_commit": assessed_commit,
        "validate_run_id": run["id"],
        "validated_jobs": sorted(completed),
        "trusted_executed_test_blob": blobs[REQUIRED_EXECUTED_TEST],
        "runtime_source_blobs": {k: blobs[k] for k in sorted(blobs) if k != REQUIRED_EXECUTED_TEST},
        "marker_inventory_fingerprint": source_inventory["fingerprint"],
        "marker_occurrences": source_inventory["marker_occurrences_by_line"],
        "unclassified_runtime_markers": 0,
        "executed_denial_entrypoints": [
            "run_product_once", "run_direct_once", "run_codex_once",
            "run_dispatch_once", "run_preview_once", "run_release_once",
            "_CheckpointedGitHub.create_pull_request",
        ],
        "live_authn_authz_certified": False,
        "critical_e2e_certified": False,
        "production_release_observed": False,
        "paid_calls": 0,
        "production_writes": 0,
    }
    return VerifiedCriterionEvidence(
        domain="functional_completeness",
        criterion="mock_noop_demo_inventory",
        repository=repository,
        assessed_commit=assessed_commit,
        verification_state="reviewed",
        source="github-exact-sha-executed-simulation-guard:" +
               str(run["id"]) + ":" + blobs[REQUIRED_EXECUTED_TEST],
        evidence=("https://github.com/" + repository + "/actions/runs/" +
                  str(run["id"]) + "#sha=" + assessed_commit,),
        retained_receipt=receipt,
    )
