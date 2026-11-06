"""Read-only evidence reuse for an unchanged, previously authenticated Console.

A green CI is not authentication evidence. Require the exact upstream workflow,
job log, encrypted artifact, release ancestry and identical Console file blobs.
Never provision an operator, read secrets, decrypt captures, or certify the
whole product. An expired artifact fails closed (no unsafe fallback).
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
PRODUCTION = "https://ai-product-factory-console.vercel.app"
VISUAL_RUN = 42100072898
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_VIEWS = frozenset({
    "overview", "projects", "runs", "new-project", "human-gates",
    "run-detail", "work-queue", "agents", "orchestration", "evals",
    "deployments", "models-usage", "audit-log", "configuration",
})


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


def capture_receipt(log: str) -> dict | None:
    if not isinstance(log, str) or len(log) > 2_000_000:
        return None
    receipts = []
    for line in log.splitlines():
        marker = '{"status":"success","captured":'
        index = line.find(marker)
        if index >= 0:
            try:
                receipts.append(json.loads(line[index:]))
            except (ValueError, TypeError):
                return None
    if len(receipts) != 1 or not isinstance(receipts[0], dict):
        return None
    return receipts[0]


def assess(candidate: str, run: dict, artifacts: dict, jobs: dict,
           capture_log: str, comparison: dict, original_tree: dict,
           candidate_tree: dict) -> dict:
    if not exact_sha(candidate):
        raise ValueError("exact lowercase 40-character candidate SHA required")
    if not isinstance(run, dict) or not exact_sha(run.get("head_sha")):
        raise ValueError("exact authenticated source SHA missing")
    source = run["head_sha"]
    checks = {}
    checks["trusted_visual_run"] = (
        run.get("name") == "Authenticated Console visual evidence"
        and run.get("path") == VISUAL_WORKFLOW
        and run.get("event") == "push"
        and run.get("head_branch") == "main"
        and run.get("run_attempt") == 1
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
    )
    checks["source_ancestor"] = (
        isinstance(comparison, dict)
        and comparison.get("status") in ("ahead", "identical")
        and comparison.get("behind_by") == 0
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
    receipt = capture_receipt(capture_log)
    interaction = receipt.get("interactionEvidence", {}) if receipt else {}
    views = receipt.get("captured") if receipt else None
    navigation = interaction.get("navigation", []) if isinstance(interaction, dict) else []
    rbac = interaction.get("operatorRbac", {}) if isinstance(interaction, dict) else {}
    checks["authenticated_navigation_observed"] = (
        isinstance(views, list) and len(views) == 14
        and len(set(views)) == 14 and set(views) == REQUIRED_VIEWS
        and isinstance(navigation, list) and len(navigation) >= 10
        and all(isinstance(n, dict) and n.get("status") == 200 for n in navigation)
    )
    checks["operator_rbac_denial_observed"] = (
        isinstance(rbac, dict) and rbac.get("href") == "/admin/operators"
        and rbac.get("finalPath") == "/unauthorized"
        and rbac.get("status") == 200
    )
    checks["exact_served_console_deployment"] = (
        capture_log.count("Console deployment verified: " + PRODUCTION + " SHA " + source[:12]) >= 2
    )
    all_verified = all(checks.values())
    return {
        "schema": "factory-block1-authenticated-console-reuse-v1",
        "source_sha": source,
        "candidate_sha": candidate,
        "visual_run_id": VISUAL_RUN,
        "checks": checks,
        "reusable_within_unchanged_console_scope": all_verified,
        "signed_jwt_issuer_claims_independently_verified": False,
        "all_tenant_authorization_covered": False,
        "authn_authz_certified": False,
        "block1_certified": False,
        "release_authorized": False,
    }


def github(path: str, token: str, *, raw: bool = False):
    url = "https://api.github.com/repos/" + REPO + "/" + path
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "factory-block1-console-reuse-audit",
        **({"Authorization": "Bearer " + token} if token else {}),
    }
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=25) as response:
        data = response.read()
    return data.decode("utf-8", errors="replace") if raw else json.loads(data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--source-run", type=int, default=VISUAL_RUN)
    parser.add_argument("--output", type=Path, default=Path("block1-console-reuse-receipt.json"))
    args = parser.parse_args()
    if args.source_run != VISUAL_RUN or not exact_sha(args.candidate_sha):
        print('{"reusable_within_unchanged_console_scope":false,"block1_certified":false}')
        return 2
    token = os.environ.get("GITHUB_TOKEN", "")
    stage = "run"
    try:
        run = github("actions/runs/" + str(args.source_run), token)
        source = run["head_sha"]
        if not exact_sha(source):
            raise ValueError("invalid source sha")
        stage = "jobs"
        jobs = github("actions/runs/" + str(args.source_run) + "/jobs?per_page=100", token)
        capture_jobs = [j for j in jobs.get("jobs", []) if j.get("name") == "capture"]
        if len(capture_jobs) != 1:
            raise ValueError("capture job missing or duplicated")
        stage = "capture_log"
        capture_log = github("actions/jobs/" + str(capture_jobs[0]["id"]) + "/logs", token, raw=True)
        stage = "evidence_bundle"
        result = assess(
            args.candidate_sha,
            run,
            github("actions/runs/" + str(args.source_run) + "/artifacts?per_page=100", token),
            jobs,
            capture_log,
            github("compare/" + source + "..." + args.candidate_sha, token),
            github("git/trees/" + source + "?recursive=1", token),
            github("git/trees/" + args.candidate_sha + "?recursive=1", token),
        )
    except (KeyError, ValueError, TypeError, OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        result = {
            "schema": "factory-block1-authenticated-console-reuse-v1",
            "candidate_sha": args.candidate_sha,
            "error_type": type(exc).__name__,
            "error_stage": stage,
            "http_status": exc.code if isinstance(exc, urllib.error.HTTPError) else None,
            "reusable_within_unchanged_console_scope": False,
            "authn_authz_certified": False,
            "block1_certified": False,
            "release_authorized": False,
        }
    args.output.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["reusable_within_unchanged_console_scope"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
