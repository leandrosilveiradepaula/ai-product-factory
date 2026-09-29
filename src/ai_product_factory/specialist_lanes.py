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


def evaluate_security_lane(item:SpecialistLaneItem,github:GitHubRestAdapter)->SpecialistLaneResult:
    pr=github.get_pull_request(item.pr_number)
    if pr.head_sha!=item.candidate_commit:
        return SpecialistLaneResult("blocked",({"code":"candidate_commit_mismatch","severity":"critical","message":"PR head changed during Security review"},),{"candidate_commit":item.candidate_commit})
    details=github.get_pull_request_file_details(item.pr_number)
    report=scan_pull_request_files(details)
    status="failed" if report.evidence["blocking_findings"] else "passed"
    return SpecialistLaneResult(status,report.findings,{
        "candidate_commit":item.candidate_commit,
        "files_reviewed":len(details),
        **report.evidence,
    })


def evaluate_qa_lane(item:SpecialistLaneItem,github:GitHubRestAdapter)->SpecialistLaneResult:
    pr=github.get_pull_request(item.pr_number)
    if pr.head_sha!=item.candidate_commit:
        return SpecialistLaneResult("blocked",({"code":"candidate_commit_mismatch","severity":"critical","message":"PR head changed during QA"},),{"candidate_commit":item.candidate_commit})
    ci=github.get_ci_state(item.pr_number)
    changed=github.get_pull_request_files(item.pr_number)
    if ci is not CIState.SUCCESS:
        return SpecialistLaneResult("failed",({
            "code":"ci_not_green","severity":"error","message":f"candidate CI state is {ci.value}",
            "scope_keys":list(changed),
        },),{"candidate_commit":item.candidate_commit,"ci_state":ci.value,"changed_files":list(changed)})
    return SpecialistLaneResult("passed",(),{
        "candidate_commit":item.candidate_commit,"ci_state":ci.value,
        "changed_files":len(changed),"acceptance_criteria_count":len(item.acceptance_criteria),
        "source":"exact_candidate_github_checks","model_call":False,
    })


def evaluate_operations_lane(item:SpecialistLaneItem,github:GitHubRestAdapter,*,health_reader=None)->SpecialistLaneResult:
    pr=github.get_pull_request(item.pr_number)
    if pr.head_sha!=item.candidate_commit:
        return SpecialistLaneResult("blocked",({"code":"candidate_commit_mismatch","severity":"critical","message":"PR head changed during Operations review"},),{"candidate_commit":item.candidate_commit})
    changed=github.get_pull_request_files(item.pr_number)
    try:
        preview=evaluate_preview_applicability(manifest=item.manifest,changed_files=changed)
    except ValueError as exc:
        return SpecialistLaneResult("blocked",({"code":"invalid_preview_policy","severity":"error","message":str(exc)},),{"candidate_commit":item.candidate_commit})
    reader=health_reader or SupabaseOperationalHealthReader()
    health=reader.read()
    alerts=evaluate_operational_alerts(health)
    blocking=[a for a in alerts if a.severity=="critical" or a.code=="unknown_cost"]
    findings=tuple({"code":a.code,"severity":"critical" if a.severity=="critical" else "error","message":a.message} for a in blocking)
    status="failed" if findings else "passed"
    return SpecialistLaneResult(status,findings,{
        "candidate_commit":item.candidate_commit,
        "preview_required":preview.required,"preview_reason":preview.reason,
        "operational_alerts":[{"code":a.code,"severity":a.severity,"message":a.message} for a in alerts],
        "known_cost":str(health.known_cost),"unknown_cost_events":health.unknown_cost_events,
        "model_call":False,
    })


def evaluate_specialist_lane(item:SpecialistLaneItem,github:GitHubRestAdapter,*,health_reader=None)->SpecialistLaneResult:
    if item.role=="security":return evaluate_security_lane(item,github)
    if item.role=="qa":return evaluate_qa_lane(item,github)
    if item.role=="operations":return evaluate_operations_lane(item,github,health_reader=health_reader)
    raise ValueError(f"unsupported specialist lane role: {item.role}")
