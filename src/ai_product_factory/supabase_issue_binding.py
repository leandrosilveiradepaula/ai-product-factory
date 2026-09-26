from __future__ import annotations
import json,os,urllib.error,urllib.request
from .github_rest import GitHubIssue
from .supabase_server import resolve_supabase_server_config

class SupabaseIssueBindingStore:
 def __init__(self,*,url:str|None=None,service_role_key:str|None=None)->None:
  cfg=resolve_supabase_server_config(url=url,service_role_key=service_role_key);self.url=cfg.url;self.key=cfg.key;self.headers=cfg.headers
 def bind_issue(self,*,run_id:str,issue:GitHubIssue)->None:
  payload={"p_run_id":run_id,"p_issue_number":issue.number,"p_issue_url":issue.html_url}
  req=urllib.request.Request(f"{self.url}/rest/v1/rpc/factory_bind_github_issue",data=json.dumps(payload).encode(),method="POST",headers={**self.headers,"Content-Type":"application/json"})
  try:
   with urllib.request.urlopen(req,timeout=30):pass
  except urllib.error.HTTPError as exc:raise RuntimeError(f"control-plane RPC failed: factory_bind_github_issue ({exc.code})") from exc
