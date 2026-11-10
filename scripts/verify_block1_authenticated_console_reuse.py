"""Read-only reuse of metadata for previously captured authenticated Console evidence.

This verifies only GitHub run provenance, retained encrypted artifact,
capture job and byte-identical Console source. Never claims the encrypted
browser payload or negative RBAC was independently re-executed or inspected.
The historical detailed browser log is unavailable to the Actions job (401/403);
do not request privileged credentials, bypass authorization, or fabricate PASS.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

REPO = "leandrosilveiradepaula/ai-product-factory"
VISUAL_WORKFLOW = ".github/workflows/authenticated-visual-evidence.yml"
# This is an immutable, successful, explicitly dispatched capture.  The
# workflow itself verifies the official target URL and its deployed commit
# before it provisions the one-time operator, and removes that operator in its
# finalization step.  Keep the source commit separate from the deployment
# target: Actions records the former as ``head_sha`` for dispatch runs.
VISUAL_RUN = 42439592059
SOURCE_SHA = "d83a7095e18244c2833d626430cb3f575eb35130"
VISUAL_EVENT = "workflow_dispatch"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def exact_sha(value: object) -> bool:
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def safe_blobs(tree: dict) -> dict | None:
    if not isinstance(tree, dict) or tree.get("truncated") is not False:
        return None
    entries = tree.get("tree")
    if not isinstance(entries, list):
        return None
    found = {}
    for item in entries:
        if not isinstance(item, dict):
            return None
        path = item.get("path")
        if item.get("type") != "blob" or not isinstance(path, str) or not path.startswith("apps/console/"):
            continue
        if path in found or not exact_sha(item.get("sha")) or not isinstance(item.get("mode"), str):
            return None
        found[path] = (item["sha"], item["mode"])
    return found if found else None


def assess(candidate: str, run: dict, artifacts: dict, jobs: dict,
           comparison: dict, original_tree: dict, candidate_tree: dict) -> dict:
    if not exact_sha(candidate):
        raise ValueError("exact lowercase candidate SHA required")
    if not isinstance(run, dict):
        raise ValueError("GitHub run unavailable")
    checks = {}
    checks["trusted_visual_run"] = (
        run.get("id") == VISUAL_RUN
        and run.get("head_sha") == SOURCE_SHA
        and run.get("name") == "Authenticated Console visual evidence"
        and run.get("path") == VISUAL_WORKFLOW
        and run.get("event") == VISUAL_EVENT
        and run.get("head_branch") == "main"
        and run.get("run_attempt") == 1
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
    )
    checks["source_ancestor"] = (
        isinstance(comparison, dict)
        and comparison.get("status") in ("ahead", "identical")
        and comparison.get("behind_by") == 0
        and comparison.get("base_commit", {}).get("sha") == SOURCE_SHA
        and comparison.get("merge_base_commit", {}).get("sha") == SOURCE_SHA
    )
    source_blobs = safe_blobs(original_tree)
    target_blobs = safe_blobs(candidate_tree)
    checks["console_blobs_identical"] = (
        source_blobs is not None and target_blobs is not None
        and source_blobs == target_blobs
    )
    items = artifacts.get("artifacts", []) if isinstance(artifacts, dict) else []
    checks["encrypted_artifact_retained"] = (
        isinstance(items, list)
        and len([a for a in items if isinstance(a, dict) and
                 a.get("name") == "authenticated-console-" + str(VISUAL_RUN)
                 and a.get("expired") is False and type(a.get("size_in_bytes")) is int
                 and a["size_in_bytes"] > 0]) == 1
    )
    found_jobs = jobs.get("jobs", []) if isinstance(jobs, dict) else []
    captures = [j for j in found_jobs if isinstance(j, dict) and j.get("name") == "capture"] if isinstance(found_jobs, list) else []
    checks["capture_job_completed"] = (
        len(captures) == 1
        and captures[0].get("status") == "completed"
        and captures[0].get("conclusion") == "success"
    )
    metadata_verified = all(checks.values())
    return {
        "schema": "factory-block1-authenticated-console-metadata-reuse-v1",
        "source_sha": SOURCE_SHA,
        "candidate_sha": candidate,
        "visual_run_id": VISUAL_RUN,
        "checks": checks,
        "reusable_encrypted_evidence_metadata_verified": metadata_verified,
        "browser_interaction_payload_independently_reopened": False,
        "operator_rbac_log_independently_revalidated": False,
        "signed_jwt_issuer_claims_independently_verified": False,
        "all_tenant_authorization_covered": False,
        "authn_authz_certified": False,
        "block1_certified": False,
        "release_authorized": False,
    }


def github(path: str, token: str) -> dict:
    url = "https://api.github.com/repos/" + REPO + "/" + path
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "factory-block1-console-metadata-reuse",
        **({"Authorization": "Bearer " + token} if token else {}),
    }
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=25) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code not in (403, 429) or not token:
            raise
        # This repository is public. Retry only the identical read-only URL;
        # do not infer success or bypass provenance checks if it is denied.
        headers.pop("Authorization", None)
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=25) as response:
            return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--source-run", type=int, default=VISUAL_RUN)
    parser.add_argument("--output", type=Path, default=Path("block1-console-reuse-receipt.json"))
    args = parser.parse_args()
    if args.source_run != VISUAL_RUN or not exact_sha(args.candidate_sha):
        print('{"reusable_encrypted_evidence_metadata_verified":false,"block1_certified":false}')
        return 2
    token = os.environ.get("GITHUB_TOKEN", "")
    stage = "run"
    try:
        run = github("actions/runs/" + str(args.source_run), token)
        stage = "jobs"
        jobs = github("actions/runs/" + str(args.source_run) + "/jobs?per_page=100", token)
        stage = "evidence_bundle"
        artifacts = github("actions/runs/" + str(args.source_run) + "/artifacts?per_page=100", token)
        result = assess(
            args.candidate_sha, run, artifacts,
            jobs,
            github("compare/" + SOURCE_SHA + "..." + args.candidate_sha, token),
            github("git/trees/" + SOURCE_SHA + "?recursive=1", token),
            github("git/trees/" + args.candidate_sha + "?recursive=1", token),
        )
        # Pull-request OIDC is deliberately not permitted to read the Control
        # Plane.  An expired artifact is therefore never a PR PASS; it can only
        # reach the trusted main post-CI observer, which rechecks the durable
        # captured registry before emitting bounded partial UX evidence.
        if artifacts.get("total_count") == 0 and artifacts.get("artifacts") == []:
            result["durable_registry_revalidation_deferred_to_trusted_main_observer"] = True
    except (KeyError, ValueError, TypeError, RuntimeError, OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        result = {
            "schema": "factory-block1-authenticated-console-metadata-reuse-v1",
            "candidate_sha": args.candidate_sha,
            "error_type": type(exc).__name__,
            "error_stage": stage,
            "http_status": exc.code if isinstance(exc, urllib.error.HTTPError) else None,
            "reusable_encrypted_evidence_metadata_verified": False,
            "authn_authz_certified": False,
            "block1_certified": False,
            "release_authorized": False,
        }
    args.output.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if result["reusable_encrypted_evidence_metadata_verified"]:
        return 0
    checks = result.get("checks")
    if (result.get("durable_registry_revalidation_deferred_to_trusted_main_observer") is True
            and isinstance(checks, dict)
            and all(value is True for name, value in checks.items()
                    if name != "encrypted_artifact_retained")):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
