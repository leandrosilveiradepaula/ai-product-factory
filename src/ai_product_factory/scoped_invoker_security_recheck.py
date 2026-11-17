"""One-shot genuine exact-SHA Security recheck after a stricter invoker/RLS guard.

Never turns a failed verdict into PASS. Verifies the full target PR,
Factory main CI and explicit tenant RLS before atomically re-queuing a
real specialist scanner; original failed evaluation and findings are
retained in immutable database audit history.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from urllib.parse import quote

from .admission_diagnostics import SupabaseAdmissionReader
from .architecture_guardian import scan_pull_request_files
from .blocked_release_candidate import (
    SHA, UUID, REPOSITORY, BlockedCandidateRecoveryDenied,
    require, one, exact_sha_ci_state,
)
from .github_rest import GitHubRestAdapter
from .supabase_delivery_store import SupabaseDeliveryStore

FACTORY="leandrosilveiradepaula/ai-product-factory"


def requeue_verified_invoker_review(
    *,run_id:str,pr_number:int,read=None,github_factory=None,
    factory_github=None,store=None,ci_verifier=None,scan=None,
)->dict:
    require(isinstance(run_id,str) and UUID.fullmatch(run_id) is not None
            and type(pr_number) is int and 1<=pr_number<=2_147_483_647,
            "invalid_recheck_identity")
    read=read or SupabaseAdmissionReader()._get
    github_factory=github_factory or (
        lambda repository:GitHubRestAdapter(repository=repository))
    factory_github=factory_github or GitHubRestAdapter(repository=FACTORY)
    store=store or SupabaseDeliveryStore()
    ci_verifier=ci_verifier or exact_sha_ci_state
    scan=scan or scan_pull_request_files
    root=one(read,"factory_runs",
        "id,task_id,status,candidate_commit,branch_name,metadata,lease_owner,lease_expires_at"
        "&id=eq."+quote(run_id,safe="")+"&limit=2")
    metadata=root.get("metadata") or {}
    sha=root.get("candidate_commit")
    require(root.get("id")==run_id
            and root.get("status")=="specialist_review_failed"
            and isinstance(sha,str) and SHA.fullmatch(sha) is not None
            and isinstance(metadata,dict)
            and metadata.get("source")=="change-set"
            and isinstance(metadata.get("change_set_id"),str)
            and UUID.fullmatch(metadata["change_set_id"]) is not None
            and root.get("lease_owner") is None
            and root.get("lease_expires_at") is None,
            "original_failed_security_review_missing")
    cs=one(read,"factory_change_sets",
        "id,project_id,root_task_id,status,candidate_commit,integration_branch,"
        "release_run_id,metadata,lease_owner,lease_expires_at"
        "&id=eq."+quote(metadata["change_set_id"],safe="")+"&limit=2")
    receipt=(cs.get("metadata") or {}).get("integration_release_request") or {}
    branch=cs.get("integration_branch")
    require(cs.get("status")=="blocked" and cs.get("release_run_id") is None
            and cs.get("candidate_commit")==sha
            and cs.get("root_task_id")==root.get("task_id")
            and cs.get("lease_owner") is None and cs.get("lease_expires_at") is None
            and branch==root.get("branch_name")
            and isinstance(branch,str) and branch.startswith("factory/change-set-")
            and receipt.get("candidate_commit")==sha
            and receipt.get("pr_number")==pr_number
            and receipt.get("branch")==branch,
            "current_blocked_change_set_lineage_missing")
    project=one(read,"factory_projects",
        "id,project_kind,is_active,repository"
        "&id=eq."+quote(cs["project_id"],safe="")+"&limit=2")
    repository=project.get("repository")
    require(project.get("project_kind")=="greenfield"
            and project.get("is_active") is True
            and isinstance(repository,str) and REPOSITORY.fullmatch(repository) is not None,
            "external_greenfield_project_unverified")
    jobs=read("factory_specialist_lane_jobs?select=id,role,status,required,"
              "candidate_commit,findings,evidence,lease_expires_at"
              "&run_id=eq."+quote(run_id,safe="")
              +"&candidate_commit=eq."+quote(sha,safe="")
              +"&order=role.asc&limit=6")
    require(isinstance(jobs,list) and len(jobs)==3
            and {x.get("role") for x in jobs if isinstance(x,dict)}
                =={"security","qa","operations"}
            and all(x.get("candidate_commit")==sha
                    and x.get("required") is True for x in jobs),
            "same_sha_specialist_job_set_unverified")
    security=next(x for x in jobs if x["role"]=="security")
    require(security.get("status")=="failed"
            and security.get("lease_expires_at") is None
            and all(x.get("status")=="passed" for x in jobs
                    if x.get("role")!="security"),
            "only_one_scoped_security_failure_allowed")
    findings=security.get("findings")
    require(isinstance(findings,list) and 1<=len(findings)<=25
            and any(x.get("code")=="permissive_public_grant"
                    and x.get("severity")=="error" for x in findings if isinstance(x,dict))
            and all(isinstance(x,dict)
                    and (x.get("severity") not in ("error","critical")
                         or x.get("code")=="permissive_public_grant")
                    and (x.get("code")!="permissive_public_grant"
                         or (x.get("kind")=="database_security"
                             and x.get("source")=="architecture_guardian_v1"
                             and str(x.get("path") or "").startswith("supabase/migrations/")))
                    for x in findings),
            "unrelated_security_finding_cannot_be_rechecked")
    target=github_factory(repository)
    pr=target.get_pull_request(pr_number)
    require(pr.number==pr_number and pr.state=="open"
            and pr.merged is False and pr.draft is False
            and pr.head_sha==sha and pr.head_ref==branch
            and pr.head_repository==repository and pr.base_ref=="main"
            and target.get_branch_sha(branch)==sha,
            "original_unchanged_candidate_pr_required")
    rows=target.get_pull_request_file_details(pr_number)
    require(isinstance(rows,tuple) and 1<=len(rows)<=300
            and all(isinstance(r,dict) and isinstance(r.get("patch"),str)
                    and bool(r.get("patch").strip()) for r in rows),
            "complete_reviewable_github_pr_diff_required")
    report=scan(rows)
    evidence=report.evidence
    require(evidence.get("scanner")=="architecture_guardian_v1"
            and evidence.get("files_reviewed")==len(rows)
            and evidence.get("blocking_findings")==0
            and evidence.get("unreviewable_paths")==[]
            and len(report.findings)<=200
            and not any(f.get("severity") in ("error","critical")
                        for f in report.findings),
            "independent_current_scanner_still_blocks_release")
    ci=ci_verifier(target,sha)
    require(isinstance(ci,dict)
            and ci.get("source")=="github_actions_checks"
            and type(ci.get("completed_native_checks")) is int
            and ci["completed_native_checks"]>=2
            and type(ci.get("workflows")) is int and ci["workflows"]>=1,
            "original_candidate_native_ci_not_current")
    factory_sha=factory_github.get_branch_sha("main")
    require(isinstance(factory_sha,str) and SHA.fullmatch(factory_sha) is not None,
            "factory_main_sha_unverified")
    workflows=factory_github._call("GET",f"/repos/{FACTORY}/actions/runs",
                    query={"head_sha":factory_sha,"per_page":"100","branch":"main"})
    wf=workflows.get("workflow_runs") if isinstance(workflows,dict) else None
    require(isinstance(wf,list) and any(
        isinstance(x,dict) and x.get("name")=="validate"
        and x.get("event")=="push" and x.get("head_sha")==factory_sha
        and x.get("status")=="completed" and x.get("conclusion")=="success"
        for x in wf),
        "independent_merged_factory_guardian_ci_missing")
    unchanged=target.get_pull_request(pr_number)
    require(unchanged.head_sha==sha and unchanged.state=="open"
            and unchanged.head_ref==branch and unchanged.merged is False
            and target.get_branch_sha(branch)==sha
            and factory_github.get_branch_sha("main")==factory_sha,
            "candidate_or_factory_policy_moved_before_recheck")
    diffhash=hashlib.sha256(json.dumps(
        rows,sort_keys=True,separators=(",",":"),ensure_ascii=True
    ).encode()).hexdigest()
    proof={
        "source":"github_native_ci_full_pr_scanner","guardian":"architecture_guardian_v1",
        "repository":repository,"candidate_commit":sha,
        "pr_number":str(pr_number),"blockers":"0",
        "files_reviewed":str(len(rows)),"diff_sha256":diffhash,
        "factory_main_sha":factory_sha,"factory_main_ci":"success",
        "native_ci_state":"success","native_checks":str(ci["completed_native_checks"]),
        "release_authorized":False,"model_called":False,
    }
    result=store._rpc("factory_requeue_verified_invoker_security_once_v1",{
        "p_run_id":run_id,"p_pr_number":pr_number,
        "p_candidate_commit":sha,"p_security_job_id":security["id"],
        "p_verified_proof":proof,
    })
    require(isinstance(result,dict)
            and result.get("status")=="specialist_review_pending"
            and result.get("run_id")==run_id
            and result.get("candidate_commit")==sha
            and result.get("security_job_id")==security["id"]
            and result.get("previous_failure_preserved") is True
            and result.get("release_authorized") is False,
            "atomic_security_recheck_receipt_inconsistent")
    return result


def main()->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--run-id",required=True)
    parser.add_argument("--pr-number",type=int,required=True)
    args=parser.parse_args()
    try:
        result=requeue_verified_invoker_review(
            run_id=args.run_id,pr_number=args.pr_number)
        print(json.dumps(result,sort_keys=True))
        return 0
    except (BlockedCandidateRecoveryDenied,ValueError,RuntimeError) as exc:
        code=str(exc)
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,110}",code):
            code="external_security_recheck_denied"
        print(json.dumps({"status":"blocked","reason_code":code,
            "new_review_performed":False,"release_authorized":False,
            "paid_model_calls":0},sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
