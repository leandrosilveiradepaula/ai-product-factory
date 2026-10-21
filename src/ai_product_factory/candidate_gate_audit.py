"""Exact-PR advisory gate diagnosis for any Factory project, GET-only.

This audits the real target repository, not the Factory's CI and not the
presence of a completed work unit. It NEVER authorizes a release, requeues a
task, or treats unrelated QA as native CI or a browser-verified Preview.
"""
from __future__ import annotations

import re
from typing import Callable
from urllib.parse import quote

from .preview_policy import evaluate_preview_applicability

_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z", re.ASCII)
_PROJECT = re.compile(r"[a-z0-9][a-z0-9_-]{0,99}\Z", re.ASCII)
_SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
_UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z", re.ASCII)
_MAX_CHECKS = 100
_MAX_RUNS = 100
_MAX_FILES = 100
_MAX_BLOCKED = 25

class CandidateGateEvidenceError(RuntimeError):
    """Fail closed on incomplete, mutable, unrelated, or ambiguous evidence."""


def _one(value: object, label: str) -> dict:
    if not isinstance(value,list) or len(value)!=1 or not isinstance(value[0],dict):
        raise CandidateGateEvidenceError("missing or ambiguous " + label)
    return value[0]


def _checked_count(payload: object, key: str, limit: int) -> list[dict]:
    if (not isinstance(payload,dict)
        or type(payload.get("total_count")) is not int
        or not 0 <= payload["total_count"] <= limit
        or not isinstance(payload.get(key),list)
        or len(payload[key]) != payload["total_count"]
        or any(not isinstance(x,dict) for x in payload[key])):
        raise CandidateGateEvidenceError("incomplete bounded " + key)
    return payload[key]


def _native_ci(checks: object, runs: object, repo: str, sha: str, branch: str) -> dict:
    check_rows=_checked_count(checks,"check_runs",_MAX_CHECKS)
    run_rows=_checked_count(runs,"workflow_runs",_MAX_RUNS)
    latest: dict[tuple[str,str],dict]={}
    seen_ids:set[int]=set()
    for row in check_rows:
        name=row.get("name")
        slug=(row.get("app") or {}).get("slug")
        identity=row.get("id")
        if (row.get("head_sha")!=sha or type(identity) is not int
            or identity <= 0 or identity in seen_ids
            or not isinstance(name,str) or not re.fullmatch(r"[a-zA-Z0-9_. -]{1,100}",name,re.ASCII)
            or not isinstance(slug,str) or not slug):
            raise CandidateGateEvidenceError("invalid native check provenance")
        seen_ids.add(identity)
        key=(slug,name)
        if key not in latest or identity > latest[key]["id"]:
            latest[key]=row
    selected=list(latest.values())
    check_verified=bool(selected) and all(
        x.get("status")=="completed" and x.get("conclusion")=="success"
        for x in selected
    )
    matching=[]
    seen_run_ids=set()
    for row in run_rows:
        identity=row.get("id")
        repository=(row.get("repository") or {}).get("full_name")
        if (type(identity) is not int or identity<=0 or identity in seen_run_ids
            or row.get("head_sha")!=sha or repository!=repo
            or row.get("event") not in {"push","pull_request"}
            or not isinstance(row.get("path"),str)
            or not row["path"].startswith(".github/workflows/")
            or row.get("head_branch")!=branch):
            raise CandidateGateEvidenceError("cross-repository or invalid native workflow")
        seen_run_ids.add(identity)
        matching.append(row)
    # Require an actual successful pull_request workflow. A check from
    # Factory, a successful push alone, or a skipped downstream job is not CI.
    prs=[x for x in matching if x["event"]=="pull_request"]
    latest_pr=max(prs,key=lambda x:x["id"]) if prs else None
    pull_verified=bool(latest_pr and latest_pr.get("status")=="completed"
                       and latest_pr.get("conclusion")=="success")
    failed=sum(x.get("status")=="completed" and x.get("conclusion")=="failure" for x in selected)
    skipped=sum(x.get("status")=="completed" and x.get("conclusion")=="skipped" for x in selected)
    return {
        "status":"verified" if check_verified and pull_verified else "blocked",
        "latest_pr_workflow_state":(
            latest_pr.get("conclusion") if latest_pr and latest_pr.get("status")=="completed"
            else "missing_or_pending"),
        "checks_observed":len(check_rows),
        "latest_checks":len(selected),
        "failed_checks":failed,
        "skipped_checks":skipped,
        "native_pr_workflow_verified":pull_verified,
        "external_qa_substituted":False,
    }


def _paths(payload: object, expected: int) -> tuple[str,...]:
    if (not 0 < expected <= _MAX_FILES or not isinstance(payload,list)
        or len(payload)!=expected):
        raise CandidateGateEvidenceError("incomplete changed-file inventory")
    paths=[]
    for row in payload:
        name=row.get("filename") if isinstance(row,dict) else None
        if (not isinstance(name,str) or not name or len(name)>512
            or name.startswith("/") or ".." in name.split("/")
            or "\n" in name or "\x00" in name):
            raise CandidateGateEvidenceError("invalid changed-file provenance")
        paths.append(name)
    if len(set(paths))!=len(paths):
        raise CandidateGateEvidenceError("duplicate changed-file provenance")
    return tuple(paths)


