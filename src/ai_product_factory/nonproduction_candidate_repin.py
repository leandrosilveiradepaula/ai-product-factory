"""Fail-closed reconciliation for declared existing-project candidates.

The Control Plane manifest is the only policy source. This module never
discovers a workflow from arbitrary GitHub checks and never creates work: it
only advances an already declared, quiescent non-production candidate through
the existing CAS RPC.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Callable
from urllib import parse, request

from .github_auth import resolve_github_token
from .github_rest import GitHubRestAdapter
from .pinned_nonproduction_target import PinnedNonproductionTarget
from .supabase_server import resolve_supabase_server_config


_SHA = re.compile(r"^[a-f0-9]{40}$")
_WORKFLOW_PATH = re.compile(r"^\.github/workflows/[A-Za-z0-9_.-]{1,180}\.(?:yml|yaml)$")
_WORKFLOW_NAME = re.compile(r"^[^\x00-\x1f]{1,160}$")
_MAX_PROJECTS = 5
_PAGE_SIZE = 20


@dataclass(frozen=True)
class NativeCIWorkflowPolicy:
    """A repository-owned Actions workflow required for a candidate repin."""

    workflow_path: str
    workflow_name: str
    workflow_id: int
    event: str

    @classmethod
    def parse(cls, value: object) -> "NativeCIWorkflowPolicy":
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise PermissionError("existing candidate native CI policy is missing or unsupported")
        path, name, workflow_id, event = (value.get("workflow_path"), value.get("workflow_name"),
                                          value.get("workflow_id"), value.get("event"))
        if (not isinstance(path, str) or not _WORKFLOW_PATH.fullmatch(path)
                or not isinstance(name, str) or not _WORKFLOW_NAME.fullmatch(name)
                or type(workflow_id) is not int or workflow_id < 1
                or event not in {"pull_request", "push"}):
            raise PermissionError("existing candidate native CI policy is invalid")
        return cls(workflow_path=path, workflow_name=name, workflow_id=workflow_id, event=event)


@dataclass(frozen=True)
class ExistingCandidatePolicy:
    target: PinnedNonproductionTarget
    ci: NativeCIWorkflowPolicy

    @classmethod
    def parse(cls, manifest: object, *, repository: object) -> "ExistingCandidatePolicy":
        if not isinstance(manifest, dict) or not isinstance(repository, str):
            raise PermissionError("existing project manifest is invalid")
        target_raw = manifest.get("delivery_target")
        target = PinnedNonproductionTarget.parse(target_raw, repository=repository)
        if not isinstance(target_raw, dict):
            raise PermissionError("existing project delivery target is invalid")
        repin = target_raw.get("repin_policy")
        if not isinstance(repin, dict) or repin.get("schema_version") != 1 or repin.get("enabled") is not True:
            raise PermissionError("existing project candidate repin is not explicitly enabled")
        return cls(target=target, ci=NativeCIWorkflowPolicy.parse(repin.get("native_ci")))


def _workflow_identity(row: dict) -> tuple[int, int, int]:
    """Return a total ordering for retries; incomplete identities fail closed."""
    workflow_id, run_number, attempt, run_id = (row.get("workflow_id"), row.get("run_number"),
                                                  row.get("run_attempt"), row.get("id"))
    if any(type(value) is not int or value < 1 for value in (workflow_id, run_number, attempt, run_id)):
        raise PermissionError("native CI workflow run identity is incomplete")
    return run_number, attempt, run_id


def _select_latest_native_ci(rows: object, *, policy: NativeCIWorkflowPolicy,
                             branch: str, sha: str) -> dict:
    if not isinstance(rows, dict) or not isinstance(rows.get("workflow_runs"), list):
        raise PermissionError("native CI workflow inventory is incomplete")
    total = rows.get("total_count")
    if type(total) is not int or total < 0 or total > 100 or total != len(rows["workflow_runs"]):
        raise PermissionError("native CI workflow inventory is truncated or ambiguous")
    candidates: list[dict] = []
    for row in rows["workflow_runs"]:
        if not isinstance(row, dict):
            raise PermissionError("native CI workflow inventory is malformed")
        if (row.get("head_sha") == sha and row.get("head_branch") == branch
                and row.get("path") == policy.workflow_path and row.get("name") == policy.workflow_name
                and row.get("workflow_id") == policy.workflow_id and row.get("event") == policy.event):
            _workflow_identity(row)
            candidates.append(row)
    if not candidates:
        raise PermissionError("declared exact-SHA native CI workflow is absent")
    ordered = sorted(candidates, key=_workflow_identity, reverse=True)
    if len(ordered) > 1 and _workflow_identity(ordered[0]) == _workflow_identity(ordered[1]):
        raise PermissionError("latest native CI workflow attempt is ambiguous")
    selected = ordered[0]
    if selected.get("status") != "completed" or selected.get("conclusion") != "success":
        raise PermissionError("latest declared exact-SHA native CI workflow is not successful")
    return selected


def verify_candidate(github, *, target: PinnedNonproductionTarget,
                     ci_policy: NativeCIWorkflowPolicy, new_sha: str) -> dict:
    old_sha, repository, branch, number = target.sha, target.repository, target.branch, target.candidate_pr_number
    if not _SHA.fullmatch(new_sha or "") or old_sha == new_sha:
        raise PermissionError("invalid candidate transition")
    if github.repository != repository or github.get_branch_sha(branch) != new_sha:
        raise PermissionError("candidate repository or branch moved")
    pr = github.get_pull_request(number)
    if (pr.state != "open" or pr.merged or pr.head_sha != new_sha or pr.head_ref != branch
            or pr.head_repository != repository or pr.base_ref != "main" or pr.number != number):
        raise PermissionError("candidate PR not verified")
    comparison = github.compare_commits(old_sha, new_sha)
    if (comparison.get("status") != "ahead" or type(comparison.get("ahead_by")) is not int
            or not 1 <= comparison["ahead_by"] <= 10000 or comparison.get("behind_by") != 0):
        raise PermissionError("candidate SHA is not a strict descendant")
    rows = github._call("GET", f"/repos/{repository}/actions/runs", query={"head_sha": new_sha, "per_page": "100"})
    selected = _select_latest_native_ci(rows, policy=ci_policy, branch=branch, sha=new_sha)
    return {
        "source": "github_actions_exact_sha", "repository": repository, "branch": branch,
        "pr_number": str(number), "pr_head_sha": new_sha, "branch_head_sha": new_sha,
        "expected_sha": old_sha, "new_sha": new_sha, "pr_base": "main", "pr_state": "open",
        "compare_status": "ahead", "ahead_by": comparison["ahead_by"], "behind_by": 0,
        "ci_conclusion": "success", "ci_sha": new_sha, "ci_run_id": selected["id"],
        "ci_workflow_id": selected["workflow_id"], "ci_run_number": selected["run_number"],
        "ci_run_attempt": selected["run_attempt"], "ci_workflow_path": ci_policy.workflow_path,
        "ci_workflow_name": ci_policy.workflow_name,
    }


def _http_get(url: str, headers: dict[str, str]) -> list[dict]:
    req = request.Request(url, headers=headers)
    with request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise RuntimeError("Control Plane existing-project query returned an invalid payload")
    return payload


def _load_projects(*, project_key: str | None = None,
                   fetcher: Callable[[str, dict[str, str]], list[dict]] | None = None) -> list[dict]:
    cfg = resolve_supabase_server_config()
    query = {"select": "id,project_key,repository,project_kind,is_active,manifest", "project_kind": "eq.existing",
             "is_active": "is.true", "order": "project_key.asc", "limit": str(_PAGE_SIZE)}
    if project_key is not None:
        if not project_key or len(project_key) > 120:
            raise ValueError("invalid project key")
        query["project_key"] = "eq." + project_key
        query["limit"] = "1"
    return (fetcher or _http_get)(cfg.url + "/rest/v1/factory_projects?" + parse.urlencode(query), cfg.headers)


def _post_rpc(name: str, body: dict) -> object:
    cfg = resolve_supabase_server_config()
    req = request.Request(cfg.url + "/rest/v1/rpc/" + name, data=json.dumps(body).encode(), method="POST",
                          headers={**cfg.headers, "Content-Type": "application/json"})
    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read() or b"null")


def _with_control(project: dict, *, control_fetcher=None) -> dict:
    cfg = resolve_supabase_server_config()
    project_id = project.get("id")
    if not isinstance(project_id, str) or not project_id:
        raise PermissionError("existing project identity is invalid")
    query = {"select": "state,generation,version", "project_id": "eq." + project_id, "limit": "1"}
    rows = (control_fetcher or _http_get)(cfg.url + "/rest/v1/factory_project_execution_controls?" + parse.urlencode(query), cfg.headers)
    if len(rows) != 1:
        raise PermissionError("existing project controller is not uniquely registered")
    return {**project, "execution_control": rows[0]}


def repin_project(project: dict, *, github_factory=None, rpc=None) -> dict:
    key, repository = project.get("project_key"), project.get("repository")
    if not isinstance(key, str) or project.get("project_kind") != "existing" or project.get("is_active") is not True:
        raise PermissionError("project is not an active existing project")
    policy = ExistingCandidatePolicy.parse(project.get("manifest"), repository=repository)
    controls = project.get("execution_control")
    if not isinstance(controls, dict) or controls.get("state") != "running":
        raise PermissionError("existing project controller is not running")
    generation, version = controls.get("generation"), controls.get("version")
    if type(generation) is not int or generation < 1 or type(version) is not int or version < 1:
        raise PermissionError("existing project execution control is invalid")
    github = github_factory(repository) if github_factory else GitHubRestAdapter(repository=repository, token=resolve_github_token(repository))
    new_sha = github.get_branch_sha(policy.target.branch)
    if new_sha == policy.target.sha:
        return {"status": "unchanged", "project_key": key, "sha": new_sha}
    evidence = verify_candidate(github, target=policy.target, ci_policy=policy.ci, new_sha=new_sha)
    result = (rpc or _post_rpc)("factory_repin_nonproduction_target_v1", {
        "p_project_key": key, "p_expected_sha": policy.target.sha, "p_new_sha": new_sha,
        "p_expected_generation": generation, "p_expected_version": version,
        "p_evidence": evidence, "p_actor_ref": "factory-candidate-reconciler"})
    if not isinstance(result, dict):
        raise RuntimeError("candidate repin RPC returned an invalid payload")
    return {"project_key": key, **result}


def repin_one(project_key: str, *, github_factory=None, rpc=None, project_fetcher=None, control_fetcher=None) -> dict:
    rows = _load_projects(project_key=project_key, fetcher=project_fetcher)
    if len(rows) != 1:
        raise PermissionError("existing project is not uniquely registered")
    return repin_project(_with_control(rows[0], control_fetcher=control_fetcher), github_factory=github_factory, rpc=rpc)


def repin_existing_projects(*, max_projects: int = 3, github_factory=None, rpc=None,
                            project_fetcher=None, control_fetcher=None) -> dict:
    if type(max_projects) is not int or not 1 <= max_projects <= _MAX_PROJECTS:
        raise ValueError(f"max_projects must be between 1 and {_MAX_PROJECTS}")
    rows = _load_projects(fetcher=project_fetcher)
    results: list[dict] = []
    for project in rows[:max_projects]:
        key = project.get("project_key") if isinstance(project.get("project_key"), str) else "unknown"
        try:
            result = repin_project(_with_control(project, control_fetcher=control_fetcher), github_factory=github_factory, rpc=rpc)
        except PermissionError as exc:
            result = {"status": "blocked", "project_key": key, "reason": str(exc)}
        except Exception as exc:
            result = {"status": "error", "project_key": key, "reason": type(exc).__name__}
        results.append(result)
    return {"status": "completed", "scanned": len(rows), "limit": max_projects, "results": results,
            "next_page": len(rows) == _PAGE_SIZE}
