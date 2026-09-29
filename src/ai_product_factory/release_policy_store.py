from __future__ import annotations

import json
import urllib.error
import urllib.request

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

    def facts(self,run_id:str)->dict:
        return self._rpc("factory_get_release_facts",{"p_run_id":run_id}) or {}

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
