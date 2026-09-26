from __future__ import annotations
import json,os,urllib.error,urllib.request
from dataclasses import dataclass
from .supabase_server import resolve_supabase_server_config

@dataclass(frozen=True)
class DurableRunRecord:
 id:str;task_id:str;status:str;candidate_commit:str|None=None

class SupabaseDeliveryStore:
 """Narrow durable store for the GitHub delivery loop."""
 def __init__(self,*,url:str|None=None,service_role_key:str|None=None)->None:
  cfg=resolve_supabase_server_config(url=url,service_role_key=service_role_key);self.url=cfg.url;self.key=cfg.key;self.headers=cfg.headers
 def _rpc(self,name:str,payload:dict):
  req=urllib.request.Request(f"{self.url}/rest/v1/rpc/{name}",data=json.dumps(payload).encode(),method="POST",headers={**self.headers,"Content-Type":"application/json"})
  try:
   with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
  except urllib.error.HTTPError as exc:raise RuntimeError(f"control-plane RPC failed: {name} ({exc.code})") from exc
  return None if not raw else json.loads(raw)
 def update_run_status(self,run_id:str,status:str,*,candidate_commit:str|None=None)->DurableRunRecord:
  d=self._rpc("factory_update_run_delivery_status",{"p_run_id":run_id,"p_status":status,"p_candidate_commit":candidate_commit})
  return DurableRunRecord(d["run_id"],d["task_id"],d["status"],d.get("candidate_commit"))
 def record_tool_usage(self,*,run_id:str,tool_family:str,operation:str|None=None,usage_units:float|None=None,estimated_cost:float|None=None,metadata:dict|None=None):
  return self._rpc("factory_record_delivery_tool_usage",{"p_run_id":run_id,"p_tool_family":tool_family,"p_operation":operation,"p_usage_units":usage_units,"p_estimated_cost":estimated_cost,"p_metadata":metadata or {}})
 def _insert(self,table:str,payload:dict):
  req=urllib.request.Request(f"{self.url}/rest/v1/{table}",data=json.dumps(payload).encode(),method="POST",headers={**self.headers,"Content-Type":"application/json","Prefer":"return=representation"})
  try:
   with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
  except urllib.error.HTTPError as exc:raise RuntimeError(f"control-plane insert failed: {table} ({exc.code})") from exc
  return None if not raw else json.loads(raw)
 def record_evaluation(self,*,run_id:str,eval_type:str,status:str,score:float|None=None,baseline_ref:str|None=None,result:dict|None=None):
  return self._insert("factory_evaluations",{"run_id":run_id,"eval_type":eval_type,"status":status,"score":score,"baseline_ref":baseline_ref,"result":result or {}})
 def record_audit_event(self,*,run_id:str,event_type:str,payload:dict|None=None,actor_type:str="factory",actor_ref:str|None=None):
  return self._insert("factory_audit_events",{"run_id":run_id,"actor_type":actor_type,"actor_ref":actor_ref,"event_type":event_type,"payload":payload or {}})
