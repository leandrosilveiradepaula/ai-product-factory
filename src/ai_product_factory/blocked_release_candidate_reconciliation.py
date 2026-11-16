"""Fail-closed, exact-SHA recovery from a blocked *development* release review.

No production release, no Github merge, no application database, no model
calls. Requires an independently authorized, service-role-only migration to
be deployed before --apply. Historical CI, reviewers and browser evidence
remain bound to their original SHA; never reused for a new candidate.
"""
from __future__ import annotations

import json
import re
import urllib.request
import urllib.error
from urllib.parse import quote

from .github_rest import GitHubRestAdapter
from .supabase_server import resolve_supabase_server_config

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_BRANCH = re.compile(r"factory/(?:change-set|journey)-[0-9a-f-]+\Z")
_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")


def _require(condition: bool, message: str) -> None:
    if condition is not True:
        raise PermissionError(message)


def _valid_sha(value: object) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _one(rows: object, label: str) -> dict:
    _require(isinstance(rows, list) and len(rows) == 1
             and isinstance(rows[0], dict), "unique " + label + " missing")
    return rows[0]


def _check_ancestry(github, old_sha: str, new_sha: str, *, bound: int) -> int:
    comparison = github.compare_commits(old_sha, new_sha)
    _require(isinstance(comparison, dict) and comparison.get("status") == "ahead"
             and comparison.get("behind_by") == 0
             and type(comparison.get("ahead_by")) is int
             and 1 <= comparison["ahead_by"] <= bound,
             "GitHub non-fast-forward or unbounded candidate")
    return comparison["ahead_by"]


