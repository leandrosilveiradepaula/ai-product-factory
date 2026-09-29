from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .supabase_server import resolve_supabase_server_config


@dataclass(frozen=True)
class PortfolioCandidate:
    project_id:str
    project_key:str
    priority:str
    deadline:str|None
    customer_impact:int
    max_active_workers:int
    active_runs:int
    open_incident_severity:str|None
    soft_preemption_active:bool


class SupabasePortfolioScheduler:
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

    def candidates(self,limit:int=20)->tuple[PortfolioCandidate,...]:
        data=self._rpc("factory_portfolio_candidates",{"p_limit":limit}) or []
        if not isinstance(data,list):raise RuntimeError("portfolio candidates must be an array")
        return tuple(PortfolioCandidate(
            project_id=str(row["project_id"]),project_key=str(row["project_key"]),
            priority=str(row.get("priority") or "P2"),deadline=str(row["deadline"]) if row.get("deadline") else None,
            customer_impact=int(row.get("customer_impact") or 0),
            max_active_workers=int(row.get("max_active_workers") or 1),
            active_runs=int(row.get("active_runs") or 0),
            open_incident_severity=str(row["open_incident_severity"]) if row.get("open_incident_severity") else None,
            soft_preemption_active=bool(row.get("soft_preemption_active")),
        ) for row in data)

    def select(self,limit:int=20)->PortfolioCandidate|None:
        candidates=self.candidates(limit)
        selected=candidates[0] if candidates else None
        reason={
            "policy":"incident-severity_then_priority_then_deadline_then_customer-impact",
            "soft_preemption":bool(selected.soft_preemption_active) if selected else False,
            "active_workers_cancelled":False,
            "production_gates_bypassed":False,
        }
        self._rpc("factory_record_portfolio_decision",{
            "p_selected_project_key":selected.project_key if selected else "",
            "p_candidates":[c.__dict__ for c in candidates],
            "p_reason":reason,
        })
        return selected


class SupabaseIncidentController:
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

    def open(self,*,project_key:str,severity:str,title:str,summary:str,metadata:dict|None=None)->dict:
        return self._rpc("factory_open_incident",{
            "p_project_key":project_key,"p_severity":severity,"p_title":title,
            "p_summary":summary,"p_metadata":metadata or {},
        }) or {}

    def transition(self,*,incident_id:str,status:str,evidence:dict|None=None)->dict:
        return self._rpc("factory_transition_incident",{
            "p_incident_id":incident_id,"p_to_status":status,"p_evidence":evidence or {},
        }) or {}
