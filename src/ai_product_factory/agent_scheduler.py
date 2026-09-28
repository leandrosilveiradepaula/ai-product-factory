from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .supabase_server import resolve_supabase_server_config


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

    def recover_expired(self)->dict:
        return self._rpc("factory_recover_expired_agent_slots",{}) or {"released":0}
