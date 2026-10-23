from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .github_loop import CIState
from .github_rest import GitHubRestAdapter
from .operational_alerts import evaluate_operational_alerts
from .preview_policy import evaluate_preview_applicability
from .specialist_lane_queue import SpecialistLaneItem
from .supabase_operational_health import SupabaseOperationalHealthReader
from .architecture_guardian import scan_pull_request_files


@dataclass(frozen=True)
class SpecialistLaneResult:
    status:str
    findings:tuple[dict,...]
    evidence:dict


def _blocked_candidate(item:SpecialistLaneItem,code:str,message:str)->SpecialistLaneResult:
    # A stale/malformed GitHub snapshot is not a failed implementation task.
    # Keep it out of automated security/QA repair and do not assert a PASS.
    return SpecialistLaneResult("blocked",(
        {"code":code,"severity":"critical","message":message},
    ),{"candidate_commit":item.candidate_commit,"model_call":False})


def _candidate_witness(item:SpecialistLaneItem,pr)->tuple[tuple[str,...]|None,SpecialistLaneResult|None]:
    if getattr(pr,"head_sha",None)!=item.candidate_commit:
        return None,_blocked_candidate(item,"candidate_commit_mismatch",
            "PR head changed during specialist review")
    if (getattr(pr,"state",None)!="open" or getattr(pr,"merged",None) is not False
        or getattr(pr,"draft",None) is not False):
        return None,_blocked_candidate(item,"candidate_pr_ineligible",
            "Specialist review requires an open, non-draft, unmerged PR")
    if (getattr(pr,"number",None)!=item.pr_number
        or not isinstance(item.branch,str) or not item.branch
        or getattr(pr,"head_ref",None)!=item.branch
        or getattr(pr,"head_repository",None)!=item.repository):
        return None,_blocked_candidate(item,"candidate_pr_origin_mismatch",
            "PR number, repository or branch differs from durable run identity")
    base=getattr(pr,"base_ref",None)
    base_sha=getattr(pr,"base_sha",None)
    if not isinstance(base,str) or not base or not isinstance(base_sha,str) or not base_sha:
        return None,_blocked_candidate(item,"candidate_base_unverified",
            "PR base identity is unavailable")
    return (pr.head_sha,pr.head_ref,pr.head_repository,base,base_sha),None


def _begin_review(item:SpecialistLaneItem,github:GitHubRestAdapter):
    return _candidate_witness(item,github.get_pull_request(item.pr_number))


def _finish_review(item:SpecialistLaneItem,github:GitHubRestAdapter,
                   initial:tuple[str,...],result:SpecialistLaneResult)->SpecialistLaneResult:
    # GitHub PR contents, CI and environment may change while being read.
    # Do not persist the result if either the PR or branch moved mid-review.
    current,blocked=_begin_review(item,github)
    if blocked is not None:
        return blocked
    if current!=initial:
        return _blocked_candidate(item,"candidate_identity_drift",
            "PR head, source branch or base changed during specialist review")
    if github.get_branch_sha(item.branch)!=item.candidate_commit:
        return _blocked_candidate(item,"candidate_branch_drift",
            "Source branch no longer points at the reviewed candidate")
    return result


def evaluate_security_lane(item:SpecialistLaneItem,github:GitHubRestAdapter)->SpecialistLaneResult:
    witness,blocked=_begin_review(item,github)
    if blocked is not None:return blocked
    details=github.get_pull_request_file_details(item.pr_number)
    report=scan_pull_request_files(details)
    # Unavailable patch bytes/binary files cannot count as inspected code.
    # Report evidence as blocked rather than sending an invented repair task.
    if report.evidence["unreviewable_paths"]:
        status="blocked"
    else:
        status="failed" if report.evidence["blocking_findings"] else "passed"
    result=SpecialistLaneResult(status,report.findings,{
        "candidate_commit":item.candidate_commit,
        "files_reviewed":len(details),
        **report.evidence,
    })
    return _finish_review(item,github,witness,result)


def evaluate_qa_lane(item:SpecialistLaneItem,github:GitHubRestAdapter)->SpecialistLaneResult:
    witness,blocked=_begin_review(item,github)
    if blocked is not None:return blocked
    ci=github.get_ci_state(item.pr_number)
    changed=github.get_pull_request_files(item.pr_number)
    if ci is not CIState.SUCCESS:
        result=SpecialistLaneResult("failed",({
            "code":"ci_not_green","severity":"error","message":f"candidate CI state is {ci.value}",
            "scope_keys":list(changed),
        },),{"candidate_commit":item.candidate_commit,"ci_state":ci.value,"changed_files":list(changed)})
    else:
        result=SpecialistLaneResult("passed",(),{
            "candidate_commit":item.candidate_commit,"ci_state":ci.value,
            "changed_files":len(changed),"acceptance_criteria_count":len(item.acceptance_criteria),
            "source":"exact_candidate_github_checks","model_call":False,
        })
    return _finish_review(item,github,witness,result)


def evaluate_operations_lane(item:SpecialistLaneItem,github:GitHubRestAdapter,*,health_reader=None)->SpecialistLaneResult:
    witness,blocked=_begin_review(item,github)
    if blocked is not None:return blocked
    changed=github.get_pull_request_files(item.pr_number)
    try:
        preview=evaluate_preview_applicability(manifest=item.manifest,changed_files=changed)
    except ValueError as exc:
        result=SpecialistLaneResult("blocked",({"code":"invalid_preview_policy","severity":"error","message":str(exc)},),{"candidate_commit":item.candidate_commit})
        return _finish_review(item,github,witness,result)
    reader=health_reader or SupabaseOperationalHealthReader()
    health=reader.read()
    alerts=evaluate_operational_alerts(health)
    blocking=[a for a in alerts if a.severity=="critical" or a.code=="unknown_cost"]
    findings=tuple({"code":a.code,"severity":"critical" if a.severity=="critical" else "error","message":a.message} for a in blocking)
    status="failed" if findings else "passed"
    result=SpecialistLaneResult(status,findings,{
        "candidate_commit":item.candidate_commit,
        "preview_required":preview.required,"preview_reason":preview.reason,
        "operational_alerts":[{"code":a.code,"severity":a.severity,"message":a.message} for a in alerts],
        "known_cost":str(health.known_cost),"unknown_cost_events":health.unknown_cost_events,
        "model_call":False,
    })
    return _finish_review(item,github,witness,result)


def evaluate_specialist_lane(item:SpecialistLaneItem,github:GitHubRestAdapter,*,health_reader=None)->SpecialistLaneResult:
    if item.role=="security":return evaluate_security_lane(item,github)
    if item.role=="qa":return evaluate_qa_lane(item,github)
    if item.role=="operations":return evaluate_operations_lane(item,github,health_reader=health_reader)
    raise ValueError(f"unsupported specialist lane role: {item.role}")
