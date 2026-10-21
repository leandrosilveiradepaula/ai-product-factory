from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import quote

from .supabase_server import resolve_supabase_server_config
from .post_release_readiness import summarize_released_product


_STAGE_RANK={
    "discovery":0,
    "specification":1,
    "planning":2,
    "implementation":3,
    "review":4,
    "validation":5,
    "release":6,
    "operations":7,
}


class SupabaseProjectReleaseReconciler:
    def __init__(self,*,url:str|None=None,secret_key:str|None=None,service_role_key:str|None=None)->None:
        cfg=resolve_supabase_server_config(url=url,secret_key=secret_key,service_role_key=service_role_key)
        self.url=cfg.url
        self.headers=cfg.headers

    def _request(self,method:str,path:str,payload:dict|None=None):
        body=None if payload is None else json.dumps(payload).encode()
        headers=self.headers if payload is None else {**self.headers,"Content-Type":"application/json","Prefer":"return=representation"}
        req=urllib.request.Request(f"{self.url}/rest/v1/{path}",data=body,headers=headers,method=method)
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane request failed: {method} {path} ({exc.code})") from exc
        return None if not raw else json.loads(raw)

    def reconcile(self,*,project_id:str,run_id:str,merge_sha:str)->dict:
        # The versioned RPC is the only mutation path. Until its separately
        # approved migration exists, release reconciliation fails BEFORE writes.
        reports=self._request(
            "GET","factory_release_reports?select=project_id,run_id,status,candidate_commit,report"
            f"&project_id=eq.{quote(project_id,safe='')}"
            f"&run_id=eq.{quote(run_id,safe='')}&limit=2")
        followup=summarize_released_product(project_id=project_id,run_id=run_id,
            merge_sha=merge_sha,report_rows=reports)
        receipt=self._request("POST","rpc/factory_reconcile_project_release_atomic",{
            "p_project_id":project_id,"p_run_id":run_id,
            "p_merge_sha":merge_sha,"p_followup":followup})
        if (not isinstance(receipt,dict) or type(receipt.get("idempotent")) is not bool
            or receipt.get("project_id")!=project_id
            or receipt.get("merge_sha")!=merge_sha
            or receipt.get("lifecycle_stage")!="operations"):
            raise RuntimeError("invalid atomic project reconciliation receipt")
        return receipt
