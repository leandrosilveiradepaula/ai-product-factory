"""Owner-triggered, fail-closed exact-SHA requeue of an existing failed Preview.

Only the original greenfield PR and Start lineage may be resumed. The external
candidate must be an ancestor-preserving, green CI commit with a first-party
signed browser-verification snapshot; historical failures and DoD stay intact.
No production merge, paid model, or artificial readiness is performed.
"""
from __future__ import annotations

import argparse
import json
import re
from urllib.parse import quote

from .admission_diagnostics import SupabaseAdmissionReader
from .blocked_release_candidate import (
    SHA, UUID, SAFE_PATH, REPOSITORY, BlockedCandidateRecoveryDenied,
    require, one, exact_sha_ci_state,
)
from .github_rest import GitHubRestAdapter
from .supabase_delivery_store import SupabaseDeliveryStore

FACTORY="leandrosilveiradepaula/ai-product-factory"
URL=re.compile(r"https://[a-z0-9][a-z0-9-]*\.vercel\.app\Z")
_REQUEST=re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")


def verify_browser_snapshot(*, row: dict, project_id: str, repository: str,
                            new_sha: str, factory: GitHubRestAdapter) -> dict:
    evidence=row.get("evidence")
    src=row.get("source_status")
    require(row.get("project_id")==project_id and row.get("run_id") is None
            and row.get("observed_stage")=="verification"
            and isinstance(evidence,dict)
            and evidence.get("target_repository")==repository
            and evidence.get("candidate_commit")==new_sha
            and isinstance(src,dict) and src.get("github_target")=="verified"
            and src.get("vercel_preview")=="resolved"
            and src.get("browser_visual_validation")=="success",
            "preview_witness_not_same_exact_candidate")
    preview=evidence.get("preview") or {}
    url=preview.get("url")
    run_id=preview.get("browser_verifier_run_id")
    request=preview.get("browser_request_id")
    sha=preview.get("verifier_factory_commit")
    require(preview.get("status")=="browser_verified"
            and preview.get("provider")=="vercel"
            and isinstance(url,str) and URL.fullmatch(url) is not None
            and type(run_id) is int and run_id>0
            and isinstance(request,str) and _REQUEST.fullmatch(request) is not None
            and isinstance(sha,str) and SHA.fullmatch(sha) is not None,
            "preview_witness_fields_invalid")
    path=f"/repos/{FACTORY}/actions/runs/{run_id}"
    workflow=factory._call("GET",path)
    jobs=factory._call("GET",path+"/jobs",query={"per_page":"100"})
    require(isinstance(workflow,dict)
            and workflow.get("id")==run_id
            and workflow.get("name")=="Console evidence "+request
            and workflow.get("event")=="workflow_dispatch"
            and workflow.get("head_sha")==sha
            and workflow.get("head_branch")=="main"
            and workflow.get("status")=="completed"
            and workflow.get("conclusion")=="success"
            and isinstance(jobs,dict) and isinstance(jobs.get("jobs"),list)
            and 1<=len(jobs["jobs"])<=100
            and jobs.get("total_count")==len(jobs["jobs"])
            and any(isinstance(j,dict) and j.get("name")=="browser-evidence"
                    and j.get("conclusion")=="success"
                    and any(isinstance(step,dict)
                            and step.get("name")=="Verify exact protected Preview"
                            and step.get("conclusion")=="success"
                            for step in (j.get("steps") or []))
                    for j in jobs["jobs"]),
            "independent_browser_run_not_reverified")
    return {"snapshot_id":row["id"],"preview_url":url,
            "browser_run_id":run_id,"verifier_factory_sha":sha}


