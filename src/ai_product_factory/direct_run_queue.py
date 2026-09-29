from __future__ import annotations
import json,os,urllib.error,urllib.request
from .execution_worker import DirectExecutionItem
from .supabase_server import resolve_supabase_server_config

class SupabaseDirectRunQueue:
 def __init__(self,*,url:str|None=None,service_role_key:str|None=None)->None:
  cfg=resolve_supabase_server_config(url=url,service_role_key=service_role_key);self.url=cfg.url;self.key=cfg.key;self.headers=cfg.headers
 def claim_next(self,worker_id:str,agent_key:str|None=None,run_id:str|None=None)->DirectExecutionItem|None:
  req=urllib.request.Request(f"{self.url}/rest/v1/rpc/factory_claim_next_agent_direct_run",data=json.dumps({"p_worker_id":worker_id,"p_agent_key":agent_key,"p_run_id":run_id}).encode(),method="POST",headers={**self.headers,"Content-Type":"application/json"})
  try:
   with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
  except urllib.error.HTTPError as exc:raise RuntimeError(f"control-plane RPC failed: factory_claim_next_agent_direct_run ({exc.code})") from exc
  if not raw:return None
  d=json.loads(raw)
  if d is None:return None
  return DirectExecutionItem(d["run_id"],d["task_id"],d["project_key"],d["repository"],d.get("issue_number"),d["title"],d.get("description") or "",d["branch"],bool(d.get("human_gate_required",False)),str(d["change_set_id"]) if d.get("change_set_id") else None,str(d["work_unit_id"]) if d.get("work_unit_id") else None,int(d["wave"]) if d.get("wave") is not None else None)
