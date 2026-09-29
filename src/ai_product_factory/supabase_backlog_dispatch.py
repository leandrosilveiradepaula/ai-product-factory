from __future__ import annotations

import json,os,urllib.error,urllib.request
from .backlog_dispatcher import BacklogDispatcher,DispatchDecision,PlannedTask
from .supabase_server import resolve_supabase_server_config
from .portfolio_scheduler import SupabasePortfolioScheduler

class SupabaseBacklogDispatch:
 def __init__(self,*,url:str|None=None,service_role_key:str|None=None,dispatcher:BacklogDispatcher|None=None,portfolio:SupabasePortfolioScheduler|None=None)->None:
  cfg=resolve_supabase_server_config(url=url,service_role_key=service_role_key);self.url=cfg.url;self.key=cfg.key;self.headers=cfg.headers;self.dispatcher=dispatcher or BacklogDispatcher();self.portfolio=portfolio or SupabasePortfolioScheduler(url=cfg.url,service_role_key=service_role_key)
 def _get(self,path:str):
  req=urllib.request.Request(f"{self.url}/rest/v1/{path}",method="GET",headers=self.headers)
  try:
   with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
  except urllib.error.HTTPError as exc:raise RuntimeError(f"control-plane read failed: {path} ({exc.code})") from exc
  return [] if not raw else json.loads(raw)
 def _rpc(self,name:str,payload:dict):
  req=urllib.request.Request(f"{self.url}/rest/v1/rpc/{name}",data=json.dumps(payload).encode(),method="POST",headers={**self.headers,"Content-Type":"application/json"})
  try:
   with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
  except urllib.error.HTTPError as exc:raise RuntimeError(f"control-plane RPC failed: {name} ({exc.code})") from exc
  return None if not raw else json.loads(raw)
 def dispatch_next(self,project_key:str)->DispatchDecision|None:
  data=self._rpc("factory_dispatch_next_planned_task",{"p_project_key":project_key})
  if data is None:return None
  task=PlannedTask(data["task_id"],data["project_key"],data["title"],data.get("description") or "",data.get("complexity") or "medium",data.get("risk") or {},data.get("metadata") or {})
  decision=self.dispatcher.decide(task);e=decision.execution
  self._rpc("factory_record_dispatch_decision_v2",{
   "p_run_id":data["run_id"],"p_route":e.route.value,
   "p_codex_level":e.codex.level,"p_codex_used":e.codex.should_use,
   "p_codex_reasons":list(e.codex.reasons),"p_routing_policy_version":e.codex.policy_version,
   "p_human_gate":e.human_gate_required,"p_gate_reasons":list(e.gate_reasons)
  })
  return decision

 def dispatch_next_any(self)->DispatchDecision|None:
  candidates=self.portfolio.candidates(20)
  for candidate in candidates:
   decision=self.dispatch_next(candidate.project_key)
   if decision is not None:
    self.portfolio.record(candidate,candidates,outcome="dispatched")
    return decision
  self.portfolio.record(None,candidates,outcome="empty_or_raced")
  return None
