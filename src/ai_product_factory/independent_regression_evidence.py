"""Fail-closed effective regression-gate evidence from GitHub rulesets."""
from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping

from .product_readiness_certification import VerifiedCriterionEvidence

REPOSITORY = "leandrosilveiradepaula/ai-product-factory"
OWNER_WORKFLOW = ".github/workflows/autonomous-runner.yml"
SHA = re.compile(r"[0-9a-f]{40}\Z")
REQUIRED_CHECKS = frozenset({"test", "factory-acceptance", "PostgreSQL QA"})


class RegressionEvidenceBlocked(RuntimeError):
    pass


def require(value: bool, code: str) -> None:
    if not value:
        raise RegressionEvidenceBlocked(code)


def _effective_rules(rulesets: object) -> dict:
    require(isinstance(rulesets, list) and 0 < len(rulesets) <= 20, "regression_rulesets_unavailable")
    checks: set[str] = set()
    pull_request = strict = block_force = block_delete = False
    approvals = 0
    active = 0
    for ruleset in rulesets:
        require(isinstance(ruleset, dict), "regression_ruleset_invalid")
        if ruleset.get("enforcement") != "active":
            continue
        active += 1
        rules = ruleset.get("rules")
        require(isinstance(rules, list), "regression_rules_missing")
        for rule in rules:
            require(isinstance(rule, dict), "regression_rule_invalid")
            kind, parameters = rule.get("type"), rule.get("parameters") or {}
            require(isinstance(parameters, dict), "regression_rule_parameters_invalid")
            if kind == "required_status_checks":
                status = parameters.get("required_status_checks")
                require(isinstance(status, list), "regression_status_checks_invalid")
                checks.update(row.get("context") for row in status if isinstance(row, dict) and isinstance(row.get("context"), str))
                strict |= parameters.get("strict_required_status_checks_policy") is True
            elif kind == "pull_request":
                pull_request = True
                count = parameters.get("required_approving_review_count", 0)
                approvals = max(approvals, count if type(count) is int else -1)
            elif kind == "non_fast_forward":
                block_force = True
            elif kind == "deletion":
                block_delete = True
    require(active > 0 and pull_request and strict and block_force and block_delete, "regression_protection_incomplete")
    require(approvals >= 1, "regression_human_review_not_required")
    require(REQUIRED_CHECKS.issubset(checks), "regression_required_checks_incomplete")
    return {"active_rulesets": active, "required_checks": sorted(checks), "required_approvals": approvals}


def verify_regression_gates(*, repository: str, assessed_commit: str, github_get: Callable[[str], object], environment: Mapping[str, str] | None = None) -> VerifiedCriterionEvidence:
    env = os.environ if environment is None else environment
    require(repository == REPOSITORY and isinstance(assessed_commit, str) and SHA.fullmatch(assessed_commit), "regression_repository_or_sha_invalid")
    require(env.get("GITHUB_ACTIONS") == "true" and env.get("GITHUB_REPOSITORY") == REPOSITORY and env.get("GITHUB_EVENT_NAME") == "workflow_run" and env.get("GITHUB_REF") == "refs/heads/main" and env.get("GITHUB_WORKFLOW_REF") == REPOSITORY + "/" + OWNER_WORKFLOW + "@refs/heads/main", "regression_runner_identity_invalid")
    run_id = env.get("GITHUB_RUN_ID", "")
    require(run_id.isdecimal(), "regression_runner_id_invalid")
    prefix = "/repos/" + REPOSITORY
    main = github_get(prefix + "/git/ref/heads/main")
    current = github_get(prefix + "/actions/runs/" + run_id)
    require(isinstance(main, dict) and (main.get("object") or {}).get("sha") == assessed_commit, "regression_main_drift")
    require(isinstance(current, dict) and current.get("id") == int(run_id) and current.get("name") == "Factory autonomous runner" and current.get("path") == OWNER_WORKFLOW and current.get("event") == "workflow_run" and current.get("head_sha") == assessed_commit and current.get("head_branch") == "main" and current.get("status") == "completed" and current.get("conclusion") == "success" and current.get("run_attempt") == 1, "regression_runner_unbound")
    summary = github_get(prefix + "/rulesets?includes_parents=true")
    require(isinstance(summary, list) and summary, "regression_ruleset_summary_invalid")
    details = []
    for row in summary:
        require(isinstance(row, dict) and type(row.get("id")) is int, "regression_ruleset_identity_invalid")
        detail = github_get(prefix + "/rulesets/" + str(row["id"]))
        require(isinstance(detail, dict) and detail.get("id") == row["id"], "regression_ruleset_detail_unbound")
        details.append(detail)
    receipt = _effective_rules(details)
    latest = github_get(prefix + "/git/ref/heads/main")
    require(isinstance(latest, dict) and (latest.get("object") or {}).get("sha") == assessed_commit, "regression_main_changed")
    return VerifiedCriterionEvidence(domain="test_strategy", criterion="regression_gates", repository=repository, assessed_commit=assessed_commit, verification_state="executed", source="github-effective-protected-regression-gates:" + ",".join(receipt["required_checks"]), evidence=("https://github.com/" + repository + "/actions/runs/" + run_id + "#sha=" + assessed_commit,), retained_receipt=receipt)
