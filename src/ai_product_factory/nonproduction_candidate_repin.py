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
import time
from typing import Callable
from urllib import error, parse, request

from .github_auth import resolve_github_token
from .github_rest import GitHubRestAdapter
from .pinned_nonproduction_target import PinnedNonproductionTarget
from .consumed_source_lineage import attest_consumed_preview_source
from .supabase_server import resolve_supabase_server_config


_SHA = re.compile(r"^[a-f0-9]{40}$")
_WORKFLOW_PATH = re.compile(r"^\.github/workflows/[A-Za-z0-9_.-]{1,180}\.(?:yml|yaml)$")
_WORKFLOW_NAME = re.compile(r"^[^\x00-\x1f]{1,160}$")
_MAX_PROJECTS = 5
_PAGE_SIZE = 20
_MAX_INVENTORY = 100  # Fail closed rather than silently starving projects beyond the scan.
_PROJECT_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")


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
    if (len(ordered) > 1 and ordered[0]["run_number"] == ordered[1]["run_number"]
            and ordered[0]["run_attempt"] == ordered[1]["run_attempt"]):
        # GitHub cannot have two IDs for one attempt of the same workflow.
        # A forged, stale or duplicated run cannot win by a larger run ID.
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
    def matching_open_pr(pr: object) -> bool:
        return (getattr(pr, "state", None) == "open" and getattr(pr, "merged", None) is False
                and getattr(pr, "draft", None) is False
                and getattr(pr, "head_sha", None) == new_sha
                and getattr(pr, "head_ref", None) == branch
                and getattr(pr, "head_repository", None) == repository
                and getattr(pr, "base_ref", None) == "main"
                and type(getattr(pr, "number", None)) is int and pr.number == number)
    if not matching_open_pr(github.get_pull_request(number)):
        raise PermissionError("candidate PR is draft or its identity is not verified")
    comparison = github.compare_commits(old_sha, new_sha)
    if (comparison.get("status") != "ahead" or type(comparison.get("ahead_by")) is not int
            or not 1 <= comparison["ahead_by"] <= 10000 or comparison.get("behind_by") != 0):
        raise PermissionError("candidate SHA is not a strict descendant")
    rows = github._call("GET", f"/repos/{repository}/actions/runs", query={"head_sha": new_sha, "per_page": "100"})
    selected = _select_latest_native_ci(rows, policy=ci_policy, branch=branch, sha=new_sha)
    # GitHub checks are observations at a moment, not a lock on remote refs.
    # Revalidate BOTH ref and PR immediately before the service-role CAS.
    if github.get_branch_sha(branch) != new_sha or not matching_open_pr(github.get_pull_request(number)):
        raise PermissionError("candidate moved after exact-SHA native CI validation")
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


def _verified_draft_hold(github, *, target: PinnedNonproductionTarget, observed_sha: str) -> bool:
    """Observe an intentionally unapproved source PR without repinning it.

    The only non-failure deferral is a stable, open, exact-identity DRAFT
    strictly descended from the already-authorized pinned SHA. A missing,
    changed, closed, foreign or non-ancestor PR still fails closed.
    """
    if github.repository != target.repository or not _SHA.fullmatch(observed_sha or ""):
        raise PermissionError("draft candidate repository or SHA mismatch")
    pr = github.get_pull_request(target.candidate_pr_number)
    if getattr(pr, "draft", None) is not True:
        return False  # Ready PRs must pass ordinary native CI + CAS preflight.

    def matches(row: object) -> bool:
        return (
            getattr(row, "number", None) == target.candidate_pr_number
            and getattr(row, "state", None) == "open"
            and getattr(row, "merged", None) is False
            and getattr(row, "draft", None) is True
            and getattr(row, "head_sha", None) == observed_sha
            and getattr(row, "head_ref", None) == target.branch
            and getattr(row, "head_repository", None) == target.repository
            and getattr(row, "base_ref", None) == "main"
        )

    if not matches(pr):
        raise PermissionError("draft candidate identity is not verified")
    ancestry = github.compare_commits(target.sha, observed_sha)
    if (
        not isinstance(ancestry, dict)
        or ancestry.get("status") != "ahead"
        or type(ancestry.get("ahead_by")) is not int
        or not 1 <= ancestry["ahead_by"] <= 10000
        or ancestry.get("behind_by") != 0
    ):
        raise PermissionError("draft candidate is not a strict descendant")
    if (
        github.get_branch_sha(target.branch) != observed_sha
        or not matches(github.get_pull_request(target.candidate_pr_number))
    ):
        raise PermissionError("draft candidate moved during read-only verification")
    return True



def _http_get(url: str, headers: dict[str, str]) -> list[dict]:
    req = request.Request(url, headers=headers)
    with request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise RuntimeError("Control Plane existing-project query returned an invalid payload")
    return payload