def verify_blocked_release_candidate(
    github, *, project: dict, change_set: dict, run: dict,
    report: dict, control: dict, create_receipt: dict,
    last_reconciliation: dict | None,
) -> dict:
    """Read GitHub twice and bind BOTH original PR and prior run ancestry."""
    repository = project.get("repository")
    _require(isinstance(repository, str) and _REPO.fullmatch(repository) is not None
             and getattr(github, "repository", None) == repository
             and project.get("is_active") is True
             and project.get("project_kind") in ("existing", "greenfield"),
             "active project/source repository missing")
    branch = change_set.get("integration_branch")
    prior = run.get("candidate_commit")
    cs_id = change_set.get("id")
    run_id = run.get("id")
    _require(isinstance(branch, str) and _BRANCH.fullmatch(branch) is not None
             and _valid_sha(prior)
             and isinstance(cs_id, str) and _UUID.fullmatch(cs_id) is not None
             and isinstance(run_id, str) and _UUID.fullmatch(run_id) is not None
             and change_set.get("project_id") == project.get("id")
             and change_set.get("release_run_id") == run_id
             and change_set.get("status") == "ci_pending"
             and change_set.get("candidate_commit") == prior
             and change_set.get("lease_owner") is None
             and change_set.get("lease_expires_at") is None,
             "Change Set is not a bounded CI-pending integration")
    meta = change_set.get("metadata")
    runmeta = run.get("metadata")
    _require(isinstance(meta, dict) and isinstance(runmeta, dict)
             and run.get("status") == "release_policy_blocked"
             and run.get("branch_name") == branch
             and run.get("lease_owner") is None and run.get("lease_expires_at") is None
             and runmeta.get("source") == "change-set"
             and runmeta.get("change_set_id") == cs_id
             and control.get("state") == "running"
             and type(control.get("generation")) is int
             and control["generation"] > 0
             and runmeta.get("execution_generation") == control["generation"]
             and report.get("status") == "blocked"
             and report.get("candidate_commit") == prior
             and isinstance(report.get("report"), dict)
             and report["report"].get("release_state") == "blocked",
             "release and execution epoch are not quiescent")
    epoch = meta.get("integration_epoch_receipt")
    request = meta.get("integration_release_request")
    _require(isinstance(epoch, dict) and isinstance(request, dict)
             and epoch.get("candidate_commit") == prior
             and epoch.get("generation") == control["generation"]
             and epoch.get("project_id") == project.get("id")
             and type(epoch.get("wave")) is int and epoch["wave"] >= 2
             and request.get("candidate_commit") == prior
             and request.get("branch") == branch
             and type(request.get("pr_number")) is int and request["pr_number"] > 0,
             "original release request or wave binding is absent")
    pr_number = request["pr_number"]
    original = create_receipt.get("head_sha")
    _require(_valid_sha(original) and create_receipt.get("change_set_id") == cs_id
             and str(create_receipt.get("pr")) == str(pr_number),
             "immutable original PR receipt missing")
    if last_reconciliation is None:
        _require(prior == original, "unrecorded candidate transition")
    else:
        _require(isinstance(last_reconciliation, dict)
                 and last_reconciliation.get("change_set_id") == cs_id
                 and last_reconciliation.get("previous_commit") == original
                 and last_reconciliation.get("old_sha") == original
                 and last_reconciliation.get("new_sha") == prior
                 and last_reconciliation.get("candidate_commit") == prior
                 and last_reconciliation.get("compare_status") == "ahead",
                 "existing PR receipt does not form a valid lineage")
    pr = github.get_pull_request(pr_number)
    candidate = getattr(pr, "head_sha", None)
    _require(getattr(pr, "number", None) == pr_number
             and getattr(pr, "state", None) == "open"
             and getattr(pr, "merged", None) is False
             and getattr(pr, "draft", None) is False
             and getattr(pr, "head_repository", None) == repository
             and getattr(pr, "base_ref", None) == "main"
             and getattr(pr, "head_ref", None) == branch
             and _valid_sha(candidate) and candidate != prior
             and github.get_branch_sha(branch) == candidate,
             "current PR is not a nonproduction exact-SHA candidate")
    prior_ahead = _check_ancestry(github, prior, candidate, bound=100)
    original_ahead = _check_ancestry(github, original, candidate, bound=200)
    # All check-runs are bounded to the requested commit, and no partial or
    # non-GitHub-Actions check can be silently interpreted as a test pass.
    inventory = github._call(
        "GET", f"/repos/{repository}/commits/{candidate}/check-runs",
        query={"per_page": "100"},
    )
    checks = inventory.get("check_runs") if isinstance(inventory, dict) else None
    _require(isinstance(checks, list) and 1 <= len(checks) <= 50
             and inventory.get("total_count") == len(checks),
             "native CI check inventory incomplete")
    native = []
    for check in checks:
        _require(isinstance(check, dict)
                 and isinstance(check.get("name"), str) and bool(check["name"])
                 and check.get("head_sha") == candidate
                 and check.get("status") == "completed"
                 and check.get("conclusion") == "success"
                 and isinstance(check.get("app"), dict),
                 "incomplete or stale native CI job")
        if check["app"].get("slug") == "github-actions":
            native.append({"name": check["name"], "app": "github-actions",
                           "status": "completed", "conclusion": "success",
                           "head_sha": candidate})
    _require(len(native) >= 1, "no passing GitHub Actions checks")
    runs = github._call(
        "GET", f"/repos/{repository}/actions/runs",
        query={"head_sha": candidate, "per_page": "100"},
    )
    candidates = runs.get("workflow_runs") if isinstance(runs, dict) else None
    _require(isinstance(candidates, list) and len(candidates) <= 100
             and isinstance(runs.get("total_count"), int)
             and runs["total_count"] == len(candidates),
             "native workflow run inventory incomplete")
    matching = [r for r in candidates if isinstance(r, dict)
                and r.get("head_sha") == candidate
                and r.get("head_branch") == branch
                and r.get("path") == ".github/workflows/validate.yml"
                and r.get("status") == "completed"
                and r.get("conclusion") == "success"
                and (r.get("repository") or {}).get("full_name") == repository
                and type(r.get("id")) is int and r["id"] > 0]
    _require(len(matching) >= 1, "no passing native workflow on the integration ref")
    winning = max(matching, key=lambda r: r["id"])
    # Re-read identity after CI. RPC holds the Control Plane epoch lock, while
    # a moved GitHub PR or ref is not treated as a successful reconciliation.
    again = github.get_pull_request(pr_number)
    _require(getattr(again, "head_sha", None) == candidate
             and getattr(again, "head_ref", None) == branch
             and getattr(again, "state", None) == "open"
             and getattr(again, "merged", None) is False
             and getattr(again, "draft", None) is False
             and github.get_branch_sha(branch) == candidate,
             "PR moved after independently verified native CI")
    return {
        "source": "github_actions_exact_sha",
        "repository": repository,
        "pr_number": pr_number,
        "pr_head_sha": candidate, "branch_head_sha": candidate,
        "pr_state": "open", "pr_merged": False, "pr_draft": False,
        "pr_base": "main", "branch": branch,
        "original_head_sha": original, "old_sha": original, "new_sha": candidate,
        "prior_candidate_commit": prior,
        "prior_compare_status": "ahead", "prior_ahead_by": prior_ahead,
        "prior_behind_by": 0,
        "compare_status": "ahead", "ahead_by": original_ahead,
        "behind_by": 0,
        "ci_sha": candidate, "ci_run_id": winning["id"],
        "ci_checks": native,
        "release_authorized": False,
        "historical_approvals_replayed": False,
    }


