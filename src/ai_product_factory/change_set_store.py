from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .supabase_server import resolve_supabase_server_config


@dataclass(frozen=True)
class ChangeSetBinding:
    change_set_id:str
    work_unit_id:str
    base_commit:str
    source_commit:str
    integration_branch:str
    wave:int


@dataclass(frozen=True)
class ChangeSetIntegrationItem:
    change_set_id:str
    project_key:str
    repository:str
    source_commit:str
    candidate_commit:str
    integration_branch:str
    current_wave:int
    work_units:tuple[dict,...]


class SupabaseChangeSetStore:
    def __init__(self,*,url:str|None=None,secret_key:str|None=None,service_role_key:str|None=None)->None:
        cfg=resolve_supabase_server_config(url=url,secret_key=secret_key,service_role_key=service_role_key)
        self.url=cfg.url;self.headers=cfg.headers

    def _rpc(self,name:str,payload:dict):
        req=urllib.request.Request(
            f"{self.url}/rest/v1/rpc/{name}",data=json.dumps(payload).encode(),
            headers={**self.headers,"Content-Type":"application/json"},method="POST",
        )
        try:
            with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane RPC failed: {name} ({exc.code})") from exc
        return None if not raw else json.loads(raw)

    def bind_source(self,*,run_id:str,source_commit:str,integration_branch:str,work_branch:str)->ChangeSetBinding:
        data=self._rpc("factory_bind_change_set_source",{
            "p_run_id":run_id,"p_source_commit":source_commit,
            "p_integration_branch":integration_branch,"p_work_branch":work_branch,
        })
        if not isinstance(data,dict):raise RuntimeError("change-set source binding returned no data")
        return ChangeSetBinding(
            change_set_id=str(data["change_set_id"]),work_unit_id=str(data["work_unit_id"]),
            base_commit=str(data["base_commit"]),source_commit=str(data["source_commit"]),
            integration_branch=str(data["integration_branch"]),wave=int(data["wave"]),
        )

    def complete_work_unit(self,*,run_id:str,output_commit:str,changed_files:tuple[str,...])->dict:
        return self._rpc("factory_complete_change_set_work_unit",{
            "p_run_id":run_id,"p_output_commit":output_commit,"p_changed_files":list(changed_files),
        }) or {}

    def claim_integration(self,worker_id:str)->ChangeSetIntegrationItem|None:
        data=self._rpc("factory_claim_change_set_integration",{"p_worker_id":worker_id,"p_lease_seconds":600})
        if data is None:return None
        return ChangeSetIntegrationItem(
            change_set_id=str(data["change_set_id"]),project_key=str(data["project_key"]),
            repository=str(data["repository"]),source_commit=str(data["source_commit"]),
            candidate_commit=str(data["candidate_commit"]),integration_branch=str(data["integration_branch"]),
            current_wave=int(data["current_wave"]),work_units=tuple(data.get("work_units") or ()),
        )

    def complete_integration(self,*,change_set_id:str,candidate_commit:str,changed_files:tuple[str,...])->dict:
        return self._rpc("factory_complete_change_set_integration",{
            "p_change_set_id":change_set_id,"p_candidate_commit":candidate_commit,
            "p_changed_files":list(changed_files),
        }) or {}

    def prepare_release(self,*,change_set_id:str,issue_number:int,issue_url:str,pr_number:int,candidate_commit:str,branch:str)->dict:
        return self._rpc("factory_prepare_change_set_release",{
            "p_change_set_id":change_set_id,"p_issue_number":issue_number,"p_issue_url":issue_url,
            "p_pr_number":pr_number,"p_candidate_commit":candidate_commit,"p_branch":branch,
        }) or {}
