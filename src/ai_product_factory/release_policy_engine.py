from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReleasePolicyContext:
    production_change:bool=True
    destructive_data_change:bool=False
    expands_sensitive_access:bool=False
    new_paid_service:bool=False
    material_requirement_change:bool=False
    unknown_paid_cost:bool=False
    missing_nonhuman_dod:tuple[str,...]=()
    migration_change:bool=False
    rollback_verified:bool=False


@dataclass(frozen=True)
class ReleasePolicyDecision:
    outcome:str
    reasons:tuple[str,...]
    policy_key:str
    policy_version:int

    @property
    def blocked(self)->bool:
        return self.outcome=="blocked"

    @property
    def ready_for_human_release(self)->bool:
        return self.outcome=="ready_for_human_release"


def load_release_policy(path:str|Path)->dict:
    policy=json.loads(Path(path).read_text())
    if policy.get("production",{}).get("auto_merge_allowed") is not False:
        raise ValueError("release policy must explicitly forbid auto merge")
    if policy.get("production",{}).get("human_release_required") is not True:
        raise ValueError("release policy must require human production release")
    if not isinstance(policy.get("version"),int) or policy["version"]<1:
        raise ValueError("release policy version must be positive")
    return policy


def evaluate_release_policy(policy:dict,context:ReleasePolicyContext)->ReleasePolicyDecision:
    reasons:list[str]=[]
    blockers:list[str]=[]

    if policy.get("production",{}).get("auto_merge_allowed") is not False:
        blockers.append("policy does not forbid auto merge")
    if policy.get("production",{}).get("human_release_required") is not True:
        blockers.append("policy does not require human release")

    if context.unknown_paid_cost:
        blockers.append("unknown paid cost blocks release readiness")
    if context.missing_nonhuman_dod:
        blockers.append("missing Definition of Done checks: "+", ".join(sorted(context.missing_nonhuman_dod)))
    if context.migration_change and policy.get("rollback",{}).get("migration_change_requires_verified_rollback") is True and not context.rollback_verified:
        blockers.append("migration change requires verified rollback or forward-recovery evidence")

    for active,key,message in (
        (context.destructive_data_change,"destructive_data_change","destructive data change requires human gate"),
        (context.expands_sensitive_access,"expands_sensitive_access","sensitive access expansion requires human gate"),
        (context.new_paid_service,"new_paid_service","new paid service requires human gate"),
        (context.material_requirement_change,"material_requirement_change","material requirement change requires human gate"),
        (context.production_change,"production_change","production release requires human gate"),
    ):
        if active and policy.get("gates",{}).get(key)=="human_gate":
            reasons.append(message)

    if blockers:
        return ReleasePolicyDecision(
            "blocked",tuple(blockers+reasons),str(policy.get("policy_key") or "unknown"),int(policy.get("version") or 0)
        )

    if context.production_change:
        if not reasons:
            reasons.append("production release requires human gate")
        return ReleasePolicyDecision(
            "ready_for_human_release",tuple(reasons),str(policy["policy_key"]),int(policy["version"])
        )

    return ReleasePolicyDecision("allowed_nonproduction",tuple(reasons),str(policy["policy_key"]),int(policy["version"]))