class BlockedCandidateStore:
    """Server-only Control Plane reader and one gated RPC; no raw SQL writes."""

    def __init__(self, *, url: str | None = None,
                 secret_key: str | None = None,
                 service_role_key: str | None = None):
        cfg = resolve_supabase_server_config(
            url=url, secret_key=secret_key, service_role_key=service_role_key)
        self.url, self.headers = cfg.url, cfg.headers

    def get(self, table: str, query: str) -> list[dict]:
        request = urllib.request.Request(
            f"{self.url}/rest/v1/{table}?{query}",
            headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                value = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError("Control Plane read rejected (" + str(exc.code) + ")") from exc
        if not isinstance(value, list) or len(value) > 20:
            raise RuntimeError("unbounded or invalid Control Plane response")
        return value

    def rpc(self, name: str, payload: dict) -> dict:
        _require(name == "factory_reconcile_blocked_release_candidate_once_v1",
                 "unapproved Control Plane operation")
        request = urllib.request.Request(
            f"{self.url}/rest/v1/rpc/{name}",
            data=json.dumps(payload).encode("utf-8"),
            headers={**self.headers, "Content-Type": "application/json"},
            method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                value = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError("Control Plane candidate RPC rejected ("+str(exc.code)+")") from exc
        if not isinstance(value, dict):
            raise RuntimeError("invalid Control Plane candidate receipt")
        return value


def reconcile_one(change_set_id: str, run_id: str, *,
                  apply: bool = False, store=None, github_factory=None) -> dict:
    """A dry-run by default. --apply requires installed, audited migration."""
    _require(isinstance(change_set_id, str) and _UUID.fullmatch(change_set_id) is not None
             and isinstance(run_id, str) and _UUID.fullmatch(run_id) is not None,
             "full Change Set and run IDs required")
    db = store if store is not None else BlockedCandidateStore()
    enc_cs, enc_run = quote(change_set_id, safe=""), quote(run_id, safe="")
    cs = _one(db.get("factory_change_sets",
        "select=id,project_id,release_run_id,root_task_id,status,candidate_commit,"
        "integration_branch,metadata,lease_owner,lease_expires_at"
        "&id=eq."+enc_cs+"&limit=2"), "Change Set")
    run = _one(db.get("factory_runs",
        "select=id,task_id,status,candidate_commit,branch_name,metadata,"
        "lease_owner,lease_expires_at&id=eq."+enc_run+"&limit=2"), "delivery run")
    project_id = cs.get("project_id")
    _require(isinstance(project_id, str) and _UUID.fullmatch(project_id) is not None,
             "project identity invalid")
    project = _one(db.get("factory_projects",
        "select=id,project_kind,is_active,repository&id=eq."+quote(project_id)+"&limit=2"), "project")
    control = _one(db.get("factory_project_execution_controls",
        "select=project_id,state,generation&project_id=eq."+quote(project_id)+"&limit=2"),
        "execution epoch")
    report = _one(db.get("factory_release_reports",
        "select=status,candidate_commit,report&run_id=eq."+enc_run+"&limit=2"),
        "blocked release report")
    create = _one(db.get("factory_tool_usage",
        "select=metadata&run_id=eq."+enc_run
        +"&operation=eq.create_pr&order=created_at.desc,id.desc&limit=2"),
        "immutable create_pr receipt")["metadata"]
    reconciliations = db.get("factory_tool_usage",
        "select=metadata&run_id=eq."+enc_run
        +"&operation=eq.reconcile_pr_candidate&order=created_at.desc,id.desc&limit=1")
    _require(len(reconciliations) <= 1, "ambiguous reconciliation receipt")
    previous = reconciliations[0]["metadata"] if reconciliations else None
    repository = project.get("repository")
    github = (github_factory(repository) if github_factory
              else GitHubRestAdapter(repository=repository))
    evidence = verify_blocked_release_candidate(
        github, project=project, change_set=cs, run=run, report=report,
        control=control, create_receipt=create, last_reconciliation=previous)
    result = {
        "status": "preflight_verified",
        "change_set_id": change_set_id, "run_id": run_id,
        "candidate_commit": evidence["new_sha"],
        "previous_commit": run["candidate_commit"],
        "pr_number": evidence["pr_number"],
        "exact_sha_ci_run_id": evidence["ci_run_id"],
        "release_authorized": False,
        "historical_approvals_replayed": False, "writes": 0,
    }
    if not apply:
        return result
    payload = {
        "p_change_set_id": change_set_id, "p_run_id": run_id,
        "p_pr_number": evidence["pr_number"],
        "p_prior_candidate": run["candidate_commit"],
        "p_new_candidate": evidence["new_sha"],
        "p_github_evidence": evidence,
    }
    receipt = db.rpc("factory_reconcile_blocked_release_candidate_once_v1", payload)
    _require(receipt.get("status") == "ci_pending"
             and receipt.get("run_id") == run_id
             and receipt.get("change_set_id") == change_set_id
             and receipt.get("candidate_commit") == evidence["new_sha"]
             and receipt.get("previous_commit") == run["candidate_commit"]
             and receipt.get("release_authorized") is False
             and receipt.get("fresh_ci_required") is True
             and receipt.get("fresh_specialists_required") is True
             and receipt.get("fresh_preview_required") is True,
             "postreview candidate CAS receipt unverified")
    return {**result, **receipt}
