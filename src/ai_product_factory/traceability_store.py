from __future__ import annotations

import json
import urllib.error
import urllib.request

from .supabase_server import resolve_supabase_server_config


class SupabaseTraceabilityStore:
    def __init__(self,*,url:str|None=None,secret_key:str|None=None,service_role_key:str|None=None)->None:
        cfg=resolve_supabase_server_config(url=url,secret_key=secret_key,service_role_key=service_role_key)
        self.url=cfg.url;self.headers=cfg.headers

    def _rpc(self,name:str,payload:dict):
        req=urllib.request.Request(
            f"{self.url}/rest/v1/rpc/{name}",
            data=json.dumps(payload).encode(),
            headers={**self.headers,"Content-Type":"application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane RPC failed: {name} ({exc.code})") from exc
        return None if not raw else json.loads(raw)

    def record_delivery_evidence(
        self,*,run_id:str,evidence_type:str,status:str,evidence_ref:str,metadata:dict|None=None
    )->dict:
        return self._rpc("factory_record_delivery_evidence",{
            "p_run_id":run_id,"p_evidence_type":evidence_type,"p_status":status,
            "p_evidence_ref":evidence_ref,"p_metadata":metadata or {},
        }) or {}

    def readiness(self,project_id:str)->dict:
        return self._rpc("factory_get_definition_of_done_readiness",{"p_project_id":project_id}) or {}
