from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

_SECRET_KEY=re.compile(r"(?:^|_)(?:secret|password|passwd|token|credential|private_key|service_role|api_key)(?:$|_)",re.I)
_SECRET_VALUE=re.compile(r"(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|sb_secret_[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{12,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|Bearer\s+[A-Za-z0-9._~-]{16,})",re.I)


@dataclass(frozen=True)
class ContextPacket:
    version:int
    payload:dict
    sha256:str

    def as_dict(self)->dict:
        return {"version":self.version,"sha256":self.sha256,**self.payload}


def _sanitize(value:Any,path:str="root")->Any:
    if isinstance(value,dict):
        out={}
        for key,item in value.items():
            key_text=str(key)
            if _SECRET_KEY.search(key_text):
                if item not in (None,"",False,0,[],{}):
                    raise ValueError(f"secret-bearing context field is forbidden: {path}.{key_text}")
                continue
            out[key_text]=_sanitize(item,f"{path}.{key_text}")
        return out
    if isinstance(value,(list,tuple)):
        return [_sanitize(item,f"{path}[]") for item in value]
    if isinstance(value,str):
        if _SECRET_VALUE.search(value):
            raise ValueError(f"secret-like value is forbidden in context packet: {path}")
        return value
    if value is None or isinstance(value,(bool,int,float)):
        return value
    return str(value)


def redact_repository_text(value:str)->str:
    redacted=_SECRET_VALUE.sub("[REDACTED_SECRET]",value)
    return redacted.replace("sb_"+"secret_","[REDACTED_SUPABASE_SECRET_PREFIX]")


def _normalize_scopes(scopes:Iterable[str])->tuple[str,...]:
    out=[]
    for raw in scopes:
        value=str(raw).strip().replace("\\","/")
        value=value.removeprefix("./").strip("/")
        if not value or value.startswith("../") or "/../" in value:
            raise ValueError("invalid write scope")
        if value not in out:
            out.append(value)
    return tuple(out)


def path_is_within_scopes(path:str,scopes:Iterable[str])->bool:
    normalized=path.strip().replace("\\","/").removeprefix("./")
    if not normalized or normalized.startswith("/") or normalized.startswith("../") or "/../" in normalized:
        return False
    for scope in _normalize_scopes(scopes):
        if scope==".":
            return True
        prefix=scope[:-3] if scope.endswith("/**") else scope
        prefix=prefix.rstrip("/")
        if normalized==prefix or normalized.startswith(prefix+"/"):
            return True
    return False


def enforce_write_scopes(paths:Iterable[str],scopes:Iterable[str])->None:
    allowed=_normalize_scopes(scopes)
    if not allowed:
        raise PermissionError("work unit has no explicit write scopes")
    outside=sorted(path for path in paths if not path_is_within_scopes(path,allowed))
    if outside:
        raise PermissionError("implementation attempted writes outside assigned scopes: "+", ".join(outside))


