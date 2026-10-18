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
  if not isinstance(d,dict):raise RuntimeError("Direct claim returned a non-object payload")
  if run_id is not None and str(d.get("run_id"))!=run_id:raise RuntimeError("Direct claim returned a different run ID")
  if agent_key is not None and d.get("agent_key")!=agent_key:raise RuntimeError("Direct claim returned a different assigned agent")
  if isinstance(d.get("execution_generation"),bool) or not isinstance(d.get("execution_generation"),int) or d["execution_generation"]<1:raise RuntimeError("Direct claim returned an invalid execution generation")
  if not isinstance(d.get("project_id"),str) or not d["project_id"].strip():raise RuntimeError("Direct claim missing project capability")
  for field in ("run_id","task_id","project_key","repository","title","branch"):
      if not isinstance(d.get(field),str) or not d[field].strip():
          raise RuntimeError("routed claim missing required "+field)
  if not isinstance(d.get("human_gate_required",False),bool):
      raise RuntimeError("routed claim has invalid human gate")
  if d.get("wave") is not None and (isinstance(d["wave"],bool) or not isinstance(d["wave"],int) or d["wave"]<1):
      raise RuntimeError("routed claim has invalid wave")
  if bool(d.get("change_set_id")) != bool(d.get("work_unit_id")):
      raise RuntimeError("routed claim has incomplete change set binding")
  if d.get("issue_number") is not None and (isinstance(d["issue_number"],bool) or not isinstance(d["issue_number"],int) or d["issue_number"]<1):
      raise RuntimeError("routed claim has invalid issue number")
  if d.get("wave") is not None and not d.get("change_set_id"):
      raise RuntimeError("routed claim wave requires change set binding")
  for field in ("change_set_id","work_unit_id"):
      if d.get(field) is not None and (not isinstance(d[field],str) or not d[field].strip()):
          raise RuntimeError("routed claim has invalid "+field)
  if d.get("description") is not None and not isinstance(d["description"],str):
      raise RuntimeError("routed claim has invalid description")
  if d.get("change_set_id") is not None and d.get("wave") is None:
      raise RuntimeError("routed claim change set requires wave")
  if d.get("issue_number") is not None and d.get("human_gate_required") is None:
      raise RuntimeError("routed claim missing human gate decision")
  item=DirectExecutionItem(d["run_id"],d["task_id"],d["project_key"],d["repository"],d.get("issue_number"),d["title"],d.get("description") or "",d["branch"],bool(d.get("human_gate_required",False)),str(d["change_set_id"]) if d.get("change_set_id") else None,str(d["work_unit_id"]) if d.get("work_unit_id") else None,int(d["wave"]) if d.get("wave") is not None else None)
  object.__setattr__(item,"project_id",d["project_id"])
  object.__setattr__(item,"execution_generation",int(d["execution_generation"]))
  return item
