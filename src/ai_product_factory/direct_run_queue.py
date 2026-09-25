from __future__ import annotations
import json,os,urllib.error,urllib.request
from .execution_worker import DirectExecutionItem

class SupabaseDirectRunQueue:
 def __init__(self,*,url:str|None=None,service_role_key:str|None=None)->None:
  self.url=(url or os.getenv("SUPABASE_URL","")).rstrip("/");self.key=service_role_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY","")
  if not self.url or not self.key:raise RuntimeError("Supabase runtime credentials are not configured")
 def claim_next(self,worker_id:str)->DirectExecutionItem|None:
  req=urllib.request.Request(f"{self.url}/rest/v1/rpc/factory_claim_next_direct_run",data=json.dumps({"p_worker_id":worker_id}).encode(),method="POST",headers={"apikey":self.key,"Authorization":f"Bearer {self.key}","Content-Type":"application/json"})
  try:
   with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
  except urllib.error.HTTPError as exc:raise RuntimeError(f"control-plane RPC failed: factory_claim_next_direct_run ({exc.code})") from exc
  if not raw:return None
  d=json.loads(raw)
  if d is None:return None
  return DirectExecutionItem(d["run_id"],d["task_id"],d["project_key"],d["repository"],d.get("issue_number"),d["title"],d.get("description") or "",d["branch"],bool(d.get("human_gate_required",False)))
