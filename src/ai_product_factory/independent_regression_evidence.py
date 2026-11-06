"""Fail-closed effective regression-gate evidence from GitHub rulesets."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
from pathlib import Path
from collections.abc import Callable, Mapping

from .product_readiness_certification import VerifiedCriterionEvidence

REPOSITORY = "leandrosilveiradepaula/ai-product-factory"
OWNER_WORKFLOW = ".github/workflows/autonomous-runner.yml"
SHA = re.compile(r"[0-9a-f]{40}\Z")
REQUIRED_CHECKS = frozenset({"test", "factory-acceptance"})
POSTGRES_WORKFLOW = "Manual project lifecycle PostgreSQL QA"
POSTGRES_JOBS = frozenset({"isolated-postgres", "change-set-guard-postgres", "project-release-atomic-postgres", "preview-integration-postgres"})


class RegressionEvidenceBlocked(RuntimeError):
    pass


def require(value: bool, code: str) -> None:
    if not value:
        raise RegressionEvidenceBlocked(code)


def _retrying_get(github_get: Callable[[str], object]) -> Callable[[str], object]:
    """Retry only transient GitHub read failures; every bad receipt still blocks."""
    def get(path: str) -> object:
        for attempt in range(3):
            try:
                return github_get(path)
            except urllib.error.HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise
                time.sleep(0.2 * (attempt + 1))
        raise AssertionError("unreachable")
    return get


def _effective_rules(rulesets: object, *, default_branch: str) -> dict:
    require(isinstance(rulesets, list) and 0 < len(rulesets) <= 20, "regression_rulesets_unavailable")
    checks: set[str] = set()
    pull_request = strict = block_force = block_delete = False
    bypass_free = True
    active = 0
    for ruleset in rulesets:
        require(isinstance(ruleset, dict), "regression_ruleset_invalid")
        if ruleset.get("enforcement") != "active":
            continue
        conditions = ruleset.get("conditions") or {}
        refs = conditions.get("ref_name") if isinstance(conditions, dict) else None
        includes = refs.get("include") if isinstance(refs, dict) else None
        if not isinstance(includes, list) or ("~DEFAULT_BRANCH" not in includes and default_branch not in includes):
            continue
        if ruleset.get("bypass_actors") not in ([], None) or ruleset.get("current_user_can_bypass") not in ("never", None):
            bypass_free = False
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
            elif kind == "non_fast_forward":
                block_force = True
            elif kind == "deletion":
                block_delete = True
    require(active > 0 and pull_request and strict and block_force and block_delete and bypass_free, "regression_protection_incomplete")
    require(REQUIRED_CHECKS.issubset(checks), "regression_required_checks_incomplete")
    return {"active_rulesets": active, "required_checks": sorted(checks), "single_maintainer_merge_gate": True, "bypass_free": bypass_free}

def _commit_tree(github_get: Callable[[str], object], prefix: str, sha: str) -> str:
    row = github_get(prefix + "/git/commits/" + sha)
    tree = row.get("tree") if isinstance(row, dict) else None
    value = tree.get("sha") if isinstance(tree, dict) else None
    require(isinstance(value, str) and SHA.fullmatch(value), "regression_commit_tree_invalid")
    return value


def _postgres_qa(github_get: Callable[[str], object], prefix: str, sha: str) -> dict:
    runs = github_get(prefix + "/actions/workflows/manual-project-control-postgres.yml/runs?event=pull_request&status=success&per_page=100")
    rows = runs.get("workflow_runs") if isinstance(runs, dict) else None
    require(isinstance(rows, list) and 0 < len(rows) <= 100, "regression_postgres_inventory_invalid")
    assessed_tree = _commit_tree(github_get, prefix, sha)
    candidates = []
    for row in rows:
        candidate_sha = row.get("head_sha") if isinstance(row, dict) else None
        if not (isinstance(row, dict) and row.get("name") == POSTGRES_WORKFLOW and row.get("event") == "pull_request" and row.get("status") == "completed" and row.get("conclusion") == "success" and type(row.get("id")) is int and isinstance(candidate_sha, str) and SHA.fullmatch(candidate_sha)):
            continue
        if _commit_tree(github_get, prefix, candidate_sha) == assessed_tree:
            candidates.append(row)
    require(len(candidates) == 1, "regression_postgres_matching_tree_missing")
    run_id = candidates[0]["id"]
    candidate_sha = candidates[0]["head_sha"]
    jobs = github_get(prefix + "/actions/runs/" + str(run_id) + "/jobs?per_page=100")
    rows = jobs.get("jobs") if isinstance(jobs, dict) else None
    names = {row.get("name") for row in rows if isinstance(row, dict) and row.get("run_id") == run_id and row.get("head_sha") == candidate_sha and row.get("status") == "completed" and row.get("conclusion") == "success"}
    require(isinstance(rows, list) and POSTGRES_JOBS.issubset(names), "regression_postgres_jobs_invalid")
    return {"run_id": run_id, "source_sha": candidate_sha, "tree_oid": assessed_tree}


def _upstream_validate_event(event_payload: Mapping[str, object], *, assessed_commit: str) -> int:
    run = event_payload.get("workflow_run")
    require(isinstance(run, dict), "regression_upstream_event_missing")
    require(run.get("name") == "validate" and run.get("path") == ".github/workflows/validate.yml" and run.get("event") == "push" and run.get("status") == "completed" and run.get("conclusion") == "success" and run.get("head_sha") == assessed_commit and run.get("head_branch") == "main", "regression_upstream_validate_invalid")
    repository = run.get("repository")
    require(isinstance(repository, dict) and repository.get("full_name") == REPOSITORY, "regression_upstream_repository_invalid")
    run_id = run.get("id")
    require(type(run_id) is int and run_id > 0 and run.get("run_attempt") == 1, "regression_upstream_run_invalid")
    return run_id


def _event_payload(env: Mapping[str, str], payload: Mapping[str, object] | None) -> Mapping[str, object]:
    if payload is not None:
        return payload
    path = env.get("GITHUB_EVENT_PATH")
    require(isinstance(path, str) and path, "regression_event_path_missing")
    raw = Path(path).read_bytes()
    require(0 < len(raw) <= 256_000, "regression_event_payload_size_invalid")
    value = json.loads(raw)
    require(isinstance(value, dict), "regression_event_payload_invalid")
    return value


def verify_regression_gates(*, repository: str, assessed_commit: str, github_get: Callable[[str], object], environment: Mapping[str, str] | None = None, event_payload: Mapping[str, object] | None = None) -> VerifiedCriterionEvidence:
    env = os.environ if environment is None else environment
    require(repository == REPOSITORY and isinstance(assessed_commit, str) and SHA.fullmatch(assessed_commit), "regression_repository_or_sha_invalid")
    require(env.get("GITHUB_ACTIONS") == "true" and env.get("GITHUB_REPOSITORY") == REPOSITORY and env.get("GITHUB_EVENT_NAME") == "workflow_run" and env.get("GITHUB_REF") == "refs/heads/main" and env.get("GITHUB_WORKFLOW_REF") == REPOSITORY + "/" + OWNER_WORKFLOW + "@refs/heads/main", "regression_runner_identity_invalid")
    run_id = env.get("GITHUB_RUN_ID", "")
    require(run_id.isdecimal(), "regression_runner_id_invalid")
    upstream_run_id = _upstream_validate_event(_event_payload(env, event_payload), assessed_commit=assessed_commit)
    prefix = "/repos/" + REPOSITORY
    github_get = _retrying_get(github_get)
    repo = github_get(prefix)
    branch = repo.get("default_branch") if isinstance(repo, dict) else None
    require(branch == "main", "regression_default_branch_invalid")
    main = github_get(prefix + "/git/ref/heads/" + branch)
    current = github_get(prefix + "/actions/runs/" + run_id)
    require(isinstance(main, dict) and (main.get("object") or {}).get("sha") == assessed_commit, "regression_main_drift")
    require(isinstance(current, dict) and current.get("id") == int(run_id) and current.get("name") == "Factory autonomous runner" and current.get("path") == OWNER_WORKFLOW and current.get("event") == "workflow_run" and current.get("head_sha") == assessed_commit and current.get("head_branch") == "main" and current.get("status") in ("queued", "in_progress", "completed") and (current.get("status") != "completed" or current.get("conclusion") == "success") and current.get("run_attempt") == 1, "regression_runner_unbound")
    summary = github_get(prefix + "/rulesets?includes_parents=true")
    require(isinstance(summary, list) and summary, "regression_ruleset_summary_invalid")
    details = []
    for row in summary:
        require(isinstance(row, dict) and type(row.get("id")) is int, "regression_ruleset_identity_invalid")
        detail = github_get(prefix + "/rulesets/" + str(row["id"]))
        require(isinstance(detail, dict) and detail.get("id") == row["id"], "regression_ruleset_detail_unbound")
        details.append(detail)
    receipt = _effective_rules(details, default_branch=branch)
    receipt["upstream_validate_run_id"] = upstream_run_id
    receipt["postgres_qa"] = _postgres_qa(github_get, prefix, assessed_commit)
    latest = github_get(prefix + "/git/ref/heads/" + branch)
    require(isinstance(latest, dict) and (latest.get("object") or {}).get("sha") == assessed_commit, "regression_main_changed")
    return VerifiedCriterionEvidence(domain="test_strategy", criterion="regression_gates", repository=repository, assessed_commit=assessed_commit, verification_state="executed", source="github-effective-protected-regression-gates:" + ",".join(receipt["required_checks"]), evidence=("https://github.com/" + repository + "/actions/runs/" + run_id + "#sha=" + assessed_commit,), retained_receipt=receipt)