def observe_candidate_gates(
    *, project_key: str, pr_number: int, candidate_sha: str,
    cp_get: Callable[[str],object], github_get: Callable[[str],object],
) -> dict:
    """Return complete bounded evidence or raise; no mutating API calls."""
    if not isinstance(project_key,str) or not _PROJECT.fullmatch(project_key):
        raise ValueError("invalid project key")
    if type(pr_number) is not int or not 1<=pr_number<=999999:
        raise ValueError("invalid pull request")
    if not isinstance(candidate_sha,str) or not _SHA.fullmatch(candidate_sha):
        raise ValueError("invalid candidate commit")
    project=_one(cp_get(
        "factory_projects?select=id,project_key,repository,project_kind,"
        "lifecycle_stage,is_active,manifest"
        "&project_key=eq."+quote(project_key,safe="")+"&limit=2"
    ),"project")
    repo=project.get("repository")
    pid=project.get("id")
    if (project.get("project_key")!=project_key or not isinstance(repo,str)
        or not _REPO.fullmatch(repo) or any(x in {".",".."} for x in repo.split("/"))
        or not isinstance(pid,str) or not _UUID.fullmatch(pid)
        or project.get("is_active") is not True
        or not isinstance(project.get("manifest"),dict)
        or not isinstance(project.get("project_kind"),str)):
        raise CandidateGateEvidenceError("unverifiable project ownership")
    ctrl=_one(cp_get(
        "factory_project_execution_controls?select=project_id,state,generation"
        "&project_id=eq."+pid+"&limit=2"
    ),"execution control")
    if (ctrl.get("project_id")!=pid
        or ctrl.get("state") not in {"draft","running","pausing","paused","stopping","stopped"}
        or type(ctrl.get("generation")) is not int or ctrl["generation"]<0):
        raise CandidateGateEvidenceError("unverifiable project execution control")

    prefix="/repos/"+repo
    identity=github_get(prefix)
    default=identity.get("default_branch") if isinstance(identity,dict) else None
    if (not isinstance(identity,dict) or identity.get("full_name")!=repo
        or not isinstance(default,str) or not re.fullmatch(r"[A-Za-z0-9._/-]{1,100}",default)):
        raise CandidateGateEvidenceError("unverifiable GitHub repository identity")
    pr=github_get(prefix+"/pulls/"+str(pr_number))
    if not isinstance(pr,dict):
        raise CandidateGateEvidenceError("unverifiable pull request")
    head=pr.get("head") or {}
    base=pr.get("base") or {}
    if (pr.get("number")!=pr_number or pr.get("state")!="open"
        or pr.get("merged") is not False
        or head.get("sha")!=candidate_sha
        or (head.get("repo") or {}).get("full_name")!=repo
        or (base.get("repo") or {}).get("full_name")!=repo
        or base.get("ref")!=default
        or not isinstance(head.get("ref"),str)):
        raise CandidateGateEvidenceError("PR is not the exact open target candidate")
    branch=head["ref"]
    changed=_paths(
        github_get(prefix+"/pulls/"+str(pr_number)+"/files?per_page=100"),
        pr.get("changed_files"),
    )
    native=_native_ci(
        github_get(prefix+"/commits/"+candidate_sha+"/check-runs?per_page=100"),
        github_get(prefix+"/actions/runs?head_sha="+candidate_sha+"&per_page=100"),
        repo,candidate_sha,branch,
    )
    applicability=evaluate_preview_applicability(
        manifest=project["manifest"],changed_files=changed,
    )
    policy=project["manifest"].get("preview")
    # Never promote a provider status or a web build to browser-verified.
    if not isinstance(policy,dict):
        preview_status="policy_missing"
    elif applicability.required:
        preview_status="browser_evidence_not_verified"
    elif policy.get("required") is False and not str(policy.get("reason") or "").strip():
        preview_status="policy_not_justified"
    else:
        preview_status="not_applicable_by_explicit_policy_or_changed_paths"
    blocked=cp_get(
        "factory_change_sets?select=id,status,project_id,root_task_id,release_run_id"
        "&project_id=eq."+pid+"&status=eq.blocked&limit=26"
    )
    if (not isinstance(blocked,list) or len(blocked)>_MAX_BLOCKED
        or any(not isinstance(x,dict) or x.get("project_id")!=pid
               or x.get("status")!="blocked" or not isinstance(x.get("id"),str)
               or not _UUID.fullmatch(x["id"])
               for x in blocked)):
        raise CandidateGateEvidenceError("incomplete blocked Change Set inventory")
    blockers=[]
    if ctrl["state"]!="running" or ctrl["generation"]<1:
        blockers.append("project_not_running")
    if native["status"]!="verified":
        blockers.append("native_ci_not_verified")
    if preview_status in {"policy_missing","policy_not_justified"}:
        blockers.append("preview_policy_unconfigured")
    elif applicability.required:
        blockers.append("preview_browser_evidence_not_verified")
    if blocked:
        blockers.append("historical_blocked_change_set_review")
    # A PR that has not been human merged NEVER becomes release-authorized
    # from this diagnostic, regardless of all other signals.
    blockers.append("human_production_merge_pending")
    return {
        "project_key":project_key,
        "project_id":pid,
        "project_kind":project["project_kind"],
        "candidate_sha":candidate_sha,
        "repository":repo,
        "pr_number":pr_number,
        "pr_draft":pr.get("draft") is True,
        "control":{"state":ctrl["state"],"generation":ctrl["generation"]},
        "native_ci":native,
        "preview":{
            "status":preview_status,
            "required":applicability.required,
            "policy_reason":applicability.reason,
            "matched_path_count":len(applicability.matched_paths),
            "browser_verified":False,
        },
        "historical_blocked_change_sets":len(blocked),
        "release":{"status":"human_gate_pending","authorized":False},
        "reason_codes":blockers,
        "status":"blocked",
        "ready_for_production":False,
        "product_ready":False,
        "read_only":True,
        "writes":0,
        "paid_calls":0,
        "evidence_scope":"advisory_exact_PR_not_a_release_gate",
    }