def _load_projects(*, project_key: str | None = None, offset: int = 0,
                   fetcher: Callable[[str, dict[str, str]], list[dict]] | None = None) -> list[dict]:
    if type(offset) is not int or offset < 0 or offset > _MAX_INVENTORY:
        raise ValueError("invalid bounded existing-project offset")
    cfg = resolve_supabase_server_config()
    query = {"select": "id,project_key,repository,project_kind,is_active,manifest",
             "project_kind": "eq.existing", "is_active": "is.true",
             "order": "project_key.asc", "limit": str(_PAGE_SIZE), "offset": str(offset)}
    if project_key is not None:
        if not _PROJECT_KEY.fullmatch(project_key) or offset != 0:
            raise ValueError("invalid project key or targeted offset")
        query["project_key"] = "eq." + project_key
        query["limit"] = "1"
    rows = (fetcher or _http_get)(cfg.url + "/rest/v1/factory_projects?" + parse.urlencode(query), cfg.headers)
    if not isinstance(rows, list) or len(rows) > (1 if project_key is not None else _PAGE_SIZE):
        raise RuntimeError("existing-project inventory page is unbounded")
    return rows


def _scan_existing_projects(*, fetcher=None) -> list[dict]:
    """Bound all reads; reject truncated or moving inventories, never ignore a tail."""
    projects: list[dict] = []
    seen: set[str] = set()
    previous_key = ""
    for offset in range(0, _MAX_INVENTORY + 1, _PAGE_SIZE):
        page = _load_projects(offset=offset, fetcher=fetcher)
        if offset == _MAX_INVENTORY and page:
            raise RuntimeError("existing-project inventory exceeds bounded scan limit")
        for row in page:
            key = row.get("project_key")
            if (not isinstance(key, str) or not _PROJECT_KEY.fullmatch(key)
                    or key in seen or (previous_key and key <= previous_key)
                    or row.get("project_kind") != "existing" or row.get("is_active") is not True):
                raise RuntimeError("existing-project inventory changed or contains duplicate identities")
            previous_key = key
            seen.add(key)
            projects.append(row)
        if len(page) < _PAGE_SIZE:
            break
    return projects


