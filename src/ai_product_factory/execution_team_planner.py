from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable, Sequence

from .agent_scheduler import AgentProfile


_WRITE_CAPABILITIES={"implementation","migration_authoring","integration","debug","ui","ux","figma"}
_SECURITY_CAPABILITIES={"security_review","auth","rls","secrets","supply_chain"}
_QA_CAPABILITIES={"tests","evals","regression","quality_gate","browser_evidence"}
_OPERATIONS_CAPABILITIES={"ci","deployments","quotas","costs","logs","health"}
_GENERIC_BUILDER_ROLES={"development","ui"}
_SPECIALIST_LANE_ROLES={"security","qa","operations"}


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(dict.fromkeys(str(x).strip() for x in value if str(x).strip()))


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+","-",value.lower()).strip("-")


def _task_key(task: dict,index: int) -> str:
    for key in ("task_key","key","external_key","id"):
        value=task.get(key)
        if isinstance(value,str) and value.strip():
            return value.strip()
    title=str(task.get("title") or "").strip()
    return _slug(title) or f"task-{index+1}"


def _scopes_conflict(left: Iterable[str],right: Iterable[str]) -> bool:
    for a in left:
        aa=a.strip().strip("/")
        if not aa:
            continue
        for b in right:
            bb=b.strip().strip("/")
            if not bb:
                continue
            if aa==bb or aa.startswith(bb+"/") or bb.startswith(aa+"/"):
                return True
    return False


def _role_policy_expectations(tasks: list[dict]) -> dict[str, list[str]]:
    expectations: dict[str,list[str]]=defaultdict(list)
    for task in tasks:
        title=str(task.get("title") or "task")
        caps=set(_string_list(task.get("required_capabilities")))
        risk=task.get("risk") if isinstance(task.get("risk"),dict) else {}
        scopes=set(_string_list(task.get("scope_keys")))
        if caps & _SECURITY_CAPABILITIES or bool(risk.get("expands_sensitive_access")) or bool(risk.get("destructive_data_change")):
            expectations["security"].append(f"{title}: security-sensitive capability/risk")
        if caps & _QA_CAPABILITIES:
            expectations["qa"].append(f"{title}: explicit quality capability")
        if caps & _OPERATIONS_CAPABILITIES:
            expectations["operations"].append(f"{title}: operational capability")
        if any(s.startswith(".github/") or "vercel" in s.lower() for s in scopes):
            expectations["operations"].append(f"{title}: CI/deployment scope")
    return dict(expectations)


def _execution_lane(agent: AgentProfile) -> str | None:
    if agent.role in _GENERIC_BUILDER_ROLES and "github_write" in set(agent.allowed_tools):
        return "builder"
    if agent.role in _SPECIALIST_LANE_ROLES and "github_write" not in set(agent.allowed_tools):
        return "specialist"
    return None


def _choose_agent(task: dict,agents: Sequence[AgentProfile]) -> tuple[AgentProfile|None,dict|None]:
    required=set(_string_list(task.get("required_capabilities")))
    preferred=str(task.get("preferred_agent_role") or "").strip()
    eligible=[
        agent for agent in agents
        if (not required or required.issubset(set(agent.capabilities)))
    ]
    if preferred:
        preferred_eligible=[a for a in eligible if a.agent_key==preferred or a.role==preferred]
        if preferred_eligible:
            eligible=preferred_eligible
        elif eligible:
            return None,{
                "code":"preferred_role_unavailable",
                "preferred_role":preferred,
                "required_capabilities":sorted(required),
                "eligible_agents":[a.agent_key for a in eligible],
            }
    if not eligible and not required and not preferred:
        eligible=[a for a in agents if a.agent_key=="development" or a.role=="development"]
    if not eligible:
        coverage={
            cap:[a.agent_key for a in agents if cap in set(a.capabilities)]
            for cap in sorted(required)
        }
        return None,{
            "code":"no_single_agent_covers_task",
            "required_capabilities":sorted(required),
            "capability_coverage":coverage,
        }
    def rank(agent:AgentProfile):
        excess=max(0,len(set(agent.capabilities)-required))
        preferred_rank=0 if preferred and (agent.agent_key==preferred or agent.role==preferred) else 1
        privilege_rank=len(agent.allowed_tools)
        budget=float(agent.cost_budget_usd) if agent.cost_budget_usd is not None else 10**9
        return (preferred_rank,excess,privilege_rank,budget,-agent.max_concurrency,agent.agent_key)
    return sorted(eligible,key=rank)[0],None


