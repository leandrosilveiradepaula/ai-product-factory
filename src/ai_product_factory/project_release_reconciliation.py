from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from urllib.parse import quote

from .supabase_server import resolve_supabase_server_config
from .post_release_readiness import summarize_released_product

_UUID=re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
_SHA=re.compile(r"^[0-9a-f]{40}$")
_PAGE=16
_MAX_PAGES=32


class SupabaseProjectReleaseReconciler:
    """An observed human release is reconciled exactly once, atomically.

    The versioned RPC must exist; never fall back to PATCH+POST+POST. Production
    merges stay human-only and this adapter neither dispatches nor merges.
    """

    def __init__(self,*,url:str|None=None,secret_key:str|None=None,service_role_key:str|None=None)->None:
        cfg=resolve_supabase_server_config(url=url,secret_key=secret_key,service_role_key=service_role_key)
        self.url=cfg.url
        self.headers=cfg.headers

    def _request(self,method:str,path:str,payload:dict|None=None):
        if method not in {"GET","POST"} or (method=="POST" and not path.startswith("rpc/")):
            raise ValueError("release reconciler only allows read-only GET or RPC")
        body=None if payload is None else json.dumps(payload).encode()
        headers=self.headers if payload is None else {**self.headers,"Content-Type":"application/json"}
        req=urllib.request.Request(f"{self.url}/rest/v1/{path}",data=body,headers=headers,method=method)
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                raw=response.read().decode()
        except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError) as exc:
            raise RuntimeError("release reconciliation Control Plane unavailable") from exc
        return None if not raw else json.loads(raw)

    def reconcile(self,*,project_id:str,run_id:str,merge_sha:str)->dict:
        if (not isinstance(project_id,str) or not _UUID.fullmatch(project_id)
            or not isinstance(run_id,str) or not _UUID.fullmatch(run_id)
            or not isinstance(merge_sha,str) or not _SHA.fullmatch(merge_sha)):
            raise ValueError("invalid exact human-release identity")
        rows=self._request(
            "GET","factory_release_reports?"
            "select=project_id,run_id,status,candidate_commit,report"
            f"&project_id=eq.{quote(project_id,safe='')}"
            f"&run_id=eq.{quote(run_id,safe='')}&limit=2"
        )
        if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict):
            raise RuntimeError("exact released report unavailable")
        summary=summarize_released_product(
            project_id=project_id,run_id=run_id,
            merge_sha=merge_sha,report_rows=rows,
        )
        if summary["report_verified"] is not True or summary["ready"] is not False:
            raise RuntimeError("release evidence is not verified for reconciliation")
        receipt=self._request("POST","rpc/factory_reconcile_observed_release_v1",{
            "p_project_id":project_id,"p_run_id":run_id,"p_merge_sha":merge_sha,
            "p_release_report":rows[0]["report"],"p_followup":summary,
        })
        if (not isinstance(receipt,dict)
            or receipt.get("project_id")!=project_id
            or receipt.get("run_id")!=run_id
            or receipt.get("merge_sha")!=merge_sha
            or receipt.get("lifecycle_stage")!="operations"
            or receipt.get("product_ready") is not False
            or type(receipt.get("idempotent")) is not bool
            or type(receipt.get("snapshot_written")) is not bool
            or type(receipt.get("audit_written")) is not bool
            or type(receipt.get("pending_domains")) is not int
            or receipt["pending_domains"]!=len(summary["pending_domains"])):
            raise RuntimeError("inconsistent atomic release reconciliation receipt")
        return receipt

    def settle_pending(self,*,max_items:int=32)->dict:
        if type(max_items) is not int or not 1<=max_items<=128:
            raise ValueError("invalid bounded release settlement")
        scanned=0
        reconciled=0
        idempotent=0
        failed=[]
        cursor=0
        exhausted=False
        for page in range(_MAX_PAGES):
            rows=self._request("POST","rpc/factory_pending_release_reconciliations_v1",{
                "p_after_event_id":cursor,"p_limit":_PAGE,
            })
            if (not isinstance(rows,list) or len(rows)>_PAGE
                or any(not isinstance(row,dict) for row in rows)):
                raise RuntimeError("invalid pending human release scan")
            if not rows:
                exhausted=True
                break
            for row in rows:
                event_id=row.get("event_id")
                if type(event_id) is not int or event_id<=cursor:
                    raise RuntimeError("invalid release keyset cursor")
                cursor=event_id
                scanned+=1
                # This loop only completes already-observed releases. A broken
                # release is isolated so another project's receipt still lands.
                try:
                    result=self.reconcile(
                        project_id=row.get("project_id"),
                        run_id=row.get("run_id"),
                        merge_sha=row.get("merge_sha"),
                    )
                except (RuntimeError,ValueError) as exc:
                    failed.append({"event_id":event_id,
                                   "reason":"release_reconciliation_requires_review"})
                else:
                    if result["idempotent"]:
                        idempotent+=1
                    else:
                        reconciled+=1
                if scanned>=max_items:
                    return {"status":"partial" if failed else "bounded",
                            "scanned":scanned,"reconciled":reconciled,
                            "idempotent":idempotent,"needs_review":failed,
                            "truncated":True}
            if len(rows)<_PAGE:
                exhausted=True
                break
        return {"status":"partial" if failed else "complete",
                "scanned":scanned,"reconciled":reconciled,
                "idempotent":idempotent,"needs_review":failed,
                "truncated":not exhausted}
