"""Fail-closed, operator-triggered reconciliation of a blocked release candidate.

A greenfield PR can advance on its nonproduction branch while the release
policy has already denied the original SHA. This module verifies GitHub commit,
PR, Actions jobs, Control Plane origin and DoD blockage *before* asking the
service-role-only RPC to requeue exact-SHA CI. No model, merge or deployment.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from .admission_diagnostics import SupabaseAdmissionReader
from .github_rest import GitHubRestAdapter
from .github_loop import CIState
from .supabase_delivery_store import SupabaseDeliveryStore

SHA = re.compile(r"[0-9a-f]{40}\Z")
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
SAFE_PATH = re.compile(r"[A-Za-z0-9_.\-/]+\Z")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


class BlockedCandidateRecoveryDenied(RuntimeError):
    """Only stable reason codes are emitted: no tokens or private response."""


def require(condition: bool, code: str) -> None:
    if condition is not True:
        raise BlockedCandidateRecoveryDenied(code)


def one(read, table: str, query: str) -> dict:
    rows=read(table + "?select=" + query)
    require(isinstance(rows,list) and len(rows)==1
            and isinstance(rows[0],dict), "control_plane_identity_ambiguous")
    return rows[0]


def exact_sha_ci_state(github, sha: str) -> dict:
    """Accept SHA-bound Actions checks across branches for RECOVERY ONLY.

    A prior Actions job on the same git SHA is useful to verify candidate code;
    it does not satisfy the new PR's later release/Preview/DoD checks. Never
    issue a release decision or mark QA passed from this helper.
    """
    source, checks, statuses=github._check_runs_or_fine_grained_evidence(sha,None)
    workflows=github.last_ci_workflow_runs
    require(isinstance(workflows,list) and 1 <= len(workflows) <= 100,
            "exact_sha_actions_workflow_missing")
    require(github._ci_state_from_fine_grained_evidence(workflows,[]) is CIState.SUCCESS,
            "exact_sha_actions_workflow_not_green")
    require(isinstance(statuses,list) and not any(
        isinstance(row,dict) and row.get("state") in ("error","failure")
        for row in statuses), "exact_sha_github_status_failed")
    require(source=="github_checks" and isinstance(checks,list)
            and 1 <= len(checks) <= 100
            and all(isinstance(c,dict) and c.get("head_sha")==sha
                    and c.get("status")=="completed"
                    and c.get("conclusion")=="success" for c in checks),
            "exact_sha_native_jobs_not_green")
    suites={w.get("check_suite_id") for w in workflows
            if w.get("status")=="completed" and w.get("conclusion")=="success"}
    observed={c.get("check_suite",{}).get("id") for c in checks}
    require(all(type(suite) is int and suite in observed for suite in suites),
            "exact_sha_actions_suite_incomplete")
    return {"source":"github_actions_checks","workflows":len(workflows),
            "completed_native_checks":len(checks)}


def reconcile_blocked_release_candidate(
    *, run_id: str, pr_number: int, read=None,
    github_factory=None, store=None, ci_verifier=None,
) -> dict:
    """Exact operator-selected run; zero writes until the final guarded RPC."""
    require(isinstance(run_id,str) and UUID.fullmatch(run_id) is not None
            and type(pr_number) is int and 1 <= pr_number <= 2_147_483_647,
            "invalid_recovery_identity")
    read=read or SupabaseAdmissionReader()._get
    github_factory=github_factory or (lambda repository: GitHubRestAdapter(repository=repository))
    ci_verifier=ci_verifier or exact_sha_ci_state
    run=one(read,"factory_runs",
        "id,task_id,status,branch_name,candidate_commit,metadata,lease_owner,lease_expires_at"
        "&id=eq."+quote(run_id,safe="")+"&limit=2")
    metadata=run.get("metadata")
    previous=run.get("candidate_commit")
    require(run.get("id")==run_id and run.get("status")=="release_policy_blocked"
            and isinstance(metadata,dict)
            and metadata.get("source")=="change-set"
            and isinstance(metadata.get("change_set_id"),str)
            and UUID.fullmatch(metadata["change_set_id"]) is not None
            and isinstance(previous,str) and SHA.fullmatch(previous) is not None
            and run.get("lease_owner") is None and run.get("lease_expires_at") is None,
            "blocked_run_not_recoverable")
    change_set=one(read,"factory_change_sets",
        "id,project_id,root_task_id,release_run_id,status,branch_name:integration_branch,"
        "candidate_commit,metadata,lease_owner,lease_expires_at"
        "&id=eq."+quote(metadata["change_set_id"],safe="")+"&limit=2")
    branch=change_set.get("branch_name")
    request=(change_set.get("metadata") or {}).get("integration_release_request")
    require(change_set.get("id")==metadata["change_set_id"]
            and change_set.get("release_run_id")==run_id
            and change_set.get("status")=="ci_pending"
            and change_set.get("root_task_id")==run.get("task_id")
            and change_set.get("candidate_commit")==previous
            and branch==run.get("branch_name")
            and isinstance(branch,str) and branch.startswith("factory/change-set-")
            and change_set.get("lease_owner") is None
            and change_set.get("lease_expires_at") is None
            and isinstance(request,dict)
            and request.get("pr_number")==pr_number
            and request.get("candidate_commit")==previous
            and request.get("branch")==branch,
            "blocked_change_set_not_recoverable")
    project=one(read,"factory_projects",
        "id,project_kind,repository,is_active"
        "&id=eq."+quote(change_set["project_id"],safe="")+"&limit=2")
    repository=project.get("repository")
    require(project.get("is_active") is True
            and project.get("project_kind") in ("existing","greenfield")
            and isinstance(repository,str) and REPOSITORY.fullmatch(repository) is not None,
            "inactive_or_invalid_target_project")
    report=one(read,"factory_release_reports",
        "run_id,project_id,status,candidate_commit,report"
        "&run_id=eq."+quote(run_id,safe="")+"&limit=2")
    payload=report.get("report")
    dod=payload.get("definition_of_done") if isinstance(payload,dict) else None
    missing=dod.get("missing") if isinstance(dod,dict) else None
    require(report.get("run_id")==run_id
            and report.get("project_id")==change_set["project_id"]
            and report.get("status")=="blocked"
            and report.get("candidate_commit")==previous
            and payload.get("release_state")=="blocked"
            and isinstance(missing,list) and 1 <= len(missing) <= 25
            and any(isinstance(x,dict) and x.get("human_only") is False
                    for x in missing),
            "original_nonhuman_dod_blocker_missing")
    github=github_factory(repository)
    pr=github.get_pull_request(pr_number)
    new=pr.head_sha
    require(pr.number==pr_number and pr.state=="open"
            and pr.merged is False and pr.draft is False
            and pr.head_repository==repository and pr.head_ref==branch
            and pr.base_ref=="main"
            and isinstance(new,str) and SHA.fullmatch(new) is not None
            and new!=previous, "candidate_pr_identity_changed")
    comparison=github.compare_commits(previous,new)
    files=comparison.get("files")
    require(comparison.get("status")=="ahead" and comparison.get("behind_by")==0
            and type(comparison.get("ahead_by")) is int
            and 1 <= comparison["ahead_by"] <= 100
            and isinstance(files,list) and 1 <= len(files) <= 300
            and len(files)==len(set(files))
            and all(isinstance(f,str) and 1 <= len(f) <= 240
                    and SAFE_PATH.fullmatch(f) is not None
                    and all(part not in ("", ".", "..") for part in f.split("/"))
                    for f in files),
            "candidate_history_or_path_policy_denied")
    require(github.get_branch_sha(branch)==new,"candidate_branch_moved")
    ci=ci_verifier(github,new)
    require(isinstance(ci,dict)
            and ci.get("source")=="github_actions_checks"
            and type(ci.get("workflows")) is int and ci["workflows"]>=1
            and type(ci.get("completed_native_checks")) is int
            and ci["completed_native_checks"]>=1,
            "exact_sha_ci_attestation_missing")
    # Recheck the PR and ref AFTER GitHub evidence, before privileged CAS.
    again=github.get_pull_request(pr_number)
    require(again.state=="open" and again.merged is False
            and again.head_sha==new and again.head_ref==branch
            and again.head_repository==repository and again.base_ref=="main"
            and github.get_branch_sha(branch)==new,
            "candidate_changed_before_atomic_reconciliation")
    evidence={
        "old_sha":previous,"new_sha":new,"pr_number":str(pr_number),
        "repository":repository,"branch":branch,
        "compare_status":"ahead","ahead_by":str(comparison["ahead_by"]),
        "behind_by":"0","changed_files":files,
        "ci_state":"success","ci_source":ci["source"],
        "native_workflows":ci["workflows"],
        "native_checks":ci["completed_native_checks"],
        "reason":"resume_blocked_release_after_verified_nonproduction_change",
        "release_authorized":False,
        "target_pr_ci_still_required":True,
    }
    store=store or SupabaseDeliveryStore()
    result=store._rpc("factory_reconcile_policy_blocked_candidate_v1",{
        "p_change_set_id":change_set["id"],
        "p_run_id":run_id,"p_pr_number":pr_number,
        "p_previous_commit":previous,"p_new_commit":new,
        "p_verified_evidence":evidence,
    })
    require(isinstance(result,dict)
            and result.get("status")=="ci_pending"
            and result.get("run_id")==run_id
            and result.get("previous_commit")==previous
            and result.get("candidate_commit")==new
            and result.get("release_authorized") is False
            and result.get("old_evidence_preserved") is True
            and result.get("new_specialist_approval_required") is True,
            "atomic_reconciliation_receipt_inconsistent")
    return result
