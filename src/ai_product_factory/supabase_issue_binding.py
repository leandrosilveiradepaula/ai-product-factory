from __future__ import annotations
import json,os,urllib.error,urllib.request
from .github_rest import GitHubIssue

class SupabaseIssueBindingStore:
 def __init__(self,*,url:str|None=None,service_role_key:str|None=None)->None:
  self.url=(url or os.getenv("SUPABASE_URL","")).rstrip("/");self.key=service_role_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY","")
  if not self.url or not self.key:raise RuntimeError("Supabase runtime credentials are not configured")
 def bind_issue(self,*,run_id:str,issue:GitHubIssue)->None:
  payload={"p_run_id":run_id,"p_issue_number":issue.number,"p_issue_url":issue.html_url}
  req=urllib.request.Request(f"{self.url}/rest/v1/rpc/factory_bind_github_issue",data=json.dumps(payload).encode(),method="POST",headers={"apikey":self.key,"Authorization":f"Bearer {self.key}","Content-Type":"application/json"})
  try:
   with urllib.request.urlopen(req,timeout=30):pass
  except urllib.error.HTTPError as exc:raise RuntimeError(f"control-plane RPC failed: factory_bind_github_issue ({exc.code})") from exc
