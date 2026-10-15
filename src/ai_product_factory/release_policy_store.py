from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from urllib.parse import quote

from .supabase_server import resolve_supabase_server_config


class SupabaseReleasePolicyStore:
    def __init__(self,*,url:str|None=None,secret_key:str|None=None,service_role_key:str|None=None)->None:
        cfg=resolve_supabase_server_config(url=url,secret_key=secret_key,service_role_key=service_role_key)
        self.url=cfg.url;self.headers=cfg.headers

    def _rpc(self,name:str,payload:dict):
        req=urllib.request.Request(
            f"{self.url}/rest/v1/rpc/{name}",
            data=json.dumps(payload).encode(),
            headers={**self.headers,"Content-Type":"application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane RPC failed: {name} ({exc.code})") from exc
        return None if not raw else json.loads(raw)

    def _get(self,table:str,query:str):
        req=urllib.request.Request(
            f"{self.url}/rest/v1/{table}?{query}",
            headers=self.headers,
            method="GET",
        )
        try:
            with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane read failed: {table} ({exc.code})") from exc
        return [] if not raw else json.loads(raw)

    def facts(self,run_id:str)->dict:
        facts=self._rpc("factory_get_release_facts",{"p_run_id":run_id}) or {}
        rows=self._get(
            "factory_evaluations",
            "select=status,baseline_ref,result,created_at"
            f"&run_id=eq.{quote(run_id)}&eval_type=eq.product_readiness"
            "&order=created_at.desc&limit=1",
        )
        if rows:
            row=rows[0]
            result=row.get("result") if isinstance(row.get("result"),dict) else {}
            facts["product_readiness"]={
                **result,
                "evaluation_status":row.get("status"),
                "baseline_ref":row.get("baseline_ref"),
                "created_at":row.get("created_at"),
            }
            # This identity comes from the trusted Control Plane project record,
            # never from an evaluation result JSON supplied by the evaluator.
            project_id=facts.get("project_id")
            if isinstance(project_id,str) and re.fullmatch(
                r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",project_id
            ):
                project_rows=self._get(
                    "factory_projects",
                    "select=project_kind&id=eq."+quote(project_id,safe="")+"&limit=2",
                )
                if (isinstance(project_rows,list) and len(project_rows)==1
                    and isinstance(project_rows[0],dict)):
                    facts["project_kind"]=project_rows[0].get("project_kind")
                    if facts["project_kind"]=="existing":
                        baseline_rows=self._get(
                            "factory_evaluations",
                            "select=status,baseline_ref,result,created_at"
                            f"&run_id=eq.{quote(run_id,safe='')}"
                            "&eval_type=eq.existing_project_baseline"
                            "&order=created_at.desc,id.desc&limit=1",
                        )
                        if (isinstance(baseline_rows,list) and len(baseline_rows)==1
                            and isinstance(baseline_rows[0],dict)):
                            baseline=baseline_rows[0]
                            facts["existing_project_baseline"]={
                                "evaluation_status":baseline.get("status"),
                                "baseline_ref":baseline.get("baseline_ref"),
                                "result":baseline.get("result"),
                            }
        return facts

    def record(self,*,run_id:str,assessment)->dict:
        decision_id=self._rpc("factory_record_policy_decision",{
            "p_run_id":run_id,
            "p_policy_key":assessment.decision.policy_key,
            "p_policy_version":assessment.decision.policy_version,
            "p_outcome":assessment.decision.outcome,
            "p_reasons":list(assessment.decision.reasons),
            "p_context":assessment.context,
        })
        report_status="blocked" if assessment.decision.blocked else "ready_for_human_release"
        report_id=self._rpc("factory_record_release_report",{
            "p_run_id":run_id,
            "p_policy_decision_id":decision_id,
            "p_candidate_commit":assessment.report["candidate_commit"],
            "p_status":report_status,
            "p_report":assessment.report,
            "p_rollback":assessment.rollback,
        })
        return {"decision_id":decision_id,"report_id":report_id,"status":report_status}

    def mark_released(self,run_id:str,merge_sha:str)->dict:
        return self._rpc("factory_mark_release_report_released",{"p_run_id":run_id,"p_merge_sha":merge_sha}) or {}
