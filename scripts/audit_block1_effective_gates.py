"""Read-only audit of the *effective* GitHub release gates.

A green validate job or a policy YAML file does not prove branch protection.
Read active GitHub rulesets for the repository, check actual enforced rules,
and emit explicit blockers. Never changes repository settings.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request

REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
REQUIRED = frozenset({"test", "factory-acceptance"})
POSTGRES_NAMES = frozenset({"product-readiness-postgres", "PostgreSQL QA", "postgres-qa"})


def assess(rulesets: object) -> dict:
    if not isinstance(rulesets, list):
        raise ValueError("ruleset inventory must be a list")
    active = [r for r in rulesets if isinstance(r, dict)
              and r.get("enforcement") == "active"]
    checks, pr_required, strict, reviews, block_force, block_delete = set(), False, False, 0, False, False
    for rule_set in active:
        for rule in rule_set.get("rules", []):
            if not isinstance(rule, dict):
                continue
            kind, params = rule.get("type"), rule.get("parameters") or {}
            if kind == "required_status_checks":
                checks.update(c.get("context") for c in params.get("required_status_checks", [])
                              if isinstance(c, dict) and isinstance(c.get("context"), str))
                strict |= params.get("strict_required_status_checks_policy") is True
            elif kind == "pull_request":
                pr_required = True
                reviews = max(reviews, params.get("required_approving_review_count", 0)
                              if type(params.get("required_approving_review_count", 0)) is int else 0)
            elif kind == "non_fast_forward":
                block_force = True
            elif kind == "deletion":
                block_delete = True
    blockers = []
    if not active:
        blockers.append("no_active_ruleset")
    if not pr_required:
        blockers.append("pull_request_not_required")
    if not REQUIRED.issubset(checks):
        blockers.append("required_validation_checks_missing")
    if not checks.intersection(POSTGRES_NAMES):
        blockers.append("postgres_qa_not_enforced")
    if not strict:
        blockers.append("required_checks_not_strict")
    if reviews < 1:
        blockers.append("approval_count_zero")
    if not block_force:
        blockers.append("force_push_not_blocked")
    if not block_delete:
        blockers.append("branch_delete_not_blocked")
    return {"scope": "effective_repository_ruleset_audit_not_product_certification",
            "active_ruleset_count": len(active), "required_status_checks": sorted(checks),
            "pull_request_required": pr_required, "approval_count": reviews,
            "strict_status_checks": strict, "force_push_blocked": block_force,
            "deletion_blocked": block_delete, "blockers": blockers,
            "regression_gates_certified": False, "writes": 0, "paid_calls": 0}


def github_rulesets(repository: str, token: str) -> list:
    if not REPO.fullmatch(repository):
        raise ValueError("invalid repository")
    if not token:
        raise ValueError("read-only GitHub token required")
    url = "https://api.github.com/repos/" + repository + "/rulesets?includes_parents=true"
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json", "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "factory-block1-gates-audit"})
    with urllib.request.urlopen(request, timeout=15) as response:
        summary = json.load(response)
    if not isinstance(summary, list):
        raise ValueError("invalid GitHub ruleset response")
    full = []
    for row in summary:
        if not isinstance(row, dict) or type(row.get("id")) is not int:
            raise ValueError("invalid ruleset summary")
        detail_url = "https://api.github.com/repos/" + repository + "/rulesets/" + str(row["id"])
        request = urllib.request.Request(detail_url, headers={
            "Accept": "application/vnd.github+json", "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "factory-block1-gates-audit"})
        with urllib.request.urlopen(request, timeout=15) as response:
            detail = json.load(response)
        if not isinstance(detail, dict) or detail.get("id") != row["id"]:
            raise ValueError("ruleset detail identity mismatch")
        full.append(detail)
    return full


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    args = parser.parse_args()
    try:
        result = assess(github_rulesets(args.repository, os.environ.get("GITHUB_TOKEN", "")))
    except (ValueError, OSError, TimeoutError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "unverified", "error_type": type(exc).__name__,
                          "regression_gates_certified": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    # Known policy gaps are actionable, not a reason to suppress the inventory.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
