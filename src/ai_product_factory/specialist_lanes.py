from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from .github_loop import CIState
from .github_rest import GitHubRestAdapter
from .operational_alerts import evaluate_operational_alerts
from .preview_policy import evaluate_preview_applicability
from .specialist_lane_queue import SpecialistLaneItem
from .supabase_operational_health import SupabaseOperationalHealthReader


@dataclass(frozen=True)
class SpecialistLaneResult:
    status:str
    findings:tuple[dict,...]
    evidence:dict


_FORBIDDEN_SECURITY_PATTERNS=(
    ("github_auto_merge",re.compile(r"merge_pull_request\s*\("),"critical"),
    ("danger_full_access",re.compile(r"danger-full-access"),"critical"),
    ("pull_request_target",re.compile(r"pull_request_target\s*:"),"critical"),
    ("public_service_role",re.compile(r"NEXT_PUBLIC_[A-Z0-9_]*(?:SERVICE_ROLE|SECRET_KEY)"),"critical"),
    ("security_definer",re.compile(r"security\s+definer",re.I),"error"),
    ("permissive_public_grant",re.compile(r"grant\s+(?:all|select|insert|update|delete).*\s+to\s+(?:public|anon|authenticated)",re.I),"error"),
)
_SENSITIVE_PATH_PARTS=("auth","security","supabase/migrations",".github/workflows","vercel.json","package.json","lock")


def _patch_text(rows:tuple[dict,...])->str:
    return "\n".join(str(row.get("patch") or "") for row in rows)


def evaluate_security_lane(item:SpecialistLaneItem,github:GitHubRestAdapter)->SpecialistLaneResult:
    pr=github.get_pull_request(item.pr_number)
    if pr.head_sha!=item.candidate_commit:
        return SpecialistLaneResult("blocked",({"code":"candidate_commit_mismatch","severity":"critical","message":"PR head changed during Security review"},),{"candidate_commit":item.candidate_commit})
    details=github.get_pull_request_file_details(item.pr_number)
    patch=_patch_text(details)
    findings=[]
    for code,pattern,severity in _FORBIDDEN_SECURITY_PATTERNS:
        if pattern.search(patch):
            findings.append({"code":code,"severity":severity,"message":f"deterministic Security invariant matched: {code}"})
    sensitive=sorted({str(row.get("filename") or "") for row in details if any(part in str(row.get("filename") or "").lower() for part in _SENSITIVE_PATH_PARTS)})
    status="failed" if any(x["severity"] in {"critical","error"} for x in findings) else "passed"
    return SpecialistLaneResult(status,tuple(findings),{
        "candidate_commit":item.candidate_commit,
        "files_reviewed":len(details),
        "sensitive_paths":sensitive,
        "checks":"deterministic_forbidden_pattern_scan",
        "model_call":False,
    })


def evaluate_qa_lane(item:SpecialistLaneItem,github:GitHubRestAdapter)->SpecialistLaneResult:
    pr=github.get_pull_request(item.pr_number)
    if pr.head_sha!=item.candidate_commit:
        return SpecialistLaneResult("blocked",({"code":"candidate_commit_mismatch","severity":"critical","message":"PR head changed during QA"},),{"candidate_commit":item.candidate_commit})
    ci=github.get_ci_state(item.pr_number)
    if ci is not CIState.SUCCESS:
        return SpecialistLaneResult("failed",({"code":"ci_not_green","severity":"error","message":f"candidate CI state is {ci.value}"},),{"candidate_commit":item.candidate_commit,"ci_state":ci.value})
    changed=github.get_pull_request_files(item.pr_number)
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
