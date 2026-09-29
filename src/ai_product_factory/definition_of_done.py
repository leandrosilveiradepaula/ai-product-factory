from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Iterable


_SECURITY_CAPS={"security_review","auth","rls","secrets","supply_chain"}
_OPERATIONS_CAPS={"ci","deployments","quotas","costs","logs","health"}
_IMPLEMENTATION_CAPS={"implementation","integration","debug","migration_authoring","ui","ux","figma"}


@dataclass(frozen=True)
class DoDCheck:
    key:str
    phase:str
    reason:str
    evidence_type:str
    human_only:bool=False


@dataclass(frozen=True)
class DefinitionOfDone:
    checks:tuple[DoDCheck,...]

    def as_records(self)->list[dict]:
        return [
            {
                "key":x.key,"phase":x.phase,"reason":x.reason,
                "evidence_type":x.evidence_type,"human_only":x.human_only,
            }
            for x in self.checks
        ]


def _preview_required(manifest:dict,scopes:set[str])->bool:
    preview=manifest.get("preview") if isinstance(manifest.get("preview"),dict) else {}
    if preview.get("required") is False:
        return False
    paths=preview.get("required_paths")
    if isinstance(paths,list) and paths:
        for scope in scopes:
            if any(fnmatch.fnmatch(scope,p) or fnmatch.fnmatch(scope+"/x",p) for p in paths if isinstance(p,str)):
                return True
        return False
    return True


def compile_definition_of_done(*,engineering_plan:dict,manifest:dict|None=None,requirement_count:int=0)->DefinitionOfDone:
    manifest=manifest or {}
    tasks=[x for x in engineering_plan.get("tasks",[]) if isinstance(x,dict)] if isinstance(engineering_plan.get("tasks"),list) else []
    caps:set[str]=set()
    scopes:set[str]=set()
    sensitive_risk=False
    for task in tasks:
        if isinstance(task.get("required_capabilities"),list):
            caps.update(str(x) for x in task["required_capabilities"])
        if isinstance(task.get("scope_keys"),list):
            scopes.update(str(x) for x in task["scope_keys"])
        risk=task.get("risk") if isinstance(task.get("risk"),dict) else {}
        sensitive_risk=sensitive_risk or bool(risk.get("expands_sensitive_access")) or bool(risk.get("destructive_data_change"))

    checks:dict[str,DoDCheck]={}
    def add(key:str,phase:str,reason:str,evidence_type:str,human_only:bool=False)->None:
        checks.setdefault(key,DoDCheck(key,phase,reason,evidence_type,human_only))

    if requirement_count:
        add("requirements_traceable","planning","planned acceptance criteria must be traceable","requirements_traceable")
    add("github_ci","pre_preview","every release candidate must pass exact-candidate CI","github_ci")

    if caps & _IMPLEMENTATION_CAPS:
        add("qa","pre_preview","implementation work requires independent QA","qa")
    if caps & _SECURITY_CAPS or sensitive_risk or any(
        s.startswith("supabase/migrations") or s.startswith(".github/workflows") or "auth" in s.lower()
        for s in scopes
    ):
        add("security_review","pre_preview","security-sensitive change requires independent Security review","security")
    if caps & _OPERATIONS_CAPS or any(
        s.startswith(".github/workflows") or "vercel" in s.lower() for s in scopes
    ):
        add("operations_review","pre_preview","operational surface requires Operations verification","operations")
    if any(s.startswith("supabase/migrations") for s in scopes) or "migration_authoring" in caps:
        add("migration_validation","pre_preview","database migration requires deterministic validation","migration_validation")
        add("rollback_analysis","pre_preview","database migration requires rollback/forward-recovery analysis","rollback_analysis")
    if any("/api" in s.lower() or s.lower().endswith("api") or s.lower().startswith("src/api") for s in scopes):
        add("api_contract","pre_preview","API surface requires contract compatibility evidence","api_contract")

    if _preview_required(manifest,scopes):
        add("preview","post_ci","deployable change requires exact-candidate Preview","preview")
        add("browser_evidence","post_ci","Preview requires browser evidence","browser_evidence")

    add("human_release","release","production merge is always a human gate","human_release",True)
    return DefinitionOfDone(tuple(checks.values()))


def evaluate_definition_of_done(*,definition:DefinitionOfDone,evidence_types:Iterable[str])->dict:
    observed=set(str(x) for x in evidence_types)
    satisfied=[]
    missing=[]
    for check in definition.checks:
        target=missing if check.evidence_type not in observed else satisfied
        target.append(check.key)
    return {"ready":not missing,"satisfied":satisfied,"missing":missing}
