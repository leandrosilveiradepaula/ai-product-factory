from __future__ import annotations

import json,os,urllib.error,urllib.request
from .backlog_dispatcher import BacklogDispatcher,DispatchDecision,PlannedTask
from .supabase_server import resolve_supabase_server_config

class SupabaseBacklogDispatch:
 def __init__(self,*,url:str|None=None,service_role_key:str|None=None,dispatcher:BacklogDispatcher|None=None)->None:
  cfg=resolve_supabase_server_config(url=url,service_role_key=service_role_key);self.url=cfg.url;self.key=cfg.key;self.headers=cfg.headers;self.dispatcher=dispatcher or BacklogDispatcher()
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
  self._rpc("factory_record_dispatch_decision",{"p_run_id":data["run_id"],"p_route":e.route.value,"p_codex_level":e.codex.level,"p_codex_used":e.codex.should_use,"p_human_gate":e.human_gate_required,"p_gate_reasons":list(e.gate_reasons)})
  return decision