def build_execution_team_plan(engineering_plan: dict,agents: Sequence[AgentProfile]) -> dict:
    raw_tasks=engineering_plan.get("tasks")
    tasks=[dict(x) for x in raw_tasks if isinstance(x,dict)] if isinstance(raw_tasks,list) else []
    active=[a for a in agents if a.is_active]
    blockers:list[dict]=[]
    normalized:list[dict]=[]
    aliases:dict[str,str]={}

    for index,task in enumerate(tasks):
        key=_task_key(task,index)
        title=str(task.get("title") or key)
        row={
            "task_key":key,
            "title":title,
            "preferred_agent_role":str(task.get("preferred_agent_role") or "").strip() or None,
            "required_capabilities":list(_string_list(task.get("required_capabilities"))),
            "scope_keys":list(_string_list(task.get("scope_keys"))),
            "depends_on_raw":list(_string_list(task.get("depends_on"))),
        }
        agent,error=_choose_agent(task,active)
        if error:
            blockers.append({"task_key":key,"title":title,**error})
            row["agent_key"]=None;row["agent_role"]=None;row["execution_ready"]=False
        else:
            row["agent_key"]=agent.agent_key
            row["agent_role"]=agent.role
            row["execution_lane"]=_execution_lane(agent)
            row["execution_ready"]=row["execution_lane"] is not None
            if not row["execution_ready"]:
                blockers.append({
                    "task_key":key,
                    "title":title,
                    "code":"execution_lane_unavailable",
                    "agent_key":agent.agent_key,
                    "role":agent.role,
                    "note":"no safe execution lane exists for this specialist profile",
                })
        normalized.append(row)
        for alias in {key,title,_slug(title)}:
            if alias:
                aliases[alias]=key

    by_key={row["task_key"]:row for row in normalized}
    for row in normalized:
        resolved=[]
        for dep in row.pop("depends_on_raw"):
            key=aliases.get(dep) or aliases.get(_slug(dep))
            if not key:
                blockers.append({"task_key":row["task_key"],"title":row["title"],"code":"unresolved_dependency","dependency":dep})
                continue
            if key==row["task_key"]:
                blockers.append({"task_key":row["task_key"],"title":row["title"],"code":"self_dependency","dependency":dep})
                continue
            if key not in resolved:
                resolved.append(key)
        row["depends_on"]=resolved

    waves:list[dict]=[]
    completed:set[str]=set()
    remaining={row["task_key"] for row in normalized if row.get("agent_key") and row.get("execution_ready") and row.get("execution_lane")=="builder"}
    wave_number=1
    while remaining:
        ready=[by_key[key] for key in remaining if set(by_key[key]["depends_on"]).issubset(completed)]
        ready.sort(key=lambda x:x["task_key"])
        if not ready:
            blockers.append({"code":"dependency_cycle_or_blocked_chain","task_keys":sorted(remaining)})
            break
        chosen:list[dict]=[]
        load:dict[str,int]=defaultdict(int)
        for row in ready:
            agent=next((a for a in active if a.agent_key==row["agent_key"]),None)
            if agent is None:
                continue
            if load[agent.agent_key]>=agent.max_concurrency:
                continue
            if any(_scopes_conflict(row["scope_keys"],other["scope_keys"]) for other in chosen):
                continue
            chosen.append(row)
            load[agent.agent_key]+=1
        if not chosen:
            chosen=[ready[0]]
            load[chosen[0]["agent_key"]]=1
        for row in chosen:
            row["wave"]=wave_number
            remaining.remove(row["task_key"])
            completed.add(row["task_key"])
        waves.append({
            "wave":wave_number,
            "task_keys":[row["task_key"] for row in chosen],
            "agent_load":dict(sorted(load.items())),
            "parallel_workers":len(chosen),
        })
        wave_number+=1

    selected_keys=sorted({row["agent_key"] for row in normalized if row.get("agent_key")})
    expectations=_role_policy_expectations(tasks)
    selected=[]
    for key in selected_keys:
        agent=next(a for a in active if a.agent_key==key)
        assigned=[row for row in normalized if row.get("agent_key")==key]
        lane=_execution_lane(agent)
        execution_ready=lane is not None
        selected.append({
            "agent_key":agent.agent_key,
            "role":agent.role,
            "execution_lane":lane,
            "workers_planned":min(agent.max_concurrency,max(1,len(assigned))) if execution_ready else 0,
            "execution_ready":execution_ready,
            "max_concurrency":agent.max_concurrency,
            "task_keys":[row["task_key"] for row in assigned],
            "reasons":[f"owns {len(assigned)} planned task(s)"] + expectations.get(agent.role,[]),
            "allowed_tools":list(agent.allowed_tools),
            "model_policy":agent.model_policy,
        })

    selected_roles={row["role"] for row in selected if row.get("execution_ready")}
    advisory=[]
    for role,reasons in sorted(expectations.items()):
        if role not in selected_roles:
            advisory.append({
                "role":role,
                "code":"specialist_review_recommended",
                "reasons":reasons,
                "execution_ready":False,
                "note":"specialist review is recommended but was not represented as an explicit planned task",
            })

    excluded=[]
    for agent in sorted(active,key=lambda a:a.agent_key):
        if agent.agent_key not in selected_keys:
            excluded.append({
                "agent_key":agent.agent_key,
                "role":agent.role,
                "reason":"no planned task currently requires this specialist",
            })

    peak=max((wave["parallel_workers"] for wave in waves),default=0)
    status="blocked" if blockers else "ready"
    return {
        "version":1,
        "status":status,
        "selection_policy":"minimum-capability-cover-with-least-privilege",
        "source":"deterministic_from_engineering_plan_and_agent_registry",
        "profiles_selected":len(selected),
        "planned_worker_peak":peak,
        "selected_agents":selected,
        "excluded_agents":excluded,
        "task_assignments":normalized,
        "waves":waves,
        "advisory_specialist_lanes":advisory,
        "blockers":blockers,
    }
