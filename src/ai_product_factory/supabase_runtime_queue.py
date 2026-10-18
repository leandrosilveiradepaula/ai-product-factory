from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from urllib.parse import quote

from .runtime_worker import RuntimeQueue, StageEvidence, WorkItem
from .agent_scheduler import AgentProfile
from .project_brain import build_project_brain_graph
from .traceability import build_requirement_trace
from .definition_of_done import compile_definition_of_done
from .execution_team_planner import build_execution_team_plan
from .supabase_server import resolve_supabase_server_config
from .github_rest import GitHubRestAdapter
from .pinned_nonproduction_target import PinnedNonproductionTarget


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

    def assert_execution_epoch(self, item: WorkItem) -> None:
        if type(item.execution_generation) is not int or item.execution_generation < 1:
            raise RuntimeError("missing project execution generation; refusing side effects")
        if not item.worker_id:
            raise RuntimeError("missing claimed worker identity")
        self._rpc("factory_assert_claimed_run_epoch",{
            "p_project_id":item.project_id,
            "p_generation":item.execution_generation,
            "p_run_id":item.run_id,
            "p_worker_id":item.worker_id,
        })

    def _reconciliation_context(self, project_id: str, original: dict) -> dict:
        """Resolve an existing project's *durable* snapshot after a claimed run.

        This is strictly scoped to the claimed project. Historical verification
        events (e.g. browser-only observations) are not a full project baseline.
        Database-read failure or absent evidence must NOT fabricate a snapshot:
        the ProductStageExecutor will reject before making a model call.
        """
        context = dict(original)
        project_ref = quote(project_id, safe="")
        if not isinstance(context.get("state_snapshot"), dict):
            try:
                rows = self._get(
                    "factory_project_state_snapshots?"
                    "select=id,observed_stage,summary,evidence,gaps,constraints,source_status,created_at"
                    "&project_id=eq." + project_ref
                    + "&observed_stage=neq.verification&order=created_at.desc&limit=6"
                )
            except (RuntimeError, ValueError, TypeError):
                rows = []
            if isinstance(rows, list):
                for row in rows[:6]:
                    if not isinstance(row, dict):
                        continue
                    # Recheck the returned stage, even when SQL was filtered:
                    # a mocked/corrupted response must not promote a browser-only
                    # verification record into a durable project baseline.
                    if row.get("observed_stage") == "verification":
                        continue
                    summary = row.get("summary")
                    evidence = row.get("evidence")
                    source_status = row.get("source_status")
                    if not isinstance(summary, str) or not summary.strip():
                        continue
                    if not (
                        (isinstance(evidence, (dict, list)) and bool(evidence))
                        or (isinstance(source_status, dict) and bool(source_status))
                    ):
                        continue
                    snapshot = {
                        "snapshot_id": row.get("id"),
                        "observed_stage": row.get("observed_stage"),
                        "recorded_at": row.get("created_at"),
                        "summary": summary,
                        "evidence": evidence if isinstance(evidence, (dict, list)) else [],
                        "gaps": row.get("gaps") if isinstance(row.get("gaps"), (dict, list)) else [],
                        "constraints": row.get("constraints") if isinstance(row.get("constraints"), (dict, list)) else [],
                        "source_status": source_status if isinstance(source_status, dict) else {},
                        "provenance": "historical_control_plane_snapshot_not_live_github",
                    }
                    # A single product prompt must not absorb an unbounded audit payload.
                    if len(json.dumps(snapshot, ensure_ascii=False).encode("utf-8")) <= 32768:
                        context["state_snapshot"] = snapshot
                        break

        # Current Control Plane task statuses take precedence over historical
        # 'known_pending' guesses. App capabilities retain their verification
        # timestamp and are *not* proof of the present GitHub PR head.
        facts = {"source": "durable_control_plane_not_live_github"}
        try:
            tasks = self._get(
                "factory_tasks?select=external_key,title,status,updated_at"
                "&project_id=eq." + project_ref
                + "&order=created_at.desc&limit=24"
            )
        except (RuntimeError, ValueError, TypeError):
            tasks = None
        if isinstance(tasks, list):
            facts["recent_tasks"] = [
                {
                    "external_key": row.get("external_key"),
                    "title": row.get("title"),
                    "status": row.get("status"),
                    "updated_at": row.get("updated_at"),
                }
                for row in tasks[:24]
                if isinstance(row, dict) and isinstance(row.get("status"), str)
            ]
        try:
            access = self._get(
                "factory_project_github_access?"
                "select=status,repository,observed_capabilities,last_verified_at"
                "&project_id=eq." + project_ref + "&limit=1"
            )
        except (RuntimeError, ValueError, TypeError):
            access = None
        if isinstance(access, list) and len(access) == 1 and isinstance(access[0], dict):
            row = access[0]
            facts["github_access"] = {
                "status": row.get("status"),
                "repository": row.get("repository"),
                "observed_capabilities": row.get("observed_capabilities")
                    if isinstance(row.get("observed_capabilities"), dict) else {},
                "last_verified_at": row.get("last_verified_at"),
                "live_github_head_verified": False,
            }
        context["current_state_facts"] = facts
        return context

    def _live_candidate_context(self, project_id: str, context: dict) -> dict:
        """Read live candidate evidence before paid reconciliation; no GitHub writes."""
        rows = self._get(
            "factory_projects?select=id,repository,project_kind,manifest"
            "&id=eq." + quote(project_id, safe="") + "&limit=1"
        )
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise PermissionError("reconciliation requires exact durable project identity")
        project = rows[0]
        if project.get("project_kind") != "existing":
            raise PermissionError("live candidate reconciliation requires an existing project")
        repo = project.get("repository")
        manifest = project.get("manifest")
        target = PinnedNonproductionTarget.parse(
            manifest.get("delivery_target") if isinstance(manifest, dict) else None,
            repository=repo,
        )
        github = GitHubRestAdapter(repository=repo)
        target.verify(github)
        main_sha = github.get_branch_sha("main")
        governance = {}
        for path in ("AGENTS.md", "docs/codex/CURRENT_TASK.md"):
            text = github.get_file_text(path, ref=target.sha)
            if not text.strip() or len(text.encode("utf-8")) > 65536:
                raise PermissionError("repository governance missing or oversized")
            governance[path] = text
        candidate = {
            "repository": repo,
            "pr_number": target.candidate_pr_number,
            "branch": target.branch,
            "sha": target.sha,
            "main_sha": main_sha,
            "observed_from": "live_github_app_exact_candidate",
            "governance": governance,
        }
        enriched = dict(context)
        facts = dict(enriched.get("current_state_facts") or {})
        facts["live_candidate"] = candidate
        enriched["current_state_facts"] = facts
        return enriched

    def claim_next(self, worker_id: str) -> WorkItem | None:
        if not isinstance(worker_id,str) or not worker_id.strip():
            raise ValueError("worker id is required")
        data=self._rpc("factory_claim_next_run",{"p_worker_id":worker_id})
        if data is None: return None
        if not isinstance(data,dict):
            raise RuntimeError("claim RPC returned an invalid response")
        stages=data.get("stages")
        if not isinstance(stages,list) or not stages or not all(isinstance(stage,str) and stage.strip() and stage==stage.strip() for stage in stages):
            raise RuntimeError("claim RPC returned invalid stages")
        if len(stages)!=len(set(stages)):
            raise RuntimeError("claim RPC returned duplicate stages")
        if not isinstance(data.get("context",{}),dict):
            raise RuntimeError("claim RPC returned invalid context")
        if not all(isinstance(data.get(key),str) and data[key].strip() for key in ("run_id","task_id","project_id","project_key")):
            raise RuntimeError("claim RPC returned invalid identifiers")
        if type(data.get("execution_generation")) is not int or data["execution_generation"] < 1:
            raise RuntimeError("claim RPC returned invalid execution generation")
        context = data.get("context", {})
        if "reconciliation" in stages:
            context = self._reconciliation_context(data["project_id"], context)
            context = self._live_candidate_context(data["project_id"], context)
        return WorkItem(run_id=data["run_id"],task_id=data["task_id"],project_id=data["project_id"],project_key=data["project_key"],stages=tuple(stages),context=context,execution_generation=data.get("execution_generation"),worker_id=worker_id)

    def record_stage_event(self,item:WorkItem,stage:str,status:str)->None:
        if status not in {"started","failed"}:
            raise ValueError("unsupported runtime stage event status")
        if not isinstance(stage,str) or not stage.strip():
            raise ValueError("invalid stage name")
        self.assert_execution_epoch(item)
        self._rpc("factory_record_runtime_stage",{
            "p_run_id":item.run_id,"p_stage":stage,"p_status":status,"p_output":{}
        })

    def record_stage(self,item:WorkItem,evidence:StageEvidence)->None:
        if evidence.status != "completed":
            raise ValueError("only completed stage evidence may be persisted")
        if not isinstance(evidence.stage,str) or not evidence.stage.strip():
            raise ValueError("invalid stage name")
        if not isinstance(evidence.output,dict):
            raise ValueError("stage output must be a mapping")
        self.assert_execution_epoch(item)
        self._rpc("factory_record_runtime_stage",{"p_run_id":item.run_id,"p_stage":evidence.stage,"p_status":evidence.status,"p_output":evidence.output})
        persisted=self._rpc("factory_persist_product_stage",{"p_run_id":item.run_id,"p_stage":evidence.stage,"p_output":evidence.output}) or {}
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
            decision_gate_pending=bool(persisted.get("human_gate_id"))
            team_plan=evidence.output.get("_team_plan")
            if isinstance(team_plan,dict) and not decision_gate_pending:
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
        self.assert_execution_epoch(item)
        self._rpc("factory_finish_run",{"p_run_id":item.run_id,"p_status":"completed","p_error":None})

    def fail(self,item:WorkItem,error:str)->None:
        self.assert_execution_epoch(item)
        self._rpc("factory_finish_run",{"p_run_id":item.run_id,"p_status":"failed","p_error":error[:2000]})
