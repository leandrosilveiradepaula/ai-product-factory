from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .runtime_worker import RuntimeQueue, StageEvidence, WorkItem


class SupabaseRuntimeQueue(RuntimeQueue):
    """Server-side REST/RPC adapter for the durable runtime queue."""
    def __init__(self, *, url: str | None = None, service_role_key: str | None = None) -> None:
        self.url=(url or os.getenv("SUPABASE_URL","")).rstrip("/")
        self.key=service_role_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY","")
        if not self.url or not self.key:
            raise RuntimeError("Supabase runtime credentials are not configured")

    def _rpc(self, name: str, payload: dict):
        req=urllib.request.Request(f"{self.url}/rest/v1/rpc/{name}",data=json.dumps(payload).encode(),method="POST",headers={"apikey":self.key,"Authorization":f"Bearer {self.key}","Content-Type":"application/json"})
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

    def complete(self,item:WorkItem)->None:
        self._rpc("factory_finish_run",{"p_run_id":item.run_id,"p_status":"completed","p_error":None})

    def fail(self,item:WorkItem,error:str)->None:
        self._rpc("factory_finish_run",{"p_run_id":item.run_id,"p_status":"failed","p_error":error[:2000]})