def _post_rpc(name: str, body: dict) -> object:
    cfg = resolve_supabase_server_config()
    req = request.Request(cfg.url + "/rest/v1/rpc/" + name, data=json.dumps(body).encode(), method="POST",
                          headers={**cfg.headers, "Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=30) as response:
            return json.loads(response.read() or b"null")
    except error.HTTPError as exc:
        # PostgREST's PT409 is a real CAS guard, not a transport outage.
        # Never echo the upstream SQL detail or request body/attestation.
        if exc.code == 409:
            raise PermissionError("candidate repin CAS conflict (HTTP 409)") from None
        raise RuntimeError("candidate repin RPC HTTP failure") from None


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



def _fetch_consumed_source_rows(project: dict) -> list[dict]:
    """Read-only, bounded receipts already written by the Factory integrator.

    A pinned SHA is a source *snapshot*, not the live head after a completed
    Factory merge. We do not infer this fact from a draft or an ancestor test.
    """
    project_id = project.get("id")
    target = project.get("manifest", {}).get("delivery_target")
    if (not isinstance(project_id, str)
            or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", project_id)
            or not isinstance(target, dict)
            or not isinstance(target.get("sha"), str)
            or not _SHA.fullmatch(target["sha"])):
        raise PermissionError("consumed source requires an exact project and SHA")
    cfg = resolve_supabase_server_config()
    query = {
        "select": "id,project_id,root_task_id,status,source_commit,candidate_commit,metadata",
        "project_id": "eq." + project_id,
        "source_commit": "eq." + target["sha"],
        "status": "eq.completed",
        "order": "created_at.desc",
        "limit": "21",
    }
    rows = _http_get(cfg.url + "/rest/v1/factory_change_sets?" + parse.urlencode(query), cfg.headers)
    if len(rows) > 20:
        raise PermissionError("consumed source history exceeds the bounded proof limit")
    return rows


def repin_project(project: dict, *, github_factory=None, rpc=None) -> dict:
    key, repository = project.get("project_key"), project.get("repository")
    if not isinstance(key, str) or project.get("project_kind") != "existing" or project.get("is_active") is not True:
        raise PermissionError("project is not an active existing project")
    policy = ExistingCandidatePolicy.parse(project.get("manifest"), repository=repository)
    controls = project.get("execution_control")
    if not isinstance(controls, dict) or controls.get("state") != "running":
        raise PermissionError("existing project controller is not running")
    generation, version = controls.get("generation"), controls.get("version")
    if type(generation) is not int or generation < 1 or type(version) is not int or version < 0:
        raise PermissionError("existing project execution control is invalid")
    github = github_factory(repository) if github_factory else GitHubRestAdapter(repository=repository, token=resolve_github_token(repository))
    new_sha = github.get_branch_sha(policy.target.branch)
    if new_sha == policy.target.sha:
        return {"status": "unchanged", "project_key": key, "sha": new_sha}
    # The Factory may itself have merged a completed Change Set into this
    # Preview branch. Such a merge is NOT a newly approved source commit,
    # even when the source PR later becomes ready. Require the exact durable
    # Change Set + project epoch + live GitHub PR/files/ancestry proof.
    completed_receipts = _fetch_consumed_source_rows(project)
    consumption = (attest_consumed_preview_source(
        github, project=project, target=policy.target, observed_sha=new_sha,
        records=completed_receipts) if completed_receipts else None)
    if consumption is not None:
        return {"status": "deferred", "project_key": key,
                "reason_code": "candidate_source_consumed", "observed_sha": new_sha}
    if _verified_draft_hold(github, target=policy.target, observed_sha=new_sha):
        # Do not mint an accepted candidate, call CI/SQL or mutate a project.
        # The SOURCE PR is explicitly awaiting human approval, not broken.
        return {"status": "deferred", "project_key": key,
                "reason_code": "candidate_draft_hold", "observed_sha": new_sha}
    evidence = verify_candidate(github, target=policy.target, ci_policy=policy.ci, new_sha=new_sha)
    result = (rpc or _post_rpc)("factory_repin_nonproduction_target_v1", {
        "p_project_key": key, "p_expected_sha": policy.target.sha, "p_new_sha": new_sha,
        "p_expected_generation": generation, "p_expected_version": version,
        "p_evidence": evidence, "p_actor_ref": "factory-candidate-reconciler"})
    if (not isinstance(result, dict) or result.get("status") != "updated"
            or result.get("project_key") != key
            or result.get("old_sha") != policy.target.sha or result.get("new_sha") != new_sha
            or type(result.get("generation")) is not int or result["generation"] != generation + 1
            or type(result.get("version")) is not int or result["version"] != version + 1):
        raise RuntimeError("candidate repin RPC receipt does not match exact project/epoch/SHA")
    return {"project_key": key, **result}


def repin_one(project_key: str, *, github_factory=None, rpc=None, project_fetcher=None, control_fetcher=None) -> dict:
    rows = _load_projects(project_key=project_key, fetcher=project_fetcher)
    if len(rows) != 1:
        raise PermissionError("existing project is not uniquely registered")
    return repin_project(_with_control(rows[0], control_fetcher=control_fetcher), github_factory=github_factory, rpc=rpc)


def repin_existing_projects(*, max_projects: int = 3, github_factory=None, rpc=None,
                            project_fetcher=None, control_fetcher=None,
                            rotation_slot: int | None = None) -> dict:
    """Scan every bounded existing project; fairly rotate a small enabled batch.

    The scheduled runner wakes at :17/:47 and selects the next group for each
    30-minute UTC slot. This avoids permanent first-N starvation without a
    new migration or hidden writable cursor. A missed GitHub schedule may
    defer a group; this is best-effort, not durable scheduling.
    """
    if type(max_projects) is not int or not 1 <= max_projects <= _MAX_PROJECTS:
        raise ValueError(f"max_projects must be between 1 and {_MAX_PROJECTS}")
    if rotation_slot is None:
        rotation_slot = int(time.time() // 1800)
    if type(rotation_slot) is not int or rotation_slot < 0:
        raise ValueError("invalid existing-project rotation slot")
    projects = _scan_existing_projects(fetcher=project_fetcher)
    enabled: list[dict] = []
    disabled = 0
    for project in projects:
        manifest = project.get("manifest")
        target = manifest.get("delivery_target") if isinstance(manifest, dict) else None
        repin = target.get("repin_policy") if isinstance(target, dict) else None
        if isinstance(repin, dict) and repin.get("enabled") is True:
            enabled.append(project)
        else:
            disabled += 1
    if not enabled:
        return {"status": "idle", "scanned": len(projects), "eligible": 0,
                "policy_disabled": disabled, "limit": max_projects,
                "rotation_group": None, "total_groups": 0,
                "results": [], "next_page": False}
    total_groups = (len(enabled) + max_projects - 1) // max_projects
    group = rotation_slot % total_groups
    selected = enabled[group * max_projects:(group + 1) * max_projects]
    results: list[dict] = []
    for project in selected:
        key = project["project_key"]
        try:
            result = repin_project(_with_control(project, control_fetcher=control_fetcher),
                                   github_factory=github_factory, rpc=rpc)
        except PermissionError as exc:
            reason_code = ("candidate_cas_conflict" if str(exc) == "candidate repin CAS conflict (HTTP 409)"
                           else "candidate_preflight_blocked")
            result = {"status": "blocked", "project_key": key, "reason_code": reason_code}
        except Exception:
            result = {"status": "error", "project_key": key,
                      "reason_code": "candidate_transport_error"}
        results.append(result)
    failed = any(r["status"] in {"error", "blocked"} for r in results)
    deferred = sum(r["status"] == "deferred" for r in results)
    status = ("partial_failure" if failed else
              "deferred" if deferred == len(results) else
              "completed_with_deferrals" if deferred else "completed")
    return {"status": status,
            "scanned": len(projects), "eligible": len(enabled), "policy_disabled": disabled,
            "limit": max_projects, "rotation_group": group, "total_groups": total_groups,
            "results": results, "next_page": total_groups > 1}