def build_context_packet(*,source:dict,impact:dict|None,base_commit:str,branch:str,repository_snapshot:dict[str,str]|None=None)->ContextPacket:
    task=source.get("task") if isinstance(source.get("task"),dict) else {}
    assignment=source.get("assignment") if isinstance(source.get("assignment"),dict) else {}
    repair=source.get("repair") if isinstance(source.get("repair"),dict) else {}
    scopes=assignment.get("scope_keys") if isinstance(assignment.get("scope_keys"),list) else repair.get("write_scopes")
    scopes=list(_normalize_scopes(scopes or ()))
    repository={
        "project_key":str(source.get("project_key") or ""),
        "repository":str(source.get("repository") or ""),
        "exact_base_commit":base_commit,
        "work_branch":branch,
        "write_scopes":scopes,
    }
    proof=source.get("repin_evidence")
    candidate_proof=source.get("ci_repair_evidence")
    is_existing_ci_repair=(source.get("project_kind")=="existing"
        and repair.get("repair_kind")=="ci")
    if is_existing_ci_repair:
        # A newer CI repair candidate is NOT the imported Preview source.
        # Its authority is the already-verified PR and bounded failure
        # lineage, not a fabricated second project repin.
        target=source.get("delivery_target")
        if (not isinstance(candidate_proof,dict) or not isinstance(target,dict)
            or candidate_proof.get("kind")!="verified_native_ci_repair_candidate"
            or candidate_proof.get("candidate_commit")!=base_commit
            or candidate_proof.get("repository")!=repository["repository"]
            or candidate_proof.get("project_key")!=repository["project_key"]
            or candidate_proof.get("base_preview_sha")!=target.get("sha")
            or candidate_proof.get("base_preview_branch")!=target.get("branch")
            or candidate_proof.get("integration_branch")!=repair.get("branch")
            or candidate_proof.get("pr_number")!=repair.get("pr_number")
            or candidate_proof.get("repair_request_id")!=repair.get("repair_request_id")
            or candidate_proof.get("attempt")!=repair.get("attempt")
            or candidate_proof.get("max_attempts")!=repair.get("max_attempts")
            or candidate_proof.get("write_scopes")!=scopes
            or repair.get("write_scopes")!=scopes):
            raise PermissionError("verified CI repair candidate evidence missing or drifted")
        repository["ci_repair_candidate_evidence"]=dict(candidate_proof)
    elif candidate_proof is not None:
        raise PermissionError("CI repair candidate evidence cannot authorize a non-repair run")
    elif proof is not None:
        target=source.get("delivery_target")
        if (not isinstance(target,dict) or not isinstance(proof,dict)
            or proof.get("kind")!="control_plane_native_ci_repin"
            or proof.get("sha")!=base_commit
            or proof.get("ci_sha")!=base_commit
            or proof.get("sha")!=target.get("sha")
            or proof.get("project_key")!=repository["project_key"]
            or proof.get("repository")!=repository["repository"]
            or proof.get("repository")!=target.get("repository")
            or proof.get("branch")!=target.get("branch")
            or proof.get("candidate_pr_number")!=target.get("candidate_pr_number")
            or type(proof.get("audit_event_id")) is not int
            or proof["audit_event_id"]<=0
            or type(proof.get("ci_run_id")) is not int or proof["ci_run_id"]<=0
            or type(proof.get("generation")) is not int or proof["generation"]<=0):
            raise PermissionError("repin evidence does not match exact pinned source")
        repository["delivery_repin_evidence"]=dict(proof)
    packet={
        "objective":{
            "title":str(task.get("title") or ""),
            "description":str(task.get("description") or ""),
            "acceptance_criteria":task.get("acceptance_criteria") if isinstance(task.get("acceptance_criteria"),list) else [],
        },
        "work_unit":{
            "task_key":str(source.get("plan_task_key") or ""),
            "agent_key":str(source.get("agent_key") or ""),
            "wave":int(source.get("wave") or 1),
            "required_capabilities":assignment.get("required_capabilities") if isinstance(assignment.get("required_capabilities"),list) else [],
            "depends_on":assignment.get("depends_on") if isinstance(assignment.get("depends_on"),list) else [],
        },
        "repository":repository,
        "sandbox":{
            "isolation":"work_unit_branch",
            "exact_base_required":True,
            "write_scope_enforced":True,
            "secrets_in_context":False,
            "github_credentials_in_model_context":False,
        },
        "impact":impact or {},
        "repository_snapshot":repository_snapshot or {},
        "human_decisions":source.get("human_decisions") if isinstance(source.get("human_decisions"),list) else [],
        "governance_amendment":source.get("verified_governance_amendment")
            if isinstance(source.get("verified_governance_amendment"),dict) else None,
        "repair":repair,
        "constraints":source.get("constraints") if isinstance(source.get("constraints"),list) else [],
    }
    clean=_sanitize(packet)
    canonical=json.dumps(clean,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return ContextPacket(version=1,payload=clean,sha256=hashlib.sha256(canonical).hexdigest())
