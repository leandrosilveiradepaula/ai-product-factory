from __future__ import annotations
import json,os,urllib.error,urllib.request
from dataclasses import dataclass

@dataclass(frozen=True)
class DurableRunRecord:
 id:str;task_id:str;status:str;candidate_commit:str|None=None

class SupabaseDeliveryStore:
 """Narrow durable store for the GitHub delivery loop."""
 def __init__(self,*,url:str|None=None,service_role_key:str|None=None)->None:
  self.url=(url or os.getenv("SUPABASE_URL","")).rstrip("/");self.key=service_role_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY","")
  if not self.url or not self.key:raise RuntimeError("Supabase runtime credentials are not configured")
 def _rpc(self,name:str,payload:dict):
  req=urllib.request.Request(f"{self.url}/rest/v1/rpc/{name}",data=json.dumps(payload).encode(),method="POST",headers={"apikey":self.key,"Authorization":f"Bearer {self.key}","Content-Type":"application/json"})
  try:
   with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
  except urllib.error.HTTPError as exc:raise RuntimeError(f"control-plane RPC failed: {name} ({exc.code})") from exc
  return None if not raw else json.loads(raw)
 def update_run_status(self,run_id:str,status:str,*,candidate_commit:str|None=None)->DurableRunRecord:
  d=self._rpc("factory_update_run_delivery_status",{"p_run_id":run_id,"p_status":status,"p_candidate_commit":candidate_commit})
  return DurableRunRecord(d["run_id"],d["task_id"],d["status"],d.get("candidate_commit"))
 def record_tool_usage(self,*,run_id:str,tool_family:str,operation:str|None=None,usage_units:float|None=None,estimated_cost:float|None=None,metadata:dict|None=None):
  return self._rpc("factory_record_delivery_tool_usage",{"p_run_id":run_id,"p_tool_family":tool_family,"p_operation":operation,"p_usage_units":usage_units,"p_estimated_cost":estimated_cost,"p_metadata":metadata or {}})
