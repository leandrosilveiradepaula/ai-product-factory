"""Owner-operated exact-SHA external security repair settlement.

Does not run a model, rewrite code, suppress a failed security finding, or
release production. Keeps original failed review, blocked executor and audit
immutable; the new SHA must pass all independent gates from zero.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from .architecture_guardian import scan_pull_request_files
from .blocked_release_candidate import (
    BlockedCandidateRecoveryDenied, exact_sha_ci_state,
    require, one,
)
from .github_rest import GitHubRestAdapter
from .supabase_delivery_store import SupabaseDeliveryStore
from .admission_diagnostics import SupabaseAdmissionReader
from .work_unit_context import redact_repository_text


_SHA=re.compile(r"[a-f0-9]{40}\Z")
_UUID=re.compile(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}\Z")

# A test assertion that compares a header to a clearly synthetic, well-known
# fake JWT is not itself an authorization header, and cannot authorize an API
# call. Permit *only* the asserted fixture shape. Never ignore actual Bearer
# values in source, assignments, requests or non-test files.
_SYNTHETIC_BEARER_EXPECT=re.compile(
    r'''(?m)(?P<before>\bexpect\([^()\r\n]{1,128}\)\.toBe\(\s*["'])'''
    r'''Bearer synthetic\.user\.jwt(?P<after>["']\s*\)\s*;)'''
)


def safe_test_assertions_for_secret_scan(value:str,path:str)->str:
    if not re.search(r"\.(?:test|spec)\.(?:ts|tsx|js|jsx)$",path):
        return value
    return _SYNTHETIC_BEARER_EXPECT.sub(
        lambda m: m.group("before")+"Bearer <asserted-fixture>"+m.group("after"),
        value,
    )


def settle_verified_security_repair(
    *,run_id:str,pr_number:int,read=None,github_factory=None,store=None,
    ci_verifier=None,
)->dict:
    require(isinstance(run_id,str) and _UUID.fullmatch(run_id) is not None
            and type(pr_number) is int and 1<=pr_number<=2_147_483_647,
            "invalid_security_repair_identity")
    read=read or SupabaseAdmissionReader()._get
    store=store or SupabaseDeliveryStore()
    github_factory=github_factory or (lambda repo:GitHubRestAdapter(repository=repo))
    ci_verifier=ci_verifier or exact_sha_ci_state
    root=one(read,"factory_runs",
        "id,task_id,status,candidate_commit,branch_name,metadata,lease_owner,lease_expires_at"
        "&id=eq."+quote(run_id,safe="")+"&limit=2")
    meta=root.get("metadata")
    old=root.get("candidate_commit")
    require(root.get("id")==run_id and root.get("status")=="specialist_review_failed"
            and isinstance(old,str) and _SHA.fullmatch(old) is not None
            and isinstance(meta,dict) and meta.get("source")=="change-set"
            and isinstance(meta.get("change_set_id"),str)
            and _UUID.fullmatch(meta["change_set_id"]) is not None
            and root.get("lease_owner") is None and root.get("lease_expires_at") is None,
            "root_security_review_identity_mismatch")
    cs=one(read,"factory_change_sets",
        "id,project_id,root_task_id,release_run_id,status,candidate_commit,"
        "integration_branch,current_wave,metadata,lease_owner,lease_expires_at"
        "&id=eq."+quote(meta["change_set_id"],safe="")+"&limit=2")
    blocker=(cs.get("metadata") or {}).get("blocker")
    request=(cs.get("metadata") or {}).get("integration_release_request")
    require(cs.get("status")=="blocked" and cs.get("release_run_id") is None
            and cs.get("candidate_commit")==old and cs.get("root_task_id")==root["task_id"]
            and cs.get("lease_owner") is None and cs.get("lease_expires_at") is None
            and isinstance(blocker,dict)
            and blocker.get("type")=="implementation_preflight_error"
            and isinstance(request,dict)
            and request.get("pr_number")==pr_number and request.get("candidate_commit")==old
            and request.get("branch")==cs.get("integration_branch")
            and root.get("branch_name")==cs.get("integration_branch"),
            "blocked_security_repair_change_set_mismatch")
    repo=one(read,"factory_projects",
        "id,repository,project_kind,is_active"
        "&id=eq."+quote(cs["project_id"],safe="")+"&limit=2")
    repository=repo.get("repository")
    require(repo.get("is_active") is True and repo.get("project_kind")=="greenfield"
            and isinstance(repository,str) and repository.count("/")==1,
            "source_greenfield_not_active")
    repair_rows=read("factory_repair_jobs?select=id,source_run_id,source_role,status,"
        "change_set_id,project_id,candidate_commit,cycle,work_unit_id,task_id,"
        "write_scopes,finding"
        "&source_run_id=eq."+quote(run_id,safe="")+
        "&status=eq.queued&order=created_at.desc&limit=2")
    require(isinstance(repair_rows,list) and len(repair_rows)==1,
            "single_bounded_security_repair_required")
    repair=repair_rows[0]
    scopes=repair.get("write_scopes")
    finding=repair.get("finding")
    require(repair.get("status")=="queued" and repair.get("source_role")=="security"
            and repair.get("source_run_id")==run_id
            and repair.get("change_set_id")==cs["id"]
            and repair.get("project_id")==cs["project_id"]
            and repair.get("candidate_commit")==old
            and isinstance(scopes,list) and len(scopes)==1
            and isinstance(scopes[0],str)
            and isinstance(finding,dict) and finding.get("path")==scopes[0]
            and finding.get("code")=="supabase_secret"
            and finding.get("kind")=="secret_scan"
            and blocker.get("reason")==
              "PermissionError: editable repository context contains redacted secret: "+scopes[0],
            "security_repair_scope_not_verified")
    unit=one(read,"factory_change_set_work_units",
        "id,task_id,run_id,status,base_commit,output_commit"
        "&id=eq."+quote(repair["work_unit_id"],safe="")+"&limit=2")
    require(unit.get("id")==repair["work_unit_id"]
            and unit.get("status")=="blocked" and unit.get("base_commit")==old
            and unit.get("output_commit") is None
            and unit.get("task_id")==repair["task_id"]
            and blocker.get("work_unit_id")==unit.get("id")
            and blocker.get("run_id")==unit.get("run_id"),
            "blocked_work_unit_mismatch")
    github=github_factory(repository)
    pr=github.get_pull_request(pr_number)
    new=pr.head_sha
    require(pr.state=="open" and pr.merged is False and pr.draft is False
            and pr.number==pr_number and pr.base_ref=="main"
            and pr.head_repository==repository
            and pr.head_ref==cs["integration_branch"]
            and isinstance(new,str) and _SHA.fullmatch(new) is not None
            and new!=old and github.get_branch_sha(pr.head_ref)==new,
            "pr_changed_or_wrong_target")
    cmp=github.compare_commits(old,new)
    changed=cmp.get("files")
    require(cmp.get("status")=="ahead" and cmp.get("ahead_by")==1
            and cmp.get("behind_by")==0 and changed==scopes,
            "security_repair_not_exact_one_file")
    content=github.get_file_text(scopes[0],ref=new)
    require(isinstance(content,str) and bool(content.strip()),
            "candidate_source_missing")
    scan_content=safe_test_assertions_for_secret_scan(content,scopes[0])
    require(redact_repository_text(scan_content)==scan_content
            and "sb_"+"secret_" not in content
            and "-----BEGIN " not in content,
            "candidate_contains_secret_like_source")
    file_details=github.get_pull_request_file_details(pr_number)
    security=scan_pull_request_files(file_details)
    require(not security.evidence.get("unreviewable_paths")
            and security.evidence.get("blocking_findings")==0,
            "new_candidate_security_guardian_did_not_pass")
    ci=ci_verifier(github,new)
    require(ci.get("source")=="github_actions_checks"
            and ci.get("completed_native_checks",0)>=2
            and ci.get("workflows",0)>=1,
            "new_exact_sha_ci_not_green")
    again=github.get_pull_request(pr_number)
    require(again.head_sha==new and again.state=="open" and again.merged is False
            and again.head_ref==cs["integration_branch"]
            and again.head_repository==repository and again.base_ref=="main"
            and github.get_branch_sha(again.head_ref)==new,
            "security_repair_sha_moved_during_verification")
    evidence={
        "old_sha":old,"new_sha":new,"pr_number":str(pr_number),
        "repository":repository,"branch":cs["integration_branch"],
        "compare_status":"ahead","ahead_by":"1","behind_by":"0",
        "changed_files":changed,"changed_files_count":"1",
        "ci_conclusion":"success","ci_source":"github_actions_checks",
        "ci_native_checks":ci["completed_native_checks"],
        "security_secret_scan":"clean","release_authorized":False,
        "no_model_calls":True,"review_pass_claimed":False,
    }
    result=store._rpc("factory_settle_verified_blocked_security_repair_v1",{
        "p_change_set_id":cs["id"],"p_root_run_id":run_id,
        "p_repair_job_id":repair["id"],"p_old_sha":old,
        "p_new_sha":new,"p_pr_number":pr_number,"p_evidence":evidence,
    })
    require(isinstance(result,dict) and result.get("status")=="ci_pending"
            and result.get("run_id")==run_id
            and result.get("repair_id")==repair["id"]
            and result.get("candidate_commit")==new
            and result.get("release_authorized") is False
            and result.get("old_evidence_preserved") is True
            and result.get("new_specialist_review_required") is True,
            "security_repair_settlement_receipt_inconsistent")
    return result
