from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .release_policy_engine import ReleasePolicyContext,ReleasePolicyDecision,evaluate_release_policy,load_release_policy


@dataclass(frozen=True)
class ReleaseAssessment:
    decision:ReleasePolicyDecision
    report:dict
    rollback:dict
    context:dict


def _missing_nonhuman(readiness:dict)->tuple[str,...]:
    out=[]
    for row in readiness.get("missing") or []:
        if isinstance(row,dict) and not bool(row.get("human_only")):
            key=str(row.get("key") or "").strip()
            if key:out.append(key)
    return tuple(sorted(set(out)))


def build_release_assessment(
    *,
    policy:dict,
    candidate_commit:str,
    changed_files:tuple[str,...],
    risk:dict,
    facts:dict,
    unknown_paid_cost:bool,
    known_cost:Decimal,
)->ReleaseAssessment:
    readiness=facts.get("definition_of_done") if isinstance(facts.get("definition_of_done"),dict) else {}
    satisfied=set(str(x) for x in readiness.get("satisfied") or [])
    migration_change=any(str(path).startswith("supabase/migrations/") for path in changed_files)
    rollback_verified=(not migration_change) or "rollback_analysis" in satisfied
    context=ReleasePolicyContext(
        production_change=True,
        destructive_data_change=bool(risk.get("destructive_data_change")),
        expands_sensitive_access=bool(risk.get("expands_sensitive_access")),
        new_paid_service=bool(risk.get("new_paid_service")),
        material_requirement_change=bool(risk.get("material_requirement_change")),
        unknown_paid_cost=unknown_paid_cost,
        missing_nonhuman_dod=_missing_nonhuman(readiness),
        migration_change=migration_change,
        rollback_verified=rollback_verified,
    )
    decision=evaluate_release_policy(policy,context)
    previous=facts.get("previous_production")
    rollback={
        "migration_change":migration_change,
        "required":migration_change,
        "verified":rollback_verified,
        "evidence":"rollback_analysis" if "rollback_analysis" in satisfied else None,
        "previous_production":previous,
        "source_candidate":candidate_commit,
        "code_revert_path":"git revert after human merge",
    }
    report={
        "candidate_commit":candidate_commit,
        "changed_files":list(changed_files),
        "requirements":facts.get("requirements") or {"total":0,"with_passing_evidence":0},
        "definition_of_done":readiness,
        "evaluations":facts.get("evaluations") or [],
        "preview":facts.get("preview"),
        "risk":{
            "destructive_data_change":context.destructive_data_change,
            "expands_sensitive_access":context.expands_sensitive_access,
            "new_paid_service":context.new_paid_service,
            "material_requirement_change":context.material_requirement_change,
        },
        "cost":{"known":str(known_cost),"unknown_paid_cost":unknown_paid_cost},
        "blockers":list(decision.reasons) if decision.blocked else [],
        "release_state":decision.outcome,
        "readiness_scope":"release_candidate",
        "product_complete":bool((facts.get("product_readiness") or {}).get("ready") is True),
        "product_readiness":facts.get("product_readiness") or {"ready":False,"status":"not_assessed"},
    }
    serializable_context={
        "production_change":context.production_change,
        "destructive_data_change":context.destructive_data_change,
        "expands_sensitive_access":context.expands_sensitive_access,
        "new_paid_service":context.new_paid_service,
        "material_requirement_change":context.material_requirement_change,
        "unknown_paid_cost":context.unknown_paid_cost,
        "missing_nonhuman_dod":list(context.missing_nonhuman_dod),
        "migration_change":context.migration_change,
        "rollback_verified":context.rollback_verified,
    }
    return ReleaseAssessment(decision,report,rollback,serializable_context)


def default_release_policy_path()->Path:
    return Path(__file__).resolve().parents[2]/"config"/"factory.release-policy.v1.json"


def load_default_release_policy()->dict:
    return load_release_policy(default_release_policy_path())
