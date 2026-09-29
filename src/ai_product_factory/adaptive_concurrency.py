from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConcurrencyPressure:
    runnable_work:int
    quota_status:str="normal"
    unknown_paid_cost:bool=False
    conflict_rate:float=0.0
    repair_rate:float=0.0
    first_pass_yield:float=1.0
    ci_queue_minutes:float=0.0


@dataclass(frozen=True)
class ConcurrencyDecision:
    agent_key:str
    profile_ceiling:int
    effective_concurrency:int
    reasons:tuple[str,...]
    pressure:ConcurrencyPressure


def decide_effective_concurrency(*,agent_key:str,profile_ceiling:int,pressure:ConcurrencyPressure)->ConcurrencyDecision:
    if profile_ceiling<1:
        raise ValueError("profile ceiling must be positive")
    if pressure.runnable_work<0:
        raise ValueError("runnable work cannot be negative")
    for name,value in (
        ("conflict_rate",pressure.conflict_rate),
        ("repair_rate",pressure.repair_rate),
        ("first_pass_yield",pressure.first_pass_yield),
    ):
        if value<0 or value>1:
            raise ValueError(f"{name} must be between 0 and 1")

    reasons=[]
    effective=min(profile_ceiling,pressure.runnable_work)
    reasons.append(f"bounded by profile ceiling={profile_ceiling} and runnable work={pressure.runnable_work}")

    if pressure.unknown_paid_cost:
        return ConcurrencyDecision(agent_key,profile_ceiling,0,tuple(reasons+["unknown paid cost blocks execution"]),pressure)

    quota=pressure.quota_status.lower().strip()
    if quota in {"blocked","critical"}:
        return ConcurrencyDecision(agent_key,profile_ceiling,0,tuple(reasons+[f"resource quota is {quota}"]),pressure)
    if quota=="unknown":
        effective=min(effective,1)
        reasons.append("unknown provider quota caps concurrency at 1")
    elif quota=="attention":
        effective=min(effective,1)
        reasons.append("provider quota attention caps concurrency at 1")

    if pressure.conflict_rate>=0.25:
        effective=min(effective,1)
        reasons.append("recent conflict rate is high")
    elif pressure.conflict_rate>=0.10 and effective>1:
        effective=max(1,effective-1)
        reasons.append("recent conflict rate reduces concurrency by one")

    if pressure.repair_rate>=0.35:
        effective=min(effective,1)
        reasons.append("recent repair rate is high")
    elif pressure.repair_rate>=0.15 and effective>1:
        effective=max(1,effective-1)
        reasons.append("recent repair rate reduces concurrency by one")

    if pressure.first_pass_yield<0.60:
        effective=min(effective,1)
        reasons.append("low first-pass yield caps concurrency at 1")

    if pressure.ci_queue_minutes>=20:
        effective=min(effective,1)
        reasons.append("CI queue latency caps concurrency at 1")
    elif pressure.ci_queue_minutes>=10 and effective>1:
        effective=max(1,effective-1)
        reasons.append("CI queue latency reduces concurrency by one")

    effective=max(0,effective)
    if effective==0 and pressure.runnable_work==0:
        reasons.append("no runnable independent work")
    elif effective>0:
        reasons.append(f"effective concurrency={effective}")
    return ConcurrencyDecision(agent_key,profile_ceiling,effective,tuple(reasons),pressure)
