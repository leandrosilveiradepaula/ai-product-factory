"""Read-only evidence of the single-owner GitHub merge gate, never authorization for release.

GitHub records *which account* merged; the API alone cannot prove a human clicked
the button rather than acting through that account's credential. This distinction
is deliberately explicit and cannot be overridden by a green CI status.
"""
from __future__ import annotations

import argparse
import json
import os
from urllib.request import Request, urlopen

REPO = "leandrosilveiradepaula/ai-product-factory"
OWNER = "leandrosilveiradepaula"
RULESET_ID = 24457514
REQUIRED = {"test", "factory-acceptance"}


def assess(sha: str, pr: dict, ruleset: dict, main: dict) -> dict:
    if not isinstance(sha, str) or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("exact lowercase commit SHA required")
    rules = {r.get("type"): r.get("parameters", {}) for r in ruleset.get("rules", []) if isinstance(r, dict)}
    checks = rules.get("required_status_checks", {})
    required = {c.get("context") for c in checks.get("required_status_checks", []) if isinstance(c, dict)}
    pull = rules.get("pull_request")
    targets = ruleset.get("conditions", {}).get("ref_name", {}).get("include", [])
    policy = (
        ruleset.get("enforcement") == "active"
        and ruleset.get("target") == "branch"
        and (targets == ["~DEFAULT_BRANCH"] or "refs/heads/main" in targets)
        and pull is not None
        and pull.get("required_approving_review_count") == 0
        and checks.get("strict_required_status_checks_policy") is True
        and REQUIRED.issubset(required)
        and "non_fast_forward" in rules
        and "deletion" in rules
        and ruleset.get("bypass_actors") == []
    )
    actor = pr.get("merged_by") or {}
    owner_merge = (
        pr.get("merged") is True
        and isinstance(pr.get("merged_at"), str)
        and bool(pr.get("merged_at"))
        and pr.get("merge_commit_sha") == sha
        and pr.get("base", {}).get("ref") == "main"
        and pr.get("base", {}).get("repo", {}).get("full_name") == REPO
        and actor.get("login") == OWNER
        and actor.get("type") == "User"
    )
    exact_main = main.get("name") == "main" and main.get("commit", {}).get("sha") == sha
    return {
        "schema": "factory-block1-owner-merge-observation-v1",
        "sha": sha,
        "single_owner_ruleset_observed": policy,
        "owner_account_merge_observed": owner_merge,
        "exact_main_sha_observed": exact_main,
        "observation_verified": bool(policy and owner_merge and exact_main),
        "physical_human_action_proven": False,
        "automation_absence_proven": False,
        "block1_certified": False,
        "release_authorized": False,
    }


def get(path: str, token: str) -> dict:
    request = Request(
        "https://api.github.com/repos/" + REPO + "/" + path,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "factory-block1-owner-merge-readonly",
                 **({"Authorization": "Bearer " + token} if token else {})},
    )
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument("--pr", type=int, required=True)
    args = parser.parse_args()
    if args.pr <= 0:
        raise SystemExit("positive PR required")
    try:
        report = assess(
            args.sha,
            get("pulls/" + str(args.pr), os.environ.get("GITHUB_TOKEN", "")),
            get("rulesets/" + str(RULESET_ID), os.environ.get("GITHUB_TOKEN", "")),
            get("branches/main", os.environ.get("GITHUB_TOKEN", "")),
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"schema": "factory-block1-owner-merge-observation-v1",
                          "error": type(exc).__name__,
                          "observation_verified": False,
                          "block1_certified": False}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["observation_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
