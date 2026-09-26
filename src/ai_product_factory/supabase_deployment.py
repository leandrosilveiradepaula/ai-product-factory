from __future__ import annotations
import json,os,urllib.error,urllib.request
from .deployment import DeploymentRequest,DeploymentResult

class SupabaseDeploymentEvidenceStore:
 def __init__(self,*,url:str|None=None,service_role_key:str|None=None)->None:
  self.url=(url or os.getenv("SUPABASE_URL","")).rstrip("/");self.key=service_role_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY","")
  if not self.url or not self.key:raise RuntimeError("Supabase runtime credentials are not configured")
 def record(self,*,run_id:str,result:DeploymentResult,metadata:dict|None=None):
  payload={"run_id":run_id,"environment":result.environment.value,"status":result.status,"deployment_ref":result.deployment_ref,"metadata":{"provider":result.provider,"preview_url":result.preview_url,**(metadata or {})}}
  req=urllib.request.Request(f"{self.url}/rest/v1/factory_deployments",data=json.dumps(payload).encode(),method="POST",headers={"apikey":self.key,"Authorization":f"Bearer {self.key}","Content-Type":"application/json","Prefer":"return=representation"})
  try:
   with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
  except urllib.error.HTTPError as exc:raise RuntimeError(f"deployment evidence insert failed ({exc.code})") from exc
  return None if not raw else json.loads(raw)

class DurablePreviewAdapter:
 name="durable-preview"
 def __init__(self,provider,store:SupabaseDeploymentEvidenceStore,*,run_id:str)->None:self.provider=provider;self.store=store;self.run_id=run_id
 def deploy(self,request:DeploymentRequest)->DeploymentResult:
  if request.environment.value!="preview":raise PermissionError("durable preview adapter refuses non-preview deployment")
  result=self.provider.deploy(request)
  self.store.record(run_id=self.run_id,result=result,metadata={"candidate_commit":request.candidate_commit})
  return result
