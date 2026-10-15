from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .release_policy_engine import ReleasePolicyContext,ReleasePolicyDecision,evaluate_release_policy,load_release_policy
from .product_readiness import assess_product_readiness


@dataclass(frozen=True)
class ReleaseAssessment:
    decision:ReleasePolicyDecision
    report:dict
    rollback:dict
    context:dict


def _missing_nonhuman(readiness:dict)->tuple[str,...]:
    """Only an actual JSON true may defer a check to the human release gate.

    Absent, malformed or contradictory DoD evidence blocks release readiness.
    In particular Python bool("false") is True and cannot be used here.
    """
    if not isinstance(readiness,dict):
        return ("definition_of_done_unverified",)
    satisfied=readiness.get("satisfied")
    missing=readiness.get("missing")
    if not isinstance(satisfied,list) or not isinstance(missing,list):
        return ("definition_of_done_unverified",)
    if any(not isinstance(value,str) or not value.strip() for value in satisfied):
        return ("definition_of_done_invalid_satisfied",)

    satisfied_set={value.strip() for value in satisfied}
    blockers=set()
    # CI evidence is an invariant for every release candidate. An entirely
    # empty DoD list is not a passing assessment, even if well-typed.
    if "github_ci" not in satisfied_set:
        blockers.add("definition_of_done_missing_verified_ci")
    seen_missing=set()
    for row in missing:
        if not isinstance(row,dict):
            blockers.add("definition_of_done_invalid_missing")
            continue
        key=row.get("key")
        if not isinstance(key,str) or not key.strip():
            blockers.add("definition_of_done_invalid_missing")
            continue
        key=key.strip()
        if key in seen_missing:
            blockers.add("definition_of_done_duplicate_missing:"+key)
        seen_missing.add(key)
        if key in satisfied_set:
            blockers.add("definition_of_done_conflicting_status:"+key)

        # Explicit native bool is required. No coercion of strings, numbers
        # or arbitrary objects into permission to skip non-human gates.
        human_only=row.get("human_only",False)
        if human_only is True:
            # Only the actual production merge gate is human-only. A caller
            # cannot relabel CI, QA, Preview, rollback or browser evidence.
            if key == "human_release":
                continue
            blockers.add("definition_of_done_unauthorized_human_only:"+key)
        elif human_only is not False:
            blockers.add("definition_of_done_invalid_human_only:"+key)
        blockers.add(key)
    return tuple(sorted(blockers))



def _verified_product_assessment(
    raw:dict,candidate_commit:str,*,project_kind:object=None,existing_baseline:object=None
)->tuple[dict,bool]:
    """Never trust a summary flag as evidence of whole-product readiness.

    Validate the *full* six-domain product-readiness assessment for this exact
    candidate. Ineligible evidence changes the product label only, never the
    separate human production-release policy decision.
    """
    if not raw:
        return {"ready":False,"status":"not_assessed"},False
    if raw.get("assessed_commit")!=candidate_commit:
        return {**raw,"ready":False,"status":"stale",
                "reason":"assessment commit does not match release candidate"},False

    # The Control Plane provides the durable evaluation row status and
    # baseline_ref separately from result JSON. Never promote an embedded
    # self-reported ready:true when that *row* failed, is missing, or was
    # evaluated against another commit. No fallback from result or facts RPC.
    if raw.get("baseline_ref") != candidate_commit:
        return {**raw,"ready":False,"status":"stale",
                "reason":"recorded evaluation baseline does not match release candidate"},False
    if raw.get("evaluation_status") != "passed":
        return {**raw,"ready":False,"status":"not_ready",
                "reason":"durable product evaluation has not passed"},False

    # A non-passing recorded assessment is never promoted just because its
    # domains happen to look valid. Its explicit recorded state wins.
    if raw.get("ready") is not True or raw.get("status")!="passed":
        return {**raw,"ready":False,"status":"not_ready"},False

    domains=raw.get("domains")
    ref=raw.get("assessment_ref")
    if not isinstance(domains,dict) or not isinstance(ref,str) or not ref.strip():
        return {**raw,"ready":False,"status":"not_ready",
                "reason":"full product assessment requires domains and assessment_ref",
                "blockers":["missing complete product assessment evidence"]},False

    critical=raw.get("blockers",[])
    if (not isinstance(critical,(list,tuple))
        or any(not isinstance(item,str) for item in critical)):
        return {**raw,"ready":False,"status":"not_ready",
                "reason":"invalid product assessment blocker record",
                "blockers":["invalid product assessment blocker record"]},False

    verified=assess_product_readiness(
        assessed_commit=candidate_commit,assessment_ref=ref,
        domains=domains,critical_blockers=tuple(critical),
    )
    result=verified.as_result()
    if not verified.ready:
        result["reason"]="full product assessment did not satisfy required domains"
        return result,False
    if not isinstance(project_kind,str) or not project_kind.strip():
        result.update(ready=False,status="not_ready",
                      reason="trusted project kind not verified")
        result["blockers"].append("project_kind: trusted Control Plane metadata required")
        return result,False
    if project_kind=="existing":
        baseline_ok,reason=_verified_existing_baseline(existing_baseline,candidate_commit)
        if not baseline_ok:
            result.update(ready=False,status="not_ready",
                          reason="existing project baseline has not passed")
            result["blockers"].append(reason)
            return result,False
        result["existing_project_baseline"]={"status":"passed","candidate_commit":candidate_commit}
    return result,True


def _verified_existing_baseline(raw:object,candidate_commit:str)->tuple[bool,str]:
    """Require a separate durable, run-linked full-repository baseline audit.

    A forged baseline nested in product_readiness.result is not evidence.
    This evaluator does not assert GitHub current HEAD or authorize a merge.
    """
    if not isinstance(raw,dict) or raw.get("evaluation_status")!="passed":
        return False,"existing_project_baseline: independent passed evaluation required"
    if raw.get("baseline_ref")!=candidate_commit:
        return False,"existing_project_baseline: durable baseline must match candidate"
    payload=raw.get("result")
    if not isinstance(payload,dict) or payload.get("assessed_commit")!=candidate_commit:
        return False,"existing_project_baseline: current candidate audit is missing"
    if payload.get("verification_state")!="executed":
        return False,"existing_project_baseline: executed audit required"
    if payload.get("blockers")!=[]:
        return False,"existing_project_baseline: unresolved or malformed blockers"
    coverage=payload.get("coverage")
    required={"repository_inventory","inherited_debt","critical_journeys"}
    if (not isinstance(coverage,list) or
        any(not isinstance(v,str) or not v.strip() for v in coverage) or
        not required.issubset(set(coverage))):
        return False,"existing_project_baseline: full repository coverage missing"
    evidence=payload.get("evidence")
    if (not isinstance(evidence,list) or not evidence or
        any(not isinstance(v,str) or not v.strip() for v in evidence)):
        return False,"existing_project_baseline: valid evidence references required"
    return True,""


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
    raw_satisfied=readiness.get("satisfied")
    satisfied={x.strip() for x in raw_satisfied if isinstance(x,str) and x.strip()} if isinstance(raw_satisfied,list) else set()
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
    raw_product=facts.get("product_readiness") if isinstance(facts.get("product_readiness"),dict) else {}
    product_readiness,product_ready=_verified_product_assessment(
        raw_product,candidate_commit,
        project_kind=facts.get("project_kind"),
        existing_baseline=facts.get("existing_project_baseline"),
    )
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
        "product_complete":product_ready,
        "product_readiness":product_readiness,
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
