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
        if not merge_sha.strip():
            raise ValueError("merge sha is required")
        rows=self._request("GET",f"factory_projects?select=id,lifecycle_stage,manifest&id=eq.{quote(project_id)}&limit=1") or []
        if not rows:
            raise RuntimeError("project not found")
        project=rows[0]
        current_stage=str(project.get("lifecycle_stage") or "")
        target_stage="operations" if _STAGE_RANK.get(current_stage,-1) < _STAGE_RANK["operations"] else current_stage

        manifest=dict(project.get("manifest") or {})
        already=(manifest.get("last_release") or {}).get("merge_sha")==merge_sha and target_stage==current_stage
        manifest["head_sha"]=merge_sha
        manifest["reported_stage"]="operations"
        manifest.pop("current_task",None)
        if manifest.get("autonomy")=="read_only_verification":
            manifest.pop("autonomy",None)
        readiness=dict(manifest.get("runtime_readiness") or {})
        if readiness.get("current_scope")=="read_only_verification":
            readiness.pop("current_scope",None)
        if readiness:
            manifest["runtime_readiness"]=readiness
        manifest["last_release"]={"run_id":run_id,"merge_sha":merge_sha,"source":"observed_human_merge"}

        if not already:
            # Never equate a human-merged release with global product readiness.
            # The release report is an additional observation: if unavailable,
            # preserve a fail-closed audit obligation, without replaying workers.
            try:
                reports = self._request(
                    "GET",
                    "factory_release_reports?"
                    "select=project_id,run_id,status,candidate_commit,report"
                    f"&project_id=eq.{quote(project_id,safe='')}"
                    f"&run_id=eq.{quote(run_id,safe='')}&limit=2",
                )
            except (RuntimeError, OSError, ValueError, TypeError):
                reports = None
            followup = summarize_released_product(
                project_id=project_id, run_id=run_id,
                merge_sha=merge_sha, report_rows=reports,
            )
            manifest["product_readiness_followup"] = followup
            self._request(
                "PATCH",
                f"factory_projects?id=eq.{quote(project_id)}",
                {"lifecycle_stage":target_stage,"manifest":manifest},
            )
            self._request(
                "POST",
                "factory_project_state_snapshots",
                {
                    "project_id":project_id,
                    "run_id":run_id,
                    "observed_stage":"operations",
                    "summary":"Release humano observado; estado do projeto reconciliado com a entrega real.",
                    "evidence":[{"type":"human_release","merge_sha":merge_sha}],
                    # Not a new executable task. Evidence required for a
                    # full-product audit is retained for future explicit work.
                    "gaps":[
                        {"kind":"global_readiness_evidence_required","domain":domain,
                         "reason_code":followup["reason_code"]}
                        for domain in followup["pending_domains"]
                    ],
                    "constraints":[],
                    "source_status":{
                        "release":"merged",
                        "product_readiness":followup["status"],
                        "product_readiness_scope":"current_product_after_release",
                        "product_readiness_report_verified":followup["report_verified"],
                    },
                },
            )
            self._request(
                "POST",
                "factory_audit_events",
                {
                    "project_id":project_id,
                    "run_id":run_id,
                    "actor_type":"system",
                    "actor_ref":"release-followup",
                    "event_type":"project.state.reconciled_after_release",
                    "payload":{
                        "merge_sha":merge_sha,"lifecycle_stage":target_stage,
                        "product_readiness":followup["status"],
                        "product_readiness_reason_code":followup["reason_code"],
                    },
                },
            )
        return {"project_id":project_id,"lifecycle_stage":target_stage,"merge_sha":merge_sha,"idempotent":already}
