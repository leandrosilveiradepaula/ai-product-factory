"""Durable, isolated project-control wake observation; never executes paid work."""
import json,re,urllib.request,urllib.error
from .supabase_server import resolve_supabase_server_config

class ControlWakeOutbox:
 def __init__(self,*,url=None,service_role_key=None):
  cfg=resolve_supabase_server_config(url=url,service_role_key=service_role_key)
  self.url=cfg.url.rstrip("/");self.headers=cfg.headers
 def rpc(self,name,payload):
  req=urllib.request.Request(self.url+"/rest/v1/rpc/"+name,
    data=json.dumps(payload).encode(),method="POST",
    headers={**self.headers,"Content-Type":"application/json"})
  try:
   with urllib.request.urlopen(req,timeout=30) as r:raw=r.read().decode()
  except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError) as exc:
   raise RuntimeError("control wake evidence RPC unavailable") from exc
  result=json.loads(raw) if raw else None
  if result is not None and not isinstance(result,dict):
   raise RuntimeError("invalid wake RPC response")
  return result
 def observe_one(self,*,owner):
  if not re.fullmatch(r"[A-Za-z0-9_.:-]{3,128}",owner):
   raise ValueError("invalid control wake owner")
  claim=self.rpc("factory_claim_project_control_wake",{"p_owner":owner,"p_command_id":None})
  if claim is None:return {"status":"empty","observed":False}
  if claim.get("status") in ("suppressed","exhausted"):
   return {"status":claim["status"],"observed":False}
  if claim.get("status")!="claimed" or not isinstance(claim.get("id"),str):
   raise RuntimeError("invalid wake claim response")
  ack=self.rpc("factory_ack_project_control_wake",
    {"p_id":claim["id"],"p_owner":owner,"p_result":"observed"})
  if not isinstance(ack,dict) or ack.get("id")!=claim["id"] or ack.get("status") not in ("observed","suppressed"):
   raise RuntimeError("control wake observation did not commit")
  return {"status":ack["status"],"observed":ack["status"]=="observed",
    "attempt":claim.get("attempt")}
