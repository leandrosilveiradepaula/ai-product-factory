from __future__ import annotations

import json
import re
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote

from .supabase_server import resolve_supabase_server_config
from .verified_repin import verified_repin


@dataclass(frozen=True)
class ChangeSetBinding:
    change_set_id:str
    work_unit_id:str
    base_commit:str
    source_commit:str
    integration_branch:str
    wave:int


@dataclass(frozen=True)
class ChangeSetIntegrationItem:
    change_set_id:str
    project_key:str
    repository:str
    source_commit:str
    candidate_commit:str
    integration_branch:str
    current_wave:int
    work_units:tuple[dict,...]
    project_id:str|None=None
    execution_generation:int|None=None
    lease_owner:str|None=None
    project_kind:str|None=None
    delivery_target:dict|None=None
    journey_binding:dict|None=None
    request_id:str|None=None
    governance_amendment:dict|None=None


class SupabaseChangeSetStore:
    def __init__(self,*,url:str|None=None,secret_key:str|None=None,service_role_key:str|None=None)->None:
        cfg=resolve_supabase_server_config(url=url,secret_key=secret_key,service_role_key=service_role_key)
        self.url=cfg.url;self.headers=cfg.headers

    def _get(self,path:str):
        req=urllib.request.Request(f"{self.url}/rest/v1/{path}",method="GET",headers=self.headers)
        try:
            with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane read failed: {path} ({exc.code})") from exc
        return [] if not raw else json.loads(raw)

    def _rpc(self,name:str,payload:dict):
        req=urllib.request.Request(
            f"{self.url}/rest/v1/rpc/{name}",data=json.dumps(payload).encode(),
            headers={**self.headers,"Content-Type":"application/json"},method="POST",
        )
        try:
            with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane RPC failed: {name} ({exc.code})") from exc
        return None if not raw else json.loads(raw)

    def _patch(self,path:str,payload:dict)->list[dict]:
        req=urllib.request.Request(
            f"{self.url}/rest/v1/{path}",data=json.dumps(payload).encode(),
            headers={**self.headers,"Content-Type":"application/json","Prefer":"return=representation"},
            method="PATCH",
        )
        try:
            with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane update failed: {path} ({exc.code})") from exc
        return [] if not raw else json.loads(raw)

    def assert_project_running(self,project_key:str)->None:
        if not isinstance(project_key,str) or not project_key.strip():
            raise PermissionError("missing project key for integration")
        rows=self._get("factory_projects?select=id&project_key=eq."+quote(project_key,safe="")+"&limit=1")
        if len(rows)!=1 or not rows[0].get("id"):
            raise PermissionError("integration project not found")
        self._rpc("factory_assert_project_running",{"p_project_id":rows[0]["id"]})

    def recover_expired(self,max_attempts:int=3)->dict:
        return self._rpc("factory_recover_change_sets",{"p_max_attempts":max_attempts}) or {}

    def frozen_source_commit(self,change_set_id:str)->str|None:
        rows=self._get(
            "factory_change_sets?select=source_commit&id=eq."+change_set_id+"&limit=1"
        )
        if not rows:
            raise RuntimeError("change set not found")
        value=rows[0].get("source_commit")
        return str(value) if value else None

    def bind_source(self,*,run_id:str,source_commit:str,integration_branch:str,work_branch:str)->ChangeSetBinding:
        data=self._rpc("factory_bind_change_set_source",{
            "p_run_id":run_id,"p_source_commit":source_commit,
            "p_integration_branch":integration_branch,"p_work_branch":work_branch,
        })
        if not isinstance(data,dict):raise RuntimeError("change-set source binding returned no data")
        return ChangeSetBinding(
            change_set_id=str(data["change_set_id"]),work_unit_id=str(data["work_unit_id"]),
            base_commit=str(data["base_commit"]),source_commit=str(data["source_commit"]),
            integration_branch=str(data["integration_branch"]),wave=int(data["wave"]),
        )

    def context_source(self,run_id:str)->dict:
        data=self._rpc("factory_work_unit_context_source",{"p_run_id":run_id})
        if not isinstance(data,dict):raise RuntimeError("work-unit context source returned no data")
        project_key=str(data.get("project_key") or "").strip()
        decisions=[]
        project_kind=""
        delivery_target=None
        repin_evidence=None
        if project_key:
            rows=self._get(
                "factory_projects?select=id,manifest,project_kind&project_key=eq."+quote(project_key)+"&limit=1"
            )
            if rows:
                project_kind=str(rows[0].get("project_kind") or "")
                if isinstance(rows[0].get("manifest"),dict):
                    value=rows[0]["manifest"].get("human_decisions")
                    if isinstance(value,list):
                        decisions=value
                    delivery_target=rows[0]["manifest"].get("delivery_target")
                    if (project_kind=="existing" and isinstance(delivery_target,dict)
                        and isinstance(delivery_target.get("repin_policy"),dict)
                        and delivery_target["repin_policy"].get("enabled") is True):
                        project_id=str(rows[0].get("id") or "")
                        if project_id:
                            controls=self._get(
                                "factory_project_execution_controls?"
                                "select=project_id,state,generation,version&project_id=eq."
                                +quote(project_id,safe="")+"&limit=1"
                            )
                            if len(controls)!=1:
                                raise PermissionError("missing current project execution epoch for repin")
                            events=self._get(
                                "factory_audit_events?"
                                "select=id,project_id,event_type,actor_type,actor_ref,payload"
                                "&project_id=eq."+quote(project_id,safe="")
                                +"&event_type=in.(project.delivery_target.reconciled,project.delivery_target.replaced)"
                                +"&order=id.desc&limit=40"
                            )
                            repin_evidence=verified_repin(
                                project_id=project_id,project_key=project_key,
                                repository=str(data.get("repository") or ""),
                                target=delivery_target,control=controls[0],events=events,
                            )

        assignment=dict(data.get("assignment") if isinstance(data.get("assignment"),dict) else {})
        work_unit_id=str(data.get("work_unit_id") or "").strip()
        if work_unit_id:
            units=self._get(
                "factory_change_set_work_units?select=task_id&id=eq."+quote(work_unit_id)+"&limit=1"
            )
            task_id=str(units[0].get("task_id") or "").strip() if units else ""
            if task_id:
                tasks=self._get(
                    "factory_tasks?select=scope_keys,required_capabilities,agent_role&id=eq."+quote(task_id)+"&limit=1"
                )
                if tasks:
                    task=tasks[0]
                    scopes=task.get("scope_keys")
                    capabilities=task.get("required_capabilities")
                    if isinstance(scopes,list) and scopes:
                        assignment["scope_keys"]=scopes
                    if isinstance(capabilities,list) and capabilities:
                        assignment["required_capabilities"]=capabilities
                    role=str(task.get("agent_role") or "").strip()
                    if role:
                        assignment["agent_role"]=role

        enriched=dict(data)
        enriched["assignment"]=assignment
        enriched["human_decisions"]=decisions
        enriched["project_kind"]=project_kind
        enriched["delivery_target"]=delivery_target
        enriched["repin_evidence"]=repin_evidence
        # The RPC predates V2. Enrich from the run/journey relation rather
        # than allowing the caller or mutable manifest to select a source.
        runs=self._get("factory_runs?select=journey_id&id=eq."+quote(run_id,safe="")+"&limit=1")
        if not isinstance(runs,list) or len(runs)!=1:
            raise PermissionError("run journey identity is unavailable")
        journey_id=runs[0].get("journey_id")
        if journey_id is not None:
            journeys=self._get("factory_journeys?select=id,project_id,request_id,binding,request_snapshot,state"
                "&id=eq."+quote(str(journey_id),safe="")+"&limit=1")
            if len(journeys)!=1 or journeys[0].get("state") not in ("source_bound","executing","preview_verified","awaiting_release"):
                raise PermissionError("journey context is not executable")
            journey=journeys[0]
            # The legacy context RPC returns project_key but no project_id.
            # Resolve the unique project from the control plane; never compare
            # against a missing field or accept caller-provided identity.
            if not project_key:
                raise PermissionError("journey context project key missing")
            identity_rows=self._get(
                "factory_projects?select=id,project_key&project_key=eq."
                +quote(project_key,safe="")+"&limit=2"
            )
            if (not isinstance(identity_rows,list) or len(identity_rows)!=1
                or identity_rows[0].get("project_key")!=project_key
                or not identity_rows[0].get("id")
                or str(journey.get("project_id") or "")!=str(identity_rows[0]["id"])):
                raise PermissionError("journey context cross-project")
            change_sets=self._get(
                "factory_change_sets?select=id,metadata"
                "&id=eq."+quote(str(data.get("change_set_id") or ""),safe="")+"&limit=1"
            )
            if not isinstance(change_sets,list) or len(change_sets)!=1:
                raise PermissionError("V2 change set recovery context missing")
            meta=change_sets[0].get("metadata")
            amendment=meta.get("governance_amendment") if isinstance(meta,dict) else None
            if amendment is not None:
                if not isinstance(amendment,dict):
                    raise PermissionError("V2 governance amendment receipt invalid")
                enriched["governance_amendment"]=amendment
            enriched["journey_id"]=journey_id
            enriched["request_id"]=journey.get("request_id")
            enriched["journey_binding"]=journey.get("binding")
            snapshot=journey.get("request_snapshot")
            if not isinstance(snapshot,dict) or not isinstance(snapshot.get("text"),str):
                raise PermissionError("journey request snapshot unavailable")
            enriched["journey_request"]=snapshot
            enriched["task"]={**(enriched.get("task") if isinstance(enriched.get("task"),dict) else {}),"description":snapshot["text"]}
            # Do not pass V1 selection/evidence to a V2 implementation prompt.
            enriched["delivery_target"]=None
            enriched["repin_evidence"]=None
        return enriched

    def record_context(self,*,run_id:str,packet_hash:str,packet:dict)->dict:
        return self._rpc("factory_record_work_unit_context",{
            "p_run_id":run_id,"p_packet_hash":packet_hash,"p_packet":packet,
        }) or {}

    def set_repair_status(self,*,run_id:str,status:str)->dict:
        return self._rpc("factory_set_repair_status",{"p_run_id":run_id,"p_status":status}) or {}

    def block_work_unit(self,*,run_id:str,reason:str,blocker_type:str="implementation_blocked")->dict:
        if not run_id.strip() or not reason.strip():
            raise ValueError("run id and blocker reason are required")
        return self._rpc("factory_block_change_set_work_unit",{
            "p_run_id":run_id,
            "p_reason":reason[:1000],
            "p_blocker_type":blocker_type,
        }) or {}

    def complete_work_unit(self,*,run_id:str,output_commit:str,changed_files:tuple[str,...])->dict:
        return self._rpc("factory_complete_change_set_work_unit",{
            "p_run_id":run_id,"p_output_commit":output_commit,"p_changed_files":list(changed_files),
        }) or {}

    def require_epoch_mutation_ready(self)->None:
        expected={
            "version":1,"atomic_completion":True,
            "atomic_release":True,"phase_checkpoints":True,
        }
        response=self._rpc("factory_integration_epoch_write_readiness",{})
        if (response!=expected or not isinstance(response,dict)
            or type(response.get("version")) is not int
            or any(type(response.get(key)) is not bool
                   for key in ("atomic_completion","atomic_release","phase_checkpoints"))):
            raise RuntimeError("atomic integration SQL migration is not ready")

    def claim_integration(self,worker_id:str)->ChangeSetIntegrationItem|None:
        if (not isinstance(worker_id,str) or not worker_id.strip() or len(worker_id)>128 or
            worker_id!=worker_id.strip() or any(ord(c)<33 or ord(c)==127 for c in worker_id)):
            raise ValueError("integration worker ID is required and must be safe")
        data=self._rpc("factory_claim_change_set_integration",{"p_worker_id":worker_id,"p_lease_seconds":600})
        if data is None:
            return None
        if not isinstance(data,dict):
            raise RuntimeError("integration claim returned a non-object payload")
        required=("change_set_id","project_key","repository","source_commit","candidate_commit","integration_branch")
        for field in required:
            if not isinstance(data.get(field),str) or not data[field].strip():
                raise RuntimeError("integration claim missing "+field)
        wave=data.get("current_wave")
        if isinstance(wave,bool) or not isinstance(wave,int) or wave<1:
            raise RuntimeError("integration claim has invalid wave")
        units=data.get("work_units")
        if not isinstance(units,list) or not units:
            raise RuntimeError("integration claim has no work units")
        for unit in units:
            if not isinstance(unit,dict):
                raise RuntimeError("integration claim has invalid work unit")
            for field in ("plan_task_key","base_commit","output_commit"):
                if not isinstance(unit.get(field),str) or not unit[field].strip():
                    raise RuntimeError("integration work unit missing "+field)
            paths=unit.get("changed_files")
            if not isinstance(paths,list) or not paths or any(not isinstance(p,str) or not p.strip() for p in paths):
                raise RuntimeError("integration work unit has invalid changed files")
            if unit["base_commit"]!=data["candidate_commit"]:
                raise RuntimeError("integration work unit has stale candidate base")
        # The claim is an untrusted privileged RPC response. Never let malformed
        # repository, ref or file identities reach the GitHub write adapter.
        repo_parts=data["repository"].split("/")
        if len(repo_parts)!=2 or any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}",part) or part in (".","..") for part in repo_parts):
            raise RuntimeError("integration claim has invalid repository")
        branch=data["integration_branch"]
        if (len(branch)>200 or not branch.startswith("factory/") or
            not re.fullmatch(r"[A-Za-z0-9_./-]+",branch) or
            branch.endswith(("/", ".")) or ".." in branch or "//" in branch or
            "/." in branch or "@{" in branch or branch.endswith(".lock")):
            raise RuntimeError("integration claim targets unsafe branch")
        if len(data["project_key"])>150 or any(ord(c)<33 or ord(c)==127 for c in data["project_key"]):
            raise RuntimeError("integration claim has unsafe project key")
        for field in ("source_commit","candidate_commit"):
            value=data[field]
            if len(value)>128 or any(ord(c)<33 or ord(c)==127 for c in value):
                raise RuntimeError("integration claim has unsafe commit reference")
        try:
            uuid.UUID(data["change_set_id"])
            uuid.UUID(data["project_id"])
        except (ValueError,TypeError,AttributeError) as exc:
            raise RuntimeError("integration claim has invalid UUID capability") from exc
        if len(units)>100:
            raise RuntimeError("integration claim exceeds work unit limit")
        seen_tasks=set()
        seen_paths=set()
        for unit in units:
            task_key=unit["plan_task_key"]
            if task_key in seen_tasks:
                raise RuntimeError("integration claim repeats plan task")
            seen_tasks.add(task_key)
            if len(unit["plan_task_key"])>200 or any(ord(c)<33 or ord(c)==127 for c in unit["plan_task_key"]):
                raise RuntimeError("integration work unit has unsafe task key")
            if len(unit["output_commit"])>128 or any(ord(c)<33 or ord(c)==127 for c in unit["output_commit"]):
                raise RuntimeError("integration work unit has unsafe output reference")
            if unit["output_commit"]==unit["base_commit"]:
                raise RuntimeError("integration work unit has unchanged output")
            if len(unit["changed_files"])>200:
                raise RuntimeError("integration work unit exceeds changed file limit")
            for path in unit["changed_files"]:
                if len(path)>1024:
                    raise RuntimeError("integration path exceeds length limit")
                if any(ord(c)<32 or ord(c)==127 for c in path):
                    raise RuntimeError("integration path contains control character")
                if any(len(part)>255 for part in path.split("/")):
                    raise RuntimeError("integration path segment exceeds limit")
                if any(part.lower()==".git" for part in path.split("/")):
                    raise RuntimeError("integration path targets git internals")
                if path.endswith(("/", " ", ".")) or any(part.endswith((" ", ".")) for part in path.split("/")):
                    raise RuntimeError("integration work unit has unsafe path suffix")
                if path.startswith("/") or "\\" in path or any(part in ("",".","..") for part in path.split("/")):
                    raise RuntimeError("integration work unit has unsafe path")
                # Reject special filesystem names and Git path ambiguity before any remote read/write.
                segments=path.split("/")
                if any(part.casefold() in (".git", ".gitmodules", ".gitattributes", ".gitignore") for part in segments):
                    raise RuntimeError("integration path targets protected git metadata")
                if any(":" in part for part in segments):
                    raise RuntimeError("integration path contains colon")
                if any("?" in part or "*" in part for part in segments):
                    raise RuntimeError("integration path contains wildcard")
                if any('"' in part or "<" in part or ">" in part or "|" in part for part in segments):
                    raise RuntimeError("integration path contains forbidden character")
                if any(part.upper().split(".")[0] in (
                    "CON","PRN","AUX","NUL","COM1","COM2","COM3","COM4","COM5","COM6","COM7","COM8","COM9",
                    "LPT1","LPT2","LPT3","LPT4","LPT5","LPT6","LPT7","LPT8","LPT9",
                ) for part in segments):
                    raise RuntimeError("integration path contains reserved device name")
                if any(part.startswith("~") for part in segments):
                    raise RuntimeError("integration path contains home alias")
                if any(part.startswith("-") for part in segments):
                    raise RuntimeError("integration path contains option-like segment")
                if any(part.endswith(".lock") for part in segments):
                    raise RuntimeError("integration path contains lock file")
                if any("\\u202e" in part or "\\u202d" in part for part in segments):
                    raise RuntimeError("integration path contains bidi override")
                if any(part.startswith(".") and part not in (".github",) for part in segments):
                    raise RuntimeError("integration path contains hidden segment")
                if path in seen_paths:
                    raise RuntimeError("integration claim has conflicting file owners")
                seen_paths.add(path)
        if len(seen_paths)>500:
            raise RuntimeError("integration claim exceeds file limit")
        # These are exact payload invariants, not project-specific directory policy.
        # On the first integration wave the candidate legitimately equals the source.
        # Completed work units carry the changed output commits, validated above.
        # Later waves likewise use the current candidate as their common base.
        # Never reject a first-wave claim merely because no integration commit exists yet.
        for unit in units:
            if len(unit["changed_files"])!=len(set(unit["changed_files"])):
                raise RuntimeError("integration work unit repeats changed file")
        generation=data.get("execution_generation")
        if isinstance(generation,bool) or not isinstance(generation,int) or generation<1:
            raise RuntimeError("integration claim missing execution generation")
        if not isinstance(data.get("project_id"),str) or not data["project_id"].strip():
            raise RuntimeError("integration claim missing project capability")
        if data.get("lease_owner")!=worker_id:
            raise RuntimeError("integration claim lease owner mismatch")
        projects=self._get("factory_projects?select=project_kind,manifest,repository&id=eq."+quote(data["project_id"],safe="")+"&limit=1")
        if not isinstance(projects,list) or len(projects)!=1 or projects[0].get("repository")!=data["repository"]:
            raise PermissionError("integration project identity unavailable or mismatched")
        row=projects[0]
        kind=row.get("project_kind")
        if kind not in ("greenfield","existing","platform"):
            raise PermissionError("unrecognized integration project kind")
        manifest=row.get("manifest")
        target=manifest.get("delivery_target") if isinstance(manifest,dict) else None
        if kind=="platform" and target not in (None,{}):
            raise PermissionError("platform cannot inherit an imported-project delivery target")
        journey_binding=None; request_id=None
        journeys_for_change=self._get("factory_change_sets?select=journey_id,metadata&id=eq."+quote(data["change_set_id"],safe="")+"&limit=1")
        if not isinstance(journeys_for_change,list) or len(journeys_for_change)!=1:
            raise PermissionError("integration Change Set journey identity unavailable")
        journey_id=journeys_for_change[0].get("journey_id")
        if journey_id is not None:
            journeys=self._get("factory_journeys?select=id,project_id,request_id,binding,execution_generation,state"
                "&id=eq."+quote(str(journey_id),safe="")+"&limit=1")
            if len(journeys)!=1 or journeys[0].get("project_id")!=data["project_id"]:
                raise PermissionError("integration journey cross-project")
            journey=journeys[0]
            if journey.get("state") not in ("source_bound","executing","preview_verified","awaiting_release") or journey.get("execution_generation")!=generation:
                raise PermissionError("integration journey is not executable in claimed epoch")
            journey_binding=journey.get("binding"); request_id=journey.get("request_id")
            if not isinstance(journey_binding,dict) or not isinstance(request_id,str):
                raise PermissionError("integration journey binding unavailable")
            # V2 never exposes the legacy mutable target to its consumer.
            target=None
        metadata=journeys_for_change[0].get("metadata") or {}
        amendment=metadata.get("governance_amendment") if isinstance(metadata,dict) else None
        if amendment is not None and not isinstance(amendment,dict):
            raise PermissionError("integration governance amendment receipt is malformed")
        return ChangeSetIntegrationItem(
            change_set_id=data["change_set_id"],project_key=data["project_key"],
            repository=data["repository"],source_commit=data["source_commit"],
            candidate_commit=data["candidate_commit"],integration_branch=data["integration_branch"],
            current_wave=wave,work_units=tuple(units),
            project_id=data["project_id"],execution_generation=generation,lease_owner=worker_id,
            project_kind=kind,delivery_target=target,journey_binding=journey_binding,request_id=request_id,
            governance_amendment=amendment,
        )

    def assert_integration_epoch(self,item:ChangeSetIntegrationItem,worker_id:str)->None:
        if (not item.project_id or isinstance(item.execution_generation,bool) or
            not isinstance(item.execution_generation,int) or item.execution_generation<1 or
            not isinstance(worker_id,str) or not worker_id.strip() or item.lease_owner!=worker_id):
            raise PermissionError("integration claim capability is incomplete")
        self._rpc("factory_assert_change_set_integration_epoch",{
            "p_change_set_id":item.change_set_id,"p_project_id":item.project_id,
            "p_generation":item.execution_generation,"p_worker_id":worker_id,
            "p_wave":item.current_wave,
        })

    def complete_integration(self,*,item:ChangeSetIntegrationItem,candidate_commit:str,changed_files:tuple[str,...])->dict:
        if not item.project_id or not item.execution_generation or not item.lease_owner:
            raise PermissionError("integration completion requires claimed epoch capability")
        result=self._rpc("factory_complete_change_set_integration_epoch",{
            "p_change_set_id":item.change_set_id,"p_project_id":item.project_id,
            "p_generation":item.execution_generation,"p_worker_id":item.lease_owner,
            "p_wave":item.current_wave,"p_candidate_commit":candidate_commit,
            "p_changed_files":list(changed_files),
        })
        if not isinstance(result,dict):
            raise RuntimeError("atomic integration completion returned no result")
        return result

    def mark_repair_wave_integrated(self,*,change_set_id:str,wave:int,candidate_commit:str)->dict:
        # Legacy endpoint has no epoch capability. Repair jobs are now mutated in
        # the same transaction as completion; no second unguarded write is allowed.
        raise PermissionError("repair wave completion is part of atomic integration")

    def prepare_release(self,*,item:ChangeSetIntegrationItem,issue_number:int,issue_url:str,pr_number:int,candidate_commit:str,branch:str)->dict:
        if not item.project_id or not item.execution_generation or not item.lease_owner:
            raise PermissionError("release preparation requires claimed epoch capability")
        result=self._rpc("factory_prepare_change_set_release_epoch",{
            "p_change_set_id":item.change_set_id,"p_project_id":item.project_id,
            "p_generation":item.execution_generation,"p_worker_id":item.lease_owner,
            "p_wave":item.current_wave,"p_issue_number":issue_number,"p_issue_url":issue_url,
            "p_pr_number":pr_number,"p_candidate_commit":candidate_commit,"p_branch":branch,
        })
        if not isinstance(result,dict):
            raise RuntimeError("atomic release preparation returned no result")
        return result

    def finalize_released_run(self,run_id:str,merge_sha:str)->dict:
        if not run_id.strip() or not merge_sha.strip():
            raise ValueError("run id and merge sha are required")
        rows=self._get(
            "factory_change_sets?select=id,status,metadata,release_run_id"
            "&release_run_id=eq."+quote(run_id)+"&limit=1"
        )
        if not rows:
            return {"matched":False,"status":"not_change_set"}
        row=rows[0]
        change_set_id=str(row["id"])
        status=str(row.get("status") or "")
        if status=="completed":
            return {"matched":True,"change_set_id":change_set_id,"status":"completed","idempotent":True}
        if status!="ci_pending":
            raise RuntimeError(f"released Change Set has incompatible status: {status or 'missing'}")
        metadata=dict(row.get("metadata") or {})
        metadata["release"]={"run_id":run_id,"merge_sha":merge_sha,"observed":True}
        updated=self._patch(
            "factory_change_sets?id=eq."+quote(change_set_id)+"&status=eq.ci_pending",
            {"status":"completed","metadata":metadata},
        )
        if updated:
            return {"matched":True,"change_set_id":change_set_id,"status":"completed","idempotent":False}
        current=self._get(
            "factory_change_sets?select=id,status&release_run_id=eq."+quote(run_id)+"&limit=1"
        )
        if current and str(current[0].get("status") or "")=="completed":
            return {"matched":True,"change_set_id":change_set_id,"status":"completed","idempotent":True}
        raise RuntimeError("Change Set release finalization lost its conditional update")
