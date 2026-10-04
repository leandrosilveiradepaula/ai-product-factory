from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .runtime_worker import RuntimeQueue, StageEvidence, WorkItem
from .agent_scheduler import AgentProfile
from .project_brain import build_project_brain_graph
from .traceability import build_requirement_trace
from .definition_of_done import compile_definition_of_done
from .execution_team_planner import build_execution_team_plan
from .supabase_server import resolve_supabase_server_config


class SupabaseRuntimeQueue(RuntimeQueue):
    """Server-side REST/RPC adapter for the durable runtime queue."""
    def __init__(self, *, url: str | None = None, service_role_key: str | None = None) -> None:
        cfg=resolve_supabase_server_config(url=url,service_role_key=service_role_key)
        self.url=cfg.url
        self.key=cfg.key
        self.headers=cfg.headers

    def _get(self, path: str):
        req=urllib.request.Request(f"{self.url}/rest/v1/{path}",method="GET",headers=self.headers)
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane read failed: {path} ({exc.code})") from exc
        return [] if not raw else json.loads(raw)

    def _rpc(self, name: str, payload: dict):
        req=urllib.request.Request(f"{self.url}/rest/v1/rpc/{name}",data=json.dumps(payload).encode(),method="POST",headers={**self.headers,"Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane RPC failed: {name} ({exc.code})") from exc
        return None if not raw else json.loads(raw)


    def rebuild_team_plan(self,source_run_id:str,profiles:tuple[AgentProfile,...])->dict:
        if not source_run_id.strip():
            raise ValueError("source run id is required")
        runs=self._get(
            "factory_runs?select=id,task_id&id=eq."+source_run_id+"&limit=1"
        )
        if len(runs)!=1:
            raise ValueError("source run not found")
        tasks=self._get(
            "factory_tasks?select=id,project_id&id=eq."+str(runs[0]["task_id"])+"&limit=1"
        )
        if len(tasks)!=1:
            raise ValueError("source task not found")
        projects=self._get(
            "factory_projects?select=id,manifest&id=eq."+str(tasks[0]["project_id"])+"&limit=1"
        )
        if len(projects)!=1:
            raise ValueError("source project not found")
        manifest=projects[0].get("manifest")
        engineering_plan=manifest.get("engineering_plan") if isinstance(manifest,dict) else None
        if not isinstance(engineering_plan,dict) or not isinstance(engineering_plan.get("tasks"),list):
            raise ValueError("persisted engineering plan is unavailable")
        plan=build_execution_team_plan(engineering_plan,profiles)
        recorded=self._rpc("factory_record_execution_team_plan",{"p_run_id":source_run_id,"p_plan":plan}) or {}
        out={"status":recorded.get("status") or plan.get("status"),"team_plan_id":recorded.get("id"),"plan":plan}
        if recorded.get("id") and recorded.get("status")=="ready":
            materialized=self._rpc("factory_materialize_change_set",{"p_team_plan_id":recorded["id"]}) or {}
            out["change_set"]=materialized
        return out

    def retry_failed_run(self,source_run_id:str,reason:str)->dict:
        source_run_id=source_run_id.strip()
        reason=reason.strip()
        if not source_run_id:
            raise ValueError("source run id is required")
        if not reason:
            raise ValueError("retry reason is required")
        data=self._rpc("factory_retry_failed_run",{"p_source_run_id":source_run_id,"p_reason":reason})
        if not isinstance(data,dict):
            raise RuntimeError("retry RPC returned an invalid response")
        return data

    def recover_expired(self,max_attempts:int=3)->dict:
        data=self._rpc("factory_recover_expired_runs",{"p_max_attempts":max_attempts})
        return data or {"requeued":0,"failed":0}

    def resume_resolved_decisions(self)->dict:
        data=self._rpc("factory_resume_resolved_decisions",{})
        if not isinstance(data,dict):
            raise RuntimeError("decision resume RPC returned an invalid response")
        return data

    def reconcile_terminal_descendants(self)->dict:
        data=self._rpc("factory_reconcile_terminal_task_descendants",{})
        if not isinstance(data,dict):
            raise RuntimeError("terminal descendant reconciliation returned an invalid response")
        return data

    def claim_next(self, worker_id: str) -> WorkItem | None:
        data=self._rpc("factory_claim_next_run",{"p_worker_id":worker_id})
        if data is None: return None
        return WorkItem(run_id=data["run_id"],task_id=data["task_id"],project_id=data["project_id"],project_key=data["project_key"],stages=tuple(data.get("stages",[])),context=data.get("context",{}))

    def record_stage_event(self,item:WorkItem,stage:str,status:str)->None:
        if status not in {"started","failed"}:
            raise ValueError("unsupported runtime stage event status")
        self._rpc("factory_record_runtime_stage",{
            "p_run_id":item.run_id,"p_stage":stage,"p_status":status,"p_output":{}
        })

    def record_stage(self,item:WorkItem,evidence:StageEvidence)->None:
        self._rpc("factory_record_runtime_stage",{"p_run_id":item.run_id,"p_stage":evidence.stage,"p_status":evidence.status,"p_output":evidence.output})
        self._rpc("factory_persist_product_stage",{"p_run_id":item.run_id,"p_stage":evidence.stage,"p_output":evidence.output})
        if evidence.stage=="planning":
            trace=build_requirement_trace(evidence.output)
            self._rpc("factory_record_requirement_trace",{
                "p_project_id":item.project_id,
                "p_source_run_id":item.run_id,
                "p_source_ref":f"run:{item.run_id}:planning",
                "p_requirements":list(trace.requirements),
            })

            brain=build_project_brain_graph(project_key=item.project_key,engineering_plan=evidence.output,context=item.context)
            self._rpc("factory_record_project_brain_snapshot",{
                "p_project_id":item.project_id,
                "p_source_ref":f"run:{item.run_id}:planning",
                "p_summary":brain.summary,
                "p_nodes":list(brain.nodes),
                "p_edges":list(brain.edges),
            })

            change_set_id=None
            team_plan=evidence.output.get("_team_plan")
            if isinstance(team_plan,dict):
                recorded=self._rpc("factory_record_execution_team_plan",{"p_run_id":item.run_id,"p_plan":team_plan}) or {}
                team_plan_id=recorded.get("id")
                if team_plan_id and recorded.get("status")=="ready":
                    materialized=self._rpc("factory_materialize_change_set",{"p_team_plan_id":team_plan_id}) or {}
                    change_set_id=materialized.get("change_set_id")

            dod=compile_definition_of_done(
                engineering_plan=evidence.output,
                manifest=item.context.get("manifest") if isinstance(item.context.get("manifest"),dict) else {},
                requirement_count=trace.count,
            )
            self._rpc("factory_record_definition_of_done",{
                "p_project_id":item.project_id,
                "p_source_run_id":item.run_id,
                "p_change_set_id":change_set_id,
                "p_checks":dod.as_records(),
            })

    def complete(self,item:WorkItem)->None:
        self._rpc("factory_finish_run",{"p_run_id":item.run_id,"p_status":"completed","p_error":None})

    def fail(self,item:WorkItem,error:str)->None:
        self._rpc("factory_finish_run",{"p_run_id":item.run_id,"p_status":"failed","p_error":error[:2000]})
