from __future__ import annotations
import json,os,urllib.error,urllib.request
from dataclasses import dataclass
from urllib.parse import quote
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
 def finalize_console_human_release(self,run_id:str,*,candidate_commit:str,merge_sha:str)->dict:
  return self._rpc("factory_finalize_console_human_release",{
   "p_run_id":run_id,"p_candidate_commit":candidate_commit,"p_merge_sha":merge_sha,
  }) or {}
 def record_tool_usage(self,*,run_id:str,tool_family:str,operation:str|None=None,usage_units:float|None=None,estimated_cost:float|None=None,metadata:dict|None=None):
  return self._rpc("factory_record_delivery_tool_usage",{"p_run_id":run_id,"p_tool_family":tool_family,"p_operation":operation,"p_usage_units":usage_units,"p_estimated_cost":estimated_cost,"p_metadata":metadata or {}})
 def record_resource_limit_signal(self,*,provider:str,resource_key:str,metric_key:str,quality:str,source:str,unit:str="count",window_key:str|None=None,metadata:dict|None=None):
  if quality not in {"provider_blocked","unknown"}:raise ValueError("resource limit signal quality must be provider_blocked or unknown")
  return self._rpc("factory_record_resource_limit",{
   "p_provider":provider,"p_resource_key":resource_key,"p_metric_key":metric_key,
   "p_used_value":None,"p_limit_value":None,"p_unit":unit,"p_window_key":window_key,
   "p_window_started_at":None,"p_resets_at":None,"p_quality":quality,
   "p_source":source,"p_metadata":metadata or {},
  })
 def _patch(self,table:str,query:str,payload:dict):
  req=urllib.request.Request(f"{self.url}/rest/v1/{table}?{query}",data=json.dumps(payload).encode(),method="PATCH",headers={**self.headers,"Content-Type":"application/json","Prefer":"return=representation"})
  try:
   with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
  except urllib.error.HTTPError as exc:raise RuntimeError(f"control-plane patch failed: {table} ({exc.code})") from exc
  return None if not raw else json.loads(raw)
 def fail_preview(self,run_id:str,*,candidate_commit:str,reason:str)->DurableRunRecord:
  if not reason.strip():raise ValueError("preview failure reason is required")
  record=self.update_run_status(run_id,"failed",candidate_commit=candidate_commit)
  self._patch("factory_tasks",f"id=eq.{quote(record.task_id)}",{"status":"failed"})
  self.record_audit_event(
   run_id=run_id,event_type="preview.failed",
   payload={"candidate_commit":candidate_commit,"reason":reason[:1000]},
   actor_ref="preview-followup"
  )
  return record
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
