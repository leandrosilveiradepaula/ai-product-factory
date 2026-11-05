"""Read-only verifier for Block 1 GitHub evidence at an exact main SHA.

No credentials are printed, no release is authorized, and missing evidence fails closed.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request

REPO = "leandrosilveiradepaula/ai-product-factory"
RULESET = 24457514
WORKFLOWS = {
    "validate": "validate",
    "console": "Console validation",
    "browser": "Authenticated Console visual evidence",
}


def fetch(path: str, token: str) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/repos/" + REPO + "/" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "factory-block1-readonly-audit",
            **({"Authorization": "Bearer " + token} if token else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def assess(sha: str, runs: dict, ruleset: dict, artifacts: list) -> dict:
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("exact lowercase commit SHA required")
    results = {}
    for key, name in WORKFLOWS.items():
        run = runs.get(key) or {}
        results[key] = (
            run.get("name") == name
            and run.get("head_sha") == sha
            and run.get("status") == "completed"
            and run.get("conclusion") == "success"
        )
    results["browser_artifact"] = results["browser"] and any(
        a.get("name") == "authenticated-console-" + str(runs["browser"].get("id"))
        and a.get("expired") is False
        and a.get("size_in_bytes", 0) > 0
        for a in artifacts
    )
    rules = {r.get("type"): r.get("parameters", {}) for r in ruleset.get("rules", [])}
    pr = rules.get("pull_request", {})
    checks = rules.get("required_status_checks", {})
    required = {c.get("context") for c in checks.get("required_status_checks", [])}
    results["ruleset_human_review"] = (
        ruleset.get("enforcement") == "active"
        and pr.get("required_approving_review_count", 0) >= 1
    )
    results["ruleset_strict_checks"] = (
        ruleset.get("enforcement") == "active"
        and checks.get("strict_required_status_checks_policy") is True
        and {"test", "factory-acceptance"}.issubset(required)
    )
    return {
        "schema": "factory-block1-live-evidence-v1",
        "sha": sha,
        "checks": results,
        "all_verified": all(results.values()),
        "block1_certified": False,
        "release_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument("--validate-run", type=int, required=True)
    parser.add_argument("--console-run", type=int, required=True)
    parser.add_argument("--browser-run", type=int, required=True)
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN", "")
    try:
        runs = {
            "validate": fetch(f"actions/runs/{args.validate_run}", token),
            "console": fetch(f"actions/runs/{args.console_run}", token),
            "browser": fetch(f"actions/runs/{args.browser_run}", token),
        }
        ruleset = fetch(f"rulesets/{RULESET}", token)
        artifacts = fetch(f"actions/runs/{args.browser_run}/artifacts", token).get("artifacts", [])
        report = assess(args.sha, runs, ruleset, artifacts)
    except (ValueError, OSError, urllib.error.URLError, KeyError) as exc:
        print(json.dumps({"error": type(exc).__name__, "all_verified": False, "block1_certified": False}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["all_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
