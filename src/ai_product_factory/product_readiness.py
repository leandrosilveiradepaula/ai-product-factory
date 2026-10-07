from __future__ import annotations

from dataclasses import dataclass


REQUIRED_DOMAINS=(
    "security",
    "observability_operations",
    "test_strategy",
    "product_experience",
    "documentation",
    "functional_completeness",
)
ALLOWED_DOMAIN_STATUS={"passed","failed","not_applicable"}

REQUIRED_COVERAGE_BY_DOMAIN={
    "security":(
        "authn_authz",
        "data_access_boundaries",
        "secrets_dependencies",
    ),
    "observability_operations":(
        "health",
        "traceability",
        "recovery_alerting",
    ),
    "test_strategy":(
        "unit_integration",
        "critical_e2e",
        "regression_gates",
    ),
    "product_experience":(
        "surface_inventory",
        "responsive",
        "accessibility",
        "states",
    ),
    "documentation":(
        "setup_configuration",
        "operations",
        "release_rollback",
    ),
    "functional_completeness":(
        "requirements_inventory",
        "mock_noop_demo_inventory",
        "critical_journeys",
    ),
}


@dataclass(frozen=True)
class ProductReadinessAssessment:
    assessed_commit:str
    assessment_ref:str
    ready:bool
    status:str
    domains:dict
    blockers:tuple[str,...]

    def as_result(self)->dict:
        return {
            "assessed_commit":self.assessed_commit,
            "assessment_ref":self.assessment_ref,
            "ready":self.ready,
            "status":self.status,
            "domains":self.domains,
            "blockers":list(self.blockers),
        }


def assess_product_readiness(*,assessed_commit:str,assessment_ref:str,domains:dict,critical_blockers:tuple[str,...]=())->ProductReadinessAssessment:
    if not assessed_commit.strip():raise ValueError("assessed_commit is required")
    if not assessment_ref.strip():raise ValueError("assessment_ref is required")
    if not isinstance(domains,dict):raise ValueError("domains must be an object")
    normalized={}
    blockers=[str(x).strip() for x in critical_blockers if str(x).strip()]
    for key in REQUIRED_DOMAINS:
        raw=domains.get(key)
        if not isinstance(raw,dict):
            normalized[key]={"status":"missing","reason":"domain assessment is required"}
            blockers.append(f"{key}: missing assessment")
            continue
        status=str(raw.get("status") or "").strip()
        reason=str(raw.get("reason") or "").strip()
        evidence=[
            str(x).strip()
            for x in (raw.get("evidence") if isinstance(raw.get("evidence"),list) else [])
            if str(x).strip()
        ]
        coverage=[
            str(x).strip()
            for x in (raw.get("coverage") if isinstance(raw.get("coverage"),list) else [])
            if str(x).strip()
        ]
        if status not in ALLOWED_DOMAIN_STATUS:
            normalized[key]={"status":"invalid","reason":"invalid domain status","evidence":evidence,"coverage":coverage}
            blockers.append(f"{key}: invalid status")
            continue
        if status=="not_applicable" and not reason:
            normalized[key]={"status":"invalid","reason":"not_applicable requires explicit reason","evidence":evidence,"coverage":coverage}
            blockers.append(f"{key}: not_applicable without reason")
            continue
        normalized[key]={"status":status,"reason":reason,"evidence":evidence,"coverage":coverage}
        if status=="failed":blockers.append(f"{key}: failed")
        if status=="passed" and not evidence:blockers.append(f"{key}: passed without evidence")
        if status=="passed":
            required=set(REQUIRED_COVERAGE_BY_DOMAIN[key])
            missing=sorted(required-set(coverage))
            if missing:
                blockers.append(f"{key}: missing coverage {','.join(missing)}")
    ready=not blockers and all(normalized[k]["status"] in {"passed","not_applicable"} for k in REQUIRED_DOMAINS)
    return ProductReadinessAssessment(
        assessed_commit=assessed_commit.strip(),assessment_ref=assessment_ref.strip(),
        ready=ready,status="passed" if ready else "not_ready",domains=normalized,blockers=tuple(blockers),
    )
