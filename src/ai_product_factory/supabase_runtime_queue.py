from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .runtime_worker import RuntimeQueue, StageEvidence, WorkItem
from .project_brain import build_project_brain_graph
from .supabase_server import resolve_supabase_server_config


class SupabaseRuntimeQueue(RuntimeQueue):
    """Server-side REST/RPC adapter for the durable runtime queue."""
    def __init__(self, *, url: str | None = None, service_role_key: str | None = None) -> None:
        cfg=resolve_supabase_server_config(url=url,service_role_key=service_role_key)
        self.url=cfg.url
        self.key=cfg.key
        self.headers=cfg.headers

    def _rpc(self, name: str, payload: dict):
        req=urllib.request.Request(f"{self.url}/rest/v1/rpc/{name}",data=json.dumps(payload).encode(),method="POST",headers={**self.headers,"Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane RPC failed: {name} ({exc.code})") from exc
        return None if not raw else json.loads(raw)

    def recover_expired(self,max_attempts:int=3)->dict:
        data=self._rpc("factory_recover_expired_runs",{"p_max_attempts":max_attempts})
        return data or {"requeued":0,"failed":0}

    def claim_next(self, worker_id: str) -> WorkItem | None:
        data=self._rpc("factory_claim_next_run",{"p_worker_id":worker_id})
        if data is None: return None
        return WorkItem(run_id=data["run_id"],task_id=data["task_id"],project_id=data["project_id"],project_key=data["project_key"],stages=tuple(data.get("stages",[])),context=data.get("context",{}))

    def record_stage(self,item:WorkItem,evidence:StageEvidence)->None:
        self._rpc("factory_record_runtime_stage",{"p_run_id":item.run_id,"p_stage":evidence.stage,"p_status":evidence.status,"p_output":evidence.output})
        self._rpc("factory_persist_product_stage",{"p_run_id":item.run_id,"p_stage":evidence.stage,"p_output":evidence.output})
        if evidence.stage=="planning":
            brain=build_project_brain_graph(project_key=item.project_key,engineering_plan=evidence.output,context=item.context)
            self._rpc("factory_record_project_brain_snapshot",{
                "p_project_id":item.project_id,
                "p_source_ref":f"run:{item.run_id}:planning",
                "p_summary":brain.summary,
                "p_nodes":list(brain.nodes),
                "p_edges":list(brain.edges),
            })
            team_plan=evidence.output.get("_team_plan")
            if isinstance(team_plan,dict):
                recorded=self._rpc("factory_record_execution_team_plan",{"p_run_id":item.run_id,"p_plan":team_plan}) or {}
                team_plan_id=recorded.get("id")
                if team_plan_id and recorded.get("status")=="ready":
                    self._rpc("factory_materialize_change_set",{"p_team_plan_id":team_plan_id})

    def complete(self,item:WorkItem)->None:
        self._rpc("factory_finish_run",{"p_run_id":item.run_id,"p_status":"completed","p_error":None})

    def fail(self,item:WorkItem,error:str)->None:
        self._rpc("factory_finish_run",{"p_run_id":item.run_id,"p_status":"failed","p_error":error[:2000]})
