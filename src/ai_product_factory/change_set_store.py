from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote

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

    def _get(self,path:str):
        req=urllib.request.Request(f"{self.url}/rest/v1/{path}",method="GET",headers=self.headers)
        try:
            with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane read failed: {path} ({exc.code})") from exc
        return [] if not raw else json.loads(raw)

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

    def _patch(self,path:str,payload:dict)->list[dict]:
        req=urllib.request.Request(
            f"{self.url}/rest/v1/{path}",data=json.dumps(payload).encode(),
            headers={**self.headers,"Content-Type":"application/json","Prefer":"return=representation"},
            method="PATCH",
        )
        try:
            with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane update failed: {path} ({exc.code})") from exc
        return [] if not raw else json.loads(raw)

    def recover_expired(self,max_attempts:int=3)->dict:
        return self._rpc("factory_recover_change_sets",{"p_max_attempts":max_attempts}) or {}

    def frozen_source_commit(self,change_set_id:str)->str|None:
        rows=self._get(
            "factory_change_sets?select=source_commit&id=eq."+change_set_id+"&limit=1"
        )
        if not rows:
            raise RuntimeError("change set not found")
        value=rows[0].get("source_commit")
        return str(value) if value else None

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

    def context_source(self,run_id:str)->dict:
        data=self._rpc("factory_work_unit_context_source",{"p_run_id":run_id})
        if not isinstance(data,dict):raise RuntimeError("work-unit context source returned no data")
        project_key=str(data.get("project_key") or "").strip()
        decisions=[]
        if project_key:
            rows=self._get(
                "factory_projects?select=manifest&project_key=eq."+quote(project_key)+"&limit=1"
            )
            if rows and isinstance(rows[0].get("manifest"),dict):
                value=rows[0]["manifest"].get("human_decisions")
                if isinstance(value,list):
                    decisions=value

        assignment=dict(data.get("assignment") if isinstance(data.get("assignment"),dict) else {})
        work_unit_id=str(data.get("work_unit_id") or "").strip()
        if work_unit_id:
            units=self._get(
                "factory_change_set_work_units?select=task_id&id=eq."+quote(work_unit_id)+"&limit=1"
            )
            task_id=str(units[0].get("task_id") or "").strip() if units else ""
            if task_id:
                tasks=self._get(
                    "factory_tasks?select=scope_keys,required_capabilities,agent_role&id=eq."+quote(task_id)+"&limit=1"
                )
                if tasks:
                    task=tasks[0]
                    scopes=task.get("scope_keys")
                    capabilities=task.get("required_capabilities")
                    if isinstance(scopes,list) and scopes:
                        assignment["scope_keys"]=scopes
                    if isinstance(capabilities,list) and capabilities:
                        assignment["required_capabilities"]=capabilities
                    role=str(task.get("agent_role") or "").strip()
                    if role:
                        assignment["agent_role"]=role

        enriched=dict(data)
        enriched["assignment"]=assignment
        enriched["human_decisions"]=decisions
        return enriched

    def record_context(self,*,run_id:str,packet_hash:str,packet:dict)->dict:
        return self._rpc("factory_record_work_unit_context",{
            "p_run_id":run_id,"p_packet_hash":packet_hash,"p_packet":packet,
        }) or {}

    def set_repair_status(self,*,run_id:str,status:str)->dict:
        return self._rpc("factory_set_repair_status",{"p_run_id":run_id,"p_status":status}) or {}

    def block_work_unit(self,*,run_id:str,reason:str,blocker_type:str="implementation_blocked")->dict:
        if not run_id.strip() or not reason.strip():
            raise ValueError("run id and blocker reason are required")
        return self._rpc("factory_block_change_set_work_unit",{
            "p_run_id":run_id,
            "p_reason":reason[:1000],
            "p_blocker_type":blocker_type,
        }) or {}

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

    def mark_repair_wave_integrated(self,*,change_set_id:str,wave:int,candidate_commit:str)->dict:
        return self._rpc("factory_mark_repair_wave_integrated",{
            "p_change_set_id":change_set_id,"p_wave":wave,"p_candidate_commit":candidate_commit,
        }) or {}

    def prepare_release(self,*,change_set_id:str,issue_number:int,issue_url:str,pr_number:int,candidate_commit:str,branch:str)->dict:
        return self._rpc("factory_prepare_change_set_release",{
            "p_change_set_id":change_set_id,"p_issue_number":issue_number,"p_issue_url":issue_url,
            "p_pr_number":pr_number,"p_candidate_commit":candidate_commit,"p_branch":branch,
        }) or {}

    def finalize_released_run(self,run_id:str,merge_sha:str)->dict:
        if not run_id.strip() or not merge_sha.strip():
            raise ValueError("run id and merge sha are required")
        rows=self._get(
            "factory_change_sets?select=id,status,metadata,release_run_id"
            "&release_run_id=eq."+quote(run_id)+"&limit=1"
        )
        if not rows:
            return {"matched":False,"status":"not_change_set"}
        row=rows[0]
        change_set_id=str(row["id"])
        status=str(row.get("status") or "")
        if status=="completed":
            return {"matched":True,"change_set_id":change_set_id,"status":"completed","idempotent":True}
        if status!="ci_pending":
            raise RuntimeError(f"released Change Set has incompatible status: {status or 'missing'}")
        metadata=dict(row.get("metadata") or {})
        metadata["release"]={"run_id":run_id,"merge_sha":merge_sha,"observed":True}
        updated=self._patch(
            "factory_change_sets?id=eq."+quote(change_set_id)+"&status=eq.ci_pending",
            {"status":"completed","metadata":metadata},
        )
        if updated:
            return {"matched":True,"change_set_id":change_set_id,"status":"completed","idempotent":False}
        current=self._get(
            "factory_change_sets?select=id,status&release_run_id=eq."+quote(run_id)+"&limit=1"
        )
        if current and str(current[0].get("status") or "")=="completed":
            return {"matched":True,"change_set_id":change_set_id,"status":"completed","idempotent":True}
        raise RuntimeError("Change Set release finalization lost its conditional update")
