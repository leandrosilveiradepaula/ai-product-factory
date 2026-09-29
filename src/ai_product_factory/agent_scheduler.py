from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .supabase_server import resolve_supabase_server_config


@dataclass(frozen=True)
class AgentProfile:
    agent_key:str
    role:str
    capabilities:tuple[str,...]
    allowed_tools:tuple[str,...]
    model_policy:dict
    max_concurrency:int
    cost_budget_usd:float|None=None
    is_active:bool=True

    def require_tools(self,*tools:str)->None:
        missing=[tool for tool in tools if tool not in self.allowed_tools]
        if missing:
            raise PermissionError(f"agent {self.agent_key} is not allowed to use: {', '.join(missing)}")

@dataclass(frozen=True)
class AgentAssignment:
    assignment_id:str
    agent_id:str
    agent_key:str
    role:str
    max_concurrency:int
    model_policy:dict
    allowed_tools:tuple[str,...]
    run_id:str|None=None
    task_id:str|None=None


class SupabaseAgentScheduler:
    def __init__(self,*,url:str|None=None,service_role_key:str|None=None)->None:
        cfg=resolve_supabase_server_config(url=url,service_role_key=service_role_key)
        self.url=cfg.url;self.headers=cfg.headers

    def _get(self,path:str):
        req=urllib.request.Request(f"{self.url}/rest/v1/{path}",method="GET",headers=self.headers)
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane read failed: {path} ({exc.code})") from exc
        return [] if not raw else json.loads(raw)

    def _rpc(self,name:str,payload:dict):
        req=urllib.request.Request(
            f"{self.url}/rest/v1/rpc/{name}",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={**self.headers,"Content-Type":"application/json"},
        )
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane RPC failed: {name} ({exc.code})") from exc
        return None if not raw else json.loads(raw)

    @staticmethod
    def _assignment(data:dict|None)->AgentAssignment|None:
        if data is None:return None
        return AgentAssignment(
            assignment_id=str(data["assignment_id"]),
            agent_id=str(data["agent_id"]),
            agent_key=str(data["agent_key"]),
            role=str(data["role"]),
            max_concurrency=int(data["max_concurrency"]),
            model_policy=dict(data.get("model_policy") or {}),
            allowed_tools=tuple(str(x) for x in (data.get("allowed_tools") or [])),
            run_id=str(data["run_id"]) if data.get("run_id") else None,
            task_id=str(data["task_id"]) if data.get("task_id") else None,
        )

    def schedule_run(self,*,run_id:str,preferred_role:str|None=None,required_capabilities:tuple[str,...]=(),scope_keys:tuple[str,...]=(),lease_seconds:int=900)->AgentAssignment:
        data=self._rpc("factory_schedule_run_agent",{
            "p_run_id":run_id,
            "p_preferred_role":preferred_role,
            "p_required_capabilities":list(required_capabilities),
            "p_scope_keys":list(scope_keys),
            "p_lease_seconds":lease_seconds,
        })
        assignment=self._assignment(data)
        if assignment is None:raise RuntimeError("agent scheduler returned no assignment")
        return assignment

    def schedule_next(self)->AgentAssignment|None:
        return self._assignment(self._rpc("factory_schedule_next_unassigned_run",{}))

    def release(self,run_id:str,status:str="released")->None:
        self._rpc("factory_release_agent_slot",{"p_run_id":run_id,"p_status":status})

    def work_matrix(self,limit:int=12)->dict:
        data=self._rpc("factory_agent_work_matrix",{"p_limit":limit}) or {}
        return {"direct":list(data.get("direct") or []),"codex":list(data.get("codex") or [])}

    def release_scopes(self,run_id:str)->int:
        result=self._rpc("factory_release_agent_scope_locks",{"p_run_id":run_id})
        return int(result or 0)

    def recover_expired(self)->dict:
        return self._rpc("factory_recover_expired_agent_slots",{}) or {"released":0}


    @staticmethod
    def _profile(row:dict)->AgentProfile:
        return AgentProfile(
            agent_key=str(row["agent_key"]),
            role=str(row["role"]),
            capabilities=tuple(str(x) for x in (row.get("capabilities") or [])),
            allowed_tools=tuple(str(x) for x in (row.get("allowed_tools") or [])),
            model_policy=dict(row.get("model_policy") or {}),
            max_concurrency=int(row.get("max_concurrency") or 1),
            cost_budget_usd=float(row["cost_budget_usd"]) if row.get("cost_budget_usd") is not None else None,
            is_active=bool(row.get("is_active",True)),
        )

    def profiles(self,*,active_only:bool=True)->tuple[AgentProfile,...]:
        suffix="&is_active=eq.true" if active_only else ""
        rows=self._get("factory_agents?select=agent_key,role,capabilities,allowed_tools,model_policy,max_concurrency,cost_budget_usd,is_active&order=agent_key.asc"+suffix)
        return tuple(self._profile(row) for row in rows)

    def profile(self,agent_key:str)->AgentProfile:
        if not agent_key.strip():raise ValueError("agent_key is required")
        rows=self._get("factory_agents?select=agent_key,role,capabilities,allowed_tools,model_policy,max_concurrency,cost_budget_usd,is_active&agent_key=eq."+agent_key+"&limit=1")
        if not rows or not bool(rows[0].get("is_active")):
            raise RuntimeError(f"active agent not found: {agent_key}")
        return self._profile(rows[0])

    def require_route_tools(self,agent_key:str,route:str)->AgentProfile:
        profile=self.profile(agent_key)
        if route=="direct":
            profile.require_tools("github_write","model_primary")
        elif route=="codex":
            profile.require_tools("github_write","codex")
        else:
            raise ValueError(f"unsupported execution route: {route}")
        return profile
