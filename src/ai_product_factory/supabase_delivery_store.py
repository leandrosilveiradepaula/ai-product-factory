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
 def reconcile_change_set_ci_candidate(self,*,change_set_id:str,run_id:str,pr_number:int,previous_commit:str,new_commit:str,verified_evidence:dict)->dict:
  """Atomic, audited SHA update; caller must first verify GitHub identity/ancestry."""
  if not change_set_id or not run_id or pr_number<1 or not isinstance(verified_evidence,dict):
   raise ValueError("missing reconciliation identity")
  result=self._rpc("factory_reconcile_change_set_ci_candidate",{
   "p_change_set_id":change_set_id,"p_run_id":run_id,
   "p_pr_number":pr_number,"p_previous_commit":previous_commit,
   "p_new_commit":new_commit,"p_verified_evidence":verified_evidence})
  if not isinstance(result,dict) or result.get("candidate_commit")!=new_commit or result.get("previous_commit")!=previous_commit or result.get("run_id")!=run_id:
   raise RuntimeError("inconsistent atomic candidate reconciliation receipt")
  return result
 def block_early_merged_ci_candidate(self,*,run_id:str,repository:str,pr_number:int,candidate_commit:str,merge_sha:str)->dict:
  """Atomic fail-closed reconciliation; only after exact GitHub merge observation.

  The RPC preserves CI evidence, candidate SHA, project stage and human gate.
  In particular it never calls a release observer or grants merge authority.
  """
  if not run_id.strip() or not repository.strip() or pr_number<1 or not candidate_commit.strip() or not merge_sha.strip():
   raise ValueError("missing exact early-merge identity")
  result=self._rpc("factory_block_early_merged_ci_candidate",{
   "p_run_id":run_id,
   "p_repository":repository,
   "p_pr_number":pr_number,
   "p_candidate_commit":candidate_commit,
   "p_merge_sha":merge_sha,
  })
  if not isinstance(result,dict) or result.get("status")!="blocked" or result.get("run_id")!=run_id or result.get("merge_sha")!=merge_sha:
   raise RuntimeError("early-merge reconciliation returned inconsistent evidence")
  return result

 def find_verified_nonproduction_browser_snapshot(
  self,*,project_id:str,repository:str,merge_sha:str,
 )->dict|None:
  """Read authoritative cross-repo browser evidence at exact merged SHA.

  Missing evidence means wait, never treat a deployment status/feedback check
  as equivalent to successful Playwright on the integrated branch.
  """
  import re
  from urllib.parse import urlparse
  if not project_id or not re.fullmatch(r"[0-9a-f]{40}",merge_sha) or "/" not in repository:
   raise ValueError("invalid postmerge browser snapshot identity")
  path=(
   f"/rest/v1/factory_project_state_snapshots?select=id,evidence,gaps,constraints,source_status"
   f"&project_id=eq.{quote(project_id)}&order=created_at.desc&limit=50"
  )
  req=urllib.request.Request(f"{self.url}{path}",headers=self.headers,method="GET")
  try:
   with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
  except urllib.error.HTTPError as exc:
   raise RuntimeError(f"postmerge browser receipt read failed ({exc.code})") from exc
  rows=json.loads(raw) if raw else []
  if not isinstance(rows,list):
   raise RuntimeError("invalid cross-repo browser receipt inventory")
  for row in rows:
   if not isinstance(row,dict):raise RuntimeError("malformed cross-repo browser receipt")
   evidence=row.get("evidence") or {}
   if not isinstance(evidence,dict):
    raise RuntimeError("malformed cross-repo browser evidence payload")
   if evidence.get("candidate_commit")!=merge_sha or evidence.get("target_repository")!=repository:
    continue
   preview=evidence.get("preview") or {}
   status=row.get("source_status") or {}
   constraints=row.get("constraints") or {}
   url=str(preview.get("url") or "")
   parsed=urlparse(url)
   verifier_id=preview.get("browser_verifier_run_id")
   if (not isinstance(preview,dict) or not isinstance(status,dict)
       or not isinstance(constraints,dict)
       or preview.get("provider")!="vercel"
       or preview.get("status")!="browser_verified"
       or status.get("browser_visual_validation")!="success"
       or status.get("vercel_preview")!="resolved"
       or constraints.get("production_merge_authorized") is not False
       or row.get("gaps") != []
       or parsed.scheme!="https" or not str(parsed.hostname or "").endswith(".vercel.app")
       or parsed.username is not None or parsed.password is not None
       or not isinstance(verifier_id,int) or isinstance(verifier_id,bool) or verifier_id<=0
       or not isinstance(row.get("id"),str) or len(row["id"])!=36):
    raise RuntimeError("cross-repo browser receipt is not a verified exact merge")
   return {"snapshot_id":row["id"],"preview_url":url,"verifier_run_id":verifier_id}
  return None

 def observe_nonproduction_preview_merge(
  self,*,run_id:str,pr_number:int,candidate_commit:str,merge_sha:str,
  base_ref:str,verified_evidence:dict,
 )->dict:
  """Atomic preview-only merge observation. Does NOT authorize production."""
  if not run_id or pr_number<=0 or not base_ref.startswith("preview/"):
   raise ValueError("preview integration requires exact run, PR and preview base")
  if not isinstance(verified_evidence,dict) or verified_evidence.get("production_released") is not False:
   raise ValueError("preview integration must explicitly reject production release")
  data=self._rpc("factory_observe_nonproduction_preview_merge",{
   "p_run_id":run_id,"p_pr_number":pr_number,
   "p_candidate_commit":candidate_commit,"p_merge_sha":merge_sha,
   "p_base_ref":base_ref,"p_verified_github":verified_evidence,
  })
  if (not isinstance(data,dict) or data.get("run_id")!=run_id
      or data.get("status")!="integrated" or data.get("merge_sha")!=merge_sha
      or data.get("release_completed") is not False):
   raise RuntimeError("nonproduction integration RPC returned inconsistent evidence")
  return data

 def reconcile_closed_preview_candidate(self,run_id:str,*,candidate_commit:str,pr_number:int,github_state:str,github_merged:bool)->dict:
  if github_state!="closed" or github_merged is not False or pr_number<=0:
   raise ValueError("only a verified closed, unmerged PR may be superseded")
  data=self._rpc("factory_reconcile_closed_preview_candidate",{
   "p_run_id":run_id,"p_candidate_commit":candidate_commit,"p_pr_number":pr_number,
   "p_github_state":github_state,"p_github_merged":github_merged,
  })
  if not isinstance(data,dict) or data.get("run_id")!=run_id or data.get("status")!="cancelled" or data.get("change_set_status")!="superseded":
   raise RuntimeError("closed Preview reconciliation result is inconsistent")
  return data
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
 def record_product_readiness(self,*,run_id:str,assessment):
  result=assessment.as_result()
  status="passed" if assessment.ready else "failed"
  saved=self.record_evaluation(
   run_id=run_id,eval_type="product_readiness",status=status,
   baseline_ref=assessment.assessed_commit,result=result,
  )
  self.record_audit_event(
   run_id=run_id,event_type="product_readiness.assessed",
   payload={"assessed_commit":assessment.assessed_commit,"assessment_ref":assessment.assessment_ref,"ready":assessment.ready,"status":assessment.status,"blockers":list(assessment.blockers)},
   actor_ref="product-readiness",
  )
  return saved
 def record_audit_event(self,*,run_id:str,event_type:str,payload:dict|None=None,actor_type:str="factory",actor_ref:str|None=None):
  return self._insert("factory_audit_events",{"run_id":run_id,"actor_type":actor_type,"actor_ref":actor_ref,"event_type":event_type,"payload":payload or {}})
