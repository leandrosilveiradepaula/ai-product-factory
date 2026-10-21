from __future__ import annotations

import json
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote

from .supabase_server import resolve_supabase_server_config
from .followup_execution_epoch import run_followup_epoch
from .candidate_pr_receipt import validate_create_pr_candidate


@dataclass(frozen=True)
class SpecialistLaneItem:
    job_id:str
    run_id:str
    project_key:str
    repository:str
    role:str
    candidate_commit:str
    pr_number:int
    issue_number:int
    manifest:dict
    acceptance_criteria:tuple[object,...]
    execution_generation:int|None=None
    require_execution_generation:bool=False
    project_id:str|None=None
    claim_token:str|None=None


class SupabaseSpecialistLaneQueue:
    def __init__(self,*,url:str|None=None,secret_key:str|None=None,service_role_key:str|None=None)->None:
        cfg=resolve_supabase_server_config(url=url,secret_key=secret_key,service_role_key=service_role_key)
        self.url=cfg.url;self.headers=cfg.headers

    def _get(self,path:str)->list[dict]:
        req=urllib.request.Request(f"{self.url}/rest/v1/{path}",headers=self.headers,method="GET")
        try:
            with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane read failed: {path} ({exc.code})") from exc
        return [] if not raw else json.loads(raw)

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

    def enqueue(self,run_id:str)->dict:
        return self._rpc("factory_enqueue_specialist_lanes",{"p_run_id":run_id}) or {}

    def recover_expired(self,max_attempts:int=3)->dict:
        return self._rpc("factory_recover_specialist_lanes",{"p_max_attempts":max_attempts}) or {}

    def claim(self,role:str,worker_id:str)->SpecialistLaneItem|None:
        data=self._rpc("factory_claim_specialist_lane",{"p_role":role,"p_worker_id":worker_id,"p_lease_seconds":600})
        if data is None:return None
        run_id=str(data["run_id"])
        usage=self._get(
            "factory_tool_usage?select=metadata&run_id=eq."+quote(run_id)+
            "&operation=eq.create_pr&order=created_at.desc&limit=1"
        )
        if not usage:raise RuntimeError("specialist lane run has no durable create_pr evidence")
        meta=usage[0].get("metadata") or {}
        pr_number=int(meta.get("pr") or 0)
        head_sha=str(meta.get("head_sha") or "")
        if pr_number<1:
            raise RuntimeError("specialist lane has invalid PR identity")
        runs=self._get("factory_runs?select=task_id,execution_route,metadata&id=eq."+quote(run_id)+"&limit=1")
        if not runs:raise RuntimeError("specialist lane run not found")
        generation,required=run_followup_epoch(runs[0])
        # The SQL claim must return a token bound to one exact lease and
        # the original run generation. No legacy tokenless completion.
        token=data.get("claim_token")
        if not isinstance(token,str):
            raise RuntimeError("specialist lane claim token unavailable")
        try:
            if str(uuid.UUID(token)) != token:
                raise ValueError("noncanonical token")
        except (ValueError,AttributeError) as exc:
            raise RuntimeError("specialist lane claim token invalid") from exc
        if not required or generation is None or data.get("execution_generation") != generation:
            raise RuntimeError("specialist lane claim generation mismatch")
        validate_create_pr_candidate(
            read=self._get,run_id=run_id,pr_number=pr_number,
            original_head=head_sha,candidate_commit=str(data["candidate_commit"]),
            run_metadata=runs[0].get("metadata") or {},
        )
        task_id=str(runs[0]["task_id"])
        issue_number=int(((runs[0].get("metadata") or {}).get("github_issue") or {}).get("number") or 0)
        tasks=self._get("factory_tasks?select=project_id,acceptance_criteria&id=eq."+quote(task_id)+"&limit=1")
        if not tasks or not isinstance(tasks[0],dict) or not isinstance(tasks[0].get("project_id"),str):
            raise RuntimeError("specialist run task has no project binding")
        criteria=tuple(tasks[0].get("acceptance_criteria") or [])
        return SpecialistLaneItem(
            job_id=str(data["job_id"]),run_id=run_id,project_key=str(data["project_key"]),
            repository=str(data["repository"]),role=str(data["role"]),
            candidate_commit=str(data["candidate_commit"]),pr_number=pr_number,
            issue_number=issue_number,manifest=dict(data.get("manifest") or {}),
            acceptance_criteria=criteria,
            execution_generation=generation,require_execution_generation=required,
            project_id=tasks[0]["project_id"],
            claim_token=token,
        )

    def complete(self,item:SpecialistLaneItem,*,status:str,findings:list[dict],evidence:dict)->dict:
        if not isinstance(item.claim_token,str) or not item.claim_token:
            raise RuntimeError("specialist completion requires claim token")
        if not isinstance(evidence,dict) or "_factory_claim_token" in evidence:
            raise RuntimeError("specialist evidence contains reserved claim token")
        # A token is a one-claim capability, checked transactionally by SQL.
        # It is stripped before storing normal specialist evidence.
        completed=self._rpc("factory_complete_specialist_lane",{
            "p_job_id":item.job_id,"p_status":status,
            "p_findings":findings,
            "p_evidence":{**evidence,"_factory_claim_token":item.claim_token},
        }) or {}
        # One SQL transaction now finalizes the review and its repair
        # consequence. A token-only completion without an atomic receipt
        # is not accepted as successful.
        if completed.get("post_review_applied") is not True:
            raise RuntimeError("specialist completion missing atomic post-review receipt")
        if status=="failed" and item.role in {"security","qa"}:
            if not isinstance(completed.get("repair"),dict):
                raise RuntimeError("specialist completion missing repair decision")
        elif status=="passed" and item.role in {"security","qa"}:
            if not isinstance(completed.get("repair_recheck"),dict):
                raise RuntimeError("specialist completion missing repair reconciliation")
        return completed