def reconcile_failed_preview_candidate(
    *,run_id:str,pr_number:int,read=None,github_factory=None,
    factory_github=None,store=None,ci_verifier=None,
) -> dict:
    require(isinstance(run_id,str) and UUID.fullmatch(run_id) is not None
            and type(pr_number) is int and 1<=pr_number<=2_147_483_647,
            "recovery_identity_invalid")
    read=read or SupabaseAdmissionReader()._get
    github_factory=github_factory or (lambda repository: GitHubRestAdapter(repository=repository))
    factory_github=factory_github or GitHubRestAdapter(repository=FACTORY)
    ci_verifier=ci_verifier or exact_sha_ci_state
    run=one(read,"factory_runs",
        "id,task_id,status,branch_name,candidate_commit,metadata,lease_owner,lease_expires_at"
        "&id=eq."+quote(run_id,safe="")+"&limit=2")
    old=run.get("candidate_commit")
    md=run.get("metadata") or {}
    require(run.get("id")==run_id and run.get("status")=="failed"
            and isinstance(old,str) and SHA.fullmatch(old) is not None
            and isinstance(md,dict) and md.get("source")=="change-set"
            and isinstance(md.get("change_set_id"),str)
            and UUID.fullmatch(md["change_set_id"]) is not None
            and run.get("lease_owner") is None and run.get("lease_expires_at") is None,
            "old_failed_run_not_recoverable")
    cs=one(read,"factory_change_sets",
        "id,project_id,root_task_id,release_run_id,status,"
        "branch_name:integration_branch,candidate_commit,metadata,lease_owner,lease_expires_at"
        "&id=eq."+quote(md["change_set_id"],safe="")+"&limit=2")
    branch=cs.get("branch_name")
    receipt=(cs.get("metadata") or {}).get("integration_release_request") or {}
    epoch=(cs.get("metadata") or {}).get("integration_epoch_receipt") or {}
    require(cs.get("id")==md["change_set_id"]
            and cs.get("release_run_id")==run_id and cs.get("root_task_id")==run.get("task_id")
            and cs.get("status")=="ci_pending" and cs.get("candidate_commit")==old
            and cs.get("lease_owner") is None and cs.get("lease_expires_at") is None
            and branch==run.get("branch_name")
            and isinstance(branch,str) and branch.startswith("factory/change-set-")
            and receipt.get("candidate_commit")==old and receipt.get("pr_number")==pr_number
            and receipt.get("branch")==branch
            and epoch.get("candidate_commit")==old
            and epoch.get("project_id")==cs.get("project_id")
            and str(md.get("execution_generation"))==str(epoch.get("generation")),
            "change_set_lineage_or_epoch_invalid")
    project=one(read,"factory_projects",
        "id,project_kind,is_active,repository"
        "&id=eq."+quote(cs["project_id"],safe="")+"&limit=2")
    repository=project.get("repository")
    require(project.get("is_active") is True and project.get("project_kind")=="greenfield"
            and isinstance(repository,str) and REPOSITORY.fullmatch(repository) is not None,
            "not_an_active_greenfield")
    task=one(read,"factory_tasks",
        "id,project_id,status&id=eq."+quote(run["task_id"],safe="")+"&limit=2")
    require(task.get("id")==run["task_id"] and task.get("project_id")==project["id"]
            and task.get("status")=="failed","root_task_not_failed")
    report=one(read,"factory_release_reports",
        "run_id,project_id,status,report"
        "&run_id=eq."+quote(run_id,safe="")+"&limit=2")
    dod=(report.get("report") or {}).get("definition_of_done") or {}
    missing=dod.get("missing")
    require(report.get("run_id")==run_id and report.get("project_id")==project["id"]
            and report.get("status")=="blocked"
            and isinstance(missing,list) and 1<=len(missing)<=25
            and any(x.get("human_only") is False for x in missing if isinstance(x,dict)),
            "nonhuman_dod_obstruction_missing")
    evaluations=read("factory_evaluations?select=eval_type,status,created_at,result"
        "&run_id=eq."+quote(run_id,safe="")
        +"&eval_type=eq.browser_e2e&order=created_at.desc&limit=1")
    require(isinstance(evaluations,list) and len(evaluations)==1
            and evaluations[0].get("status")=="failure",
            "latest_original_browser_failure_missing")
    github=github_factory(repository)
    pr=github.get_pull_request(pr_number)
    new=pr.head_sha
    require(pr.number==pr_number and pr.state=="open" and pr.merged is False
            and pr.draft is False and pr.head_repository==repository
            and pr.head_ref==branch and pr.base_ref=="main"
            and isinstance(new,str) and SHA.fullmatch(new) is not None
            and new!=old and github.get_branch_sha(branch)==new,
            "current_pr_head_not_verified")
    comparison=github.compare_commits(old,new)
    files=comparison.get("files")
    require(comparison.get("status")=="ahead" and comparison.get("behind_by")==0
            and type(comparison.get("ahead_by")) is int
            and 1<=comparison["ahead_by"]<=32
            and isinstance(files,list) and 1<=len(files)<=300
            and len(files)==len(set(files))
            and all(isinstance(f,str) and 1<=len(f)<=240
                    and SAFE_PATH.fullmatch(f) is not None
                    and all(part not in ("",".","..") for part in f.split("/"))
                    for f in files),
            "candidate_ancestry_or_changed_files_unverified")
    ci=ci_verifier(github,new)
    require(isinstance(ci,dict) and ci.get("source")=="github_actions_checks"
            and type(ci.get("workflows")) is int and ci["workflows"]>=1
            and type(ci.get("completed_native_checks")) is int
            and ci["completed_native_checks"]>=2,
            "candidate_native_ci_incomplete")
    snapshots=read(
        "factory_project_state_snapshots?select=id,project_id,run_id,observed_stage,"
        "evidence,source_status&project_id=eq."+quote(project["id"],safe="")
        +"&observed_stage=eq.verification&order=created_at.desc&limit=15")
    require(isinstance(snapshots,list) and len(snapshots)<=15,
            "browser_evidence_inventory_unbounded")
    found=[x for x in snapshots if isinstance(x,dict)
           and (x.get("evidence") or {}).get("candidate_commit")==new
           and (x.get("evidence") or {}).get("preview",{}).get("status")=="browser_verified"]
    require(len(found)==1,"current_candidate_browser_attestation_missing_or_ambiguous")
    browser=verify_browser_snapshot(row=found[0],project_id=project["id"],
        repository=repository,new_sha=new,factory=factory_github)
    again=github.get_pull_request(pr_number)
    require(again.head_sha==new and again.state=="open" and again.merged is False
            and again.head_ref==branch and again.head_repository==repository
            and github.get_branch_sha(branch)==new,
            "candidate_moved_before_recovery")
    evidence={
        "source":"github_actions_exact_sha",
        "repository":repository,"branch":branch,
        "old_sha":old,"new_sha":new,"pr_number":str(pr_number),
        "compare_status":"ahead","ahead_by":str(comparison["ahead_by"]),
        "behind_by":"0","changed_files":files,
        "ci_state":"success","ci_source":ci["source"],
        "native_checks":ci["completed_native_checks"],
        "native_workflows":ci["workflows"],
        "browser_snapshot_id":browser["snapshot_id"],
        "browser_run_id":str(browser["browser_run_id"]),
        "verifier_factory_sha":browser["verifier_factory_sha"],
        "preview_url":browser["preview_url"],
        "release_authorized":False,
        "new_specialist_approval_required":True,
        "recheck_dod_required":True,
    }
    result=(store or SupabaseDeliveryStore())._rpc(
        "factory_reconcile_failed_preview_candidate_v1",{
            "p_change_set_id":cs["id"],"p_run_id":run_id,
            "p_pr_number":pr_number,"p_previous_commit":old,
            "p_new_commit":new,"p_verified_evidence":evidence,
        })
    require(isinstance(result,dict) and result.get("run_id")==run_id
            and result.get("status")=="ci_pending"
            and result.get("previous_commit")==old
            and result.get("candidate_commit")==new
            and result.get("release_authorized") is False
            and result.get("old_evidence_preserved") is True,
            "atomic_recovery_receipt_inconsistent")
    return result


def main()->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--run-id",required=True)
    parser.add_argument("--pr-number",type=int,required=True)
    args=parser.parse_args()
    try:
        result=reconcile_failed_preview_candidate(
            run_id=args.run_id,pr_number=args.pr_number)
        print(json.dumps(result,sort_keys=True))
        return 0
    except (BlockedCandidateRecoveryDenied,ValueError,RuntimeError) as exc:
        code=str(exc)
        # Only stable local reason codes. External errors may contain URLs.
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,100}",code):
            code="external_reconciliation_denied"
        print(json.dumps({"status":"blocked","reason_code":code,
             "release_authorized":False,"paid_model_calls":0}))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
