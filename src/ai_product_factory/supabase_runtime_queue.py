from __future__ import annotations

import json
import os
import re
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
from .source_scope_admission import SourceScopeBlocked
from .planning_replay_guard import PlanningReplayBlocked, find_same_source_empty_planning
from .candidate_source_evidence import (
    collect_candidate_source_evidence,
    latest_authorization_excerpt,
    source_issue_scope_alignment,
)
from .product_stage_output_contract import (
    assert_executed_product_stage_output, NON_ACTIONABLE_PLANNING_EVIDENCE,
)
from .journey_delivery_binding import JourneyBinding, JourneyBindingBlocked


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

    def bind_journey_source_v2(self, *, project_key: str, request_id: str,
                               expected_generation: int, expected_policy_version: int,
                               binding: dict) -> dict:
        """Commit an already GitHub-verified V2 binding; never creates it from text."""
        from uuid import UUID
        if not isinstance(project_key, str) or not project_key.strip():
            raise ValueError("project key is required")
        try:
            UUID(request_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("request id is invalid") from exc
        if type(expected_generation) is not int or expected_generation < 1 or type(expected_policy_version) is not int or expected_policy_version < 1:
            raise ValueError("journey binding epoch is invalid")
        if not isinstance(binding, dict):
            raise ValueError("journey binding is required")
        result = self._rpc("factory_bind_journey_source_v2", {
            "p_project_key": project_key, "p_request_id": request_id,
            "p_expected_generation": expected_generation,
            "p_expected_policy_version": expected_policy_version, "p_binding": binding,
        })
        if not isinstance(result, dict) or result.get("state") != "source_bound":
            raise RuntimeError("journey source binding receipt is invalid")
        return result

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
        # Preserve the exact release's global-readiness obligations when
        # preparing a later, independently authorized continuation. This is
        # passive evidence, never a worker claim or paid-model authorization.
        from .post_release_readiness import observe_manifest_release
        manifest = context.get("manifest")
        followup = observe_manifest_release(
            get=self._get, project_id=project_id, manifest=manifest
        )
        if followup is not None:
            facts["global_product_readiness"] = followup
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
        repo = project.get("repository")
        manifest = project.get("manifest")
        if project.get("project_kind") == "platform":
            # Platform products (including the Factory itself) use an exact
            # GitHub main snapshot. The CRM-only open Preview PR target must
            # never be invented or imposed on these projects.
            from .platform_source_context import live_platform_source_context
            if not isinstance(repo, str) or "/" not in repo:
                raise PermissionError("platform reconciliation has no repository identity")
            github = GitHubRestAdapter(repository=repo)
            return live_platform_source_context(project=project, context=context, github=github)
        if project.get("project_kind") == "greenfield":
            from .greenfield_source_context import live_greenfield_source_context
            if not isinstance(repo, str) or "/" not in repo:
                raise PermissionError("greenfield reconciliation has no repository identity")
            if (not isinstance(manifest, dict)
                or manifest.get("source") != "factory-console"
                or manifest.get("onboarding_mode") != "greenfield"
                or not isinstance(manifest.get("continuation_request"), dict)
                or manifest["continuation_request"].get("source") != "github-owner"):
                raise PermissionError("greenfield source provenance unavailable")
            github = GitHubRestAdapter(repository=repo)
            return live_greenfield_source_context(
                project=project, context=context, github=github,
            )
        if project.get("project_kind") != "existing":
            raise PermissionError("live candidate reconciliation requires an existing or platform project")
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
        request = (
            manifest.get("continuation_request", {}).get("summary")
            if isinstance(manifest.get("continuation_request"), dict)
            else None
        )
        alignment = source_issue_scope_alignment(
            governance["docs/codex/CURRENT_TASK.md"], request, repository=repo,
        )
        if alignment["status"] == "conflict":
            # An OWNER Start does not override a different repository write
            # authorization. This preflight happens before any paid stage.
            raise SourceScopeBlocked("source_authorization_issue_mismatch")
        active_task = latest_authorization_excerpt(governance["docs/codex/CURRENT_TASK.md"])
        if active_task is not None and len(active_task.encode("utf-8")) > 16000:
            raise SourceScopeBlocked("source_active_scope_oversized")
        # Full CURRENT_TASK was fetched at the exact SHA. Historical tasks
        # should not become new model priorities or increase paid prompt cost.
        model_governance = {
            **governance,
            "docs/codex/CURRENT_TASK.md": (
                "# Latest authorized task only; older sections are historical.\n"
                + (active_task or "No recognized authorization: do not infer write scope.")
            ),
        }
        source_evidence = collect_candidate_source_evidence(
            governance["docs/codex/CURRENT_TASK.md"], github, sha=target.sha,
            continuation_request=request,
        )
        candidate = {
            "repository": repo,
            "pr_number": target.candidate_pr_number,
            "branch": target.branch,
            "sha": target.sha,
            "main_sha": main_sha,
            "observed_from": "live_github_app_exact_candidate",
            "verified_open_pr": {
                "state": "open", "base_ref": "main", "head_ref": target.branch,
                "head_sha": target.sha, "verified": True,
            },
            "governance": model_governance,
            "governance_selection": "exact_sha_latest_authorized_section_only",
            "source_evidence": source_evidence,
        }
        enriched = dict(context)
        facts = dict(enriched.get("current_state_facts") or {})
        access = facts.get("github_access")
        if isinstance(access, dict):
            facts["github_access"] = {
                **access, "live_github_head_verified": True,
                "verified_candidate_sha": target.sha,
            }
        facts["live_candidate"] = candidate
        enriched["current_state_facts"] = facts
        return enriched


    def _planning_resume_context(
        self, run_id: str, task_id: str, project_id: str,
        epoch: int, original: dict,
    ) -> dict:
        """Hydrate verified same-run paid stages without calling the provider.

        A durable retry receipt by itself is insufficient: compare the immutable
        source and snapshot with live project state on the claimed epoch.
        """
        import uuid
        def valid_uuid(value):
            if not isinstance(value, str):
                return False
            try:
                return str(uuid.UUID(value)) == value
            except ValueError:
                return False

        claimed = self._get(
            "factory_runs?select=id,task_id,status,metadata"
            "&id=eq." + quote(run_id,safe="") + "&limit=2"
        )
        if (not isinstance(claimed,list) or len(claimed)!=1
                or claimed[0].get("id")!=run_id
                or claimed[0].get("task_id")!=task_id
                or claimed[0].get("status")!="running"):
            raise PermissionError("planning resume claim cannot be verified")
        md=claimed[0].get("metadata")
        if not isinstance(md,dict):
            raise PermissionError("planning resume metadata invalid")
        proof=md.get("resume_checkpoint")
        if proof is None:
            return original  # Ordinary planning-only runs are unchanged.
        source_id=proof.get("source_run_id") if isinstance(proof,dict) else None
        snapshot_id=proof.get("snapshot_id") if isinstance(proof,dict) else None
        if (not isinstance(proof,dict)
                or proof.get("schema")!="checkpointed_product_planning_v1"
                or not valid_uuid(source_id) or not valid_uuid(snapshot_id)
                or proof.get("project_id")!=project_id
                or type(proof.get("source_generation")) is not int
                or proof["source_generation"]!=epoch
                or md.get("execution_generation")!=epoch
                or md.get("stages")!=["planning"]
                or not isinstance(proof.get("request_id"),str)
                or md.get("continuation_request_id")!=proof["request_id"]
                or not isinstance(proof.get("reconciliation"),dict)
                or not isinstance(proof.get("gap_analysis"),dict)):
            raise PermissionError("planning resume checkpoint identity invalid")
        source = self._get(
            "factory_runs?select=id,task_id,status,execution_route,metadata"
            "&id=eq." + quote(source_id,safe="") + "&limit=2"
        )
        if (not isinstance(source,list) or len(source)!=1
                or source[0].get("id")!=source_id
                or source[0].get("task_id")!=task_id
                or source[0].get("status")!="failed"
                or source[0].get("execution_route")!="direct"):
            raise PermissionError("planning resume source identity invalid")
        source_md=source[0].get("metadata")
        if (not isinstance(source_md,dict)
                or source_md.get("error")!="reserved provider cost exceeds remaining budget"
                or source_md.get("stages")!=["reconciliation","gap_analysis","planning"]
                or str(source_md.get("execution_generation"))!=str(epoch)
                or source_md.get("continuation_request_id")!=proof["request_id"]):
            raise PermissionError("planning resume source stages invalid")
        snaps=self._get(
            "factory_project_state_snapshots?select="
            "id,run_id,project_id,observed_stage,summary,evidence,gaps,"
            "constraints,source_status"
            "&id=eq." + quote(snapshot_id,safe="")
            + "&project_id=eq." + quote(project_id,safe="")
            + "&run_id=eq." + quote(source_id,safe="")
            + "&limit=2"
        )
        if (not isinstance(snaps,list) or len(snaps)!=1
                or snaps[0].get("id")!=snapshot_id
                or snaps[0].get("run_id")!=source_id
                or snaps[0].get("project_id")!=project_id
                or snaps[0].get("observed_stage")=="verification"):
            raise PermissionError("planning resume snapshot identity invalid")
        snap=snaps[0]
        expected={key:snap.get(key) for key in (
            "summary","observed_stage","evidence","gaps","constraints","source_status"
        )}
        if (expected!=proof["reconciliation"]
                or not isinstance(expected["summary"],str)
                or not expected["summary"].strip()
                or not (
                    isinstance(expected["evidence"],(dict,list)) and bool(expected["evidence"])
                    or isinstance(expected["source_status"],dict) and bool(expected["source_status"])
                )):
            raise PermissionError("planning resume reconciliation checkpoint drift")
        project=self._get(
            "factory_projects?select=id,manifest"
            "&id=eq." + quote(project_id,safe="") + "&limit=2"
        )
        if (not isinstance(project,list) or len(project)!=1
                or project[0].get("id")!=project_id
                or not isinstance(project[0].get("manifest"),dict)):
            raise PermissionError("planning resume project identity invalid")
        manifest=project[0]["manifest"]
        if (manifest.get("gap_analysis")!=proof["gap_analysis"]
                or original.get("manifest")!=manifest
                or not isinstance(manifest.get("continuation_request"),dict)
                or manifest["continuation_request"].get("id")!=proof["request_id"]
                or manifest["continuation_request"].get("source") not in (
                    "factory-console","github-owner"
                )
                or len(str(proof["gap_analysis"]))>262144
                or not isinstance(proof["gap_analysis"].get("recommended_next_work"),list)
                or len(proof["gap_analysis"]["recommended_next_work"])<1):
            raise PermissionError("planning resume gap analysis changed or missing")
        context=dict(original)
        context["_verified_resume_prior_stages"]={
            "reconciliation":proof["reconciliation"],
            "gap_analysis":proof["gap_analysis"],
        }
        context["_verified_resume_origin"]={
            "source_run_id":source_id,"snapshot_id":snapshot_id,
            "request_id":proof["request_id"],"generation":epoch,
        }
        return context

    def _reject_repeat_empty_planning(self, *, run_id: str, task_id: str, context: dict) -> None:
        """Read-only proof of an identical prior failed paid plan, before model."""
        origin=context.get("_verified_resume_origin")
        if not isinstance(origin,dict):
            return
        facts=context.get("current_state_facts")
        live=facts.get("live_candidate") if isinstance(facts,dict) else None
        sha=live.get("sha") if isinstance(live,dict) else None
        manifest=context.get("manifest")
        current=manifest.get("continuation_request") if isinstance(manifest,dict) else None
        if not isinstance(sha,str) or not re.fullmatch(r"[0-9a-f]{40}",sha):
            return  # Original source admission owns source SHA, no guess.
        if not isinstance(current,dict):
            return
        if not isinstance(task_id,str) or not re.fullmatch(r"[0-9a-f-]{36}",task_id):
            raise PermissionError("planning replay task identity invalid")
        rows=self._get(
            "factory_runs?select=id,task_id,status,metadata"
            "&task_id=eq."+quote(task_id,safe="")
            +"&status=eq.failed&order=created_at.desc&limit=40"
        )
        if find_same_source_empty_planning(
            rows,current_run_id=run_id,task_id=task_id,
            origin=origin,current_commit=sha,current_request=current,
        ):
            raise PlanningReplayBlocked()

    def _v2_journey_context(self, *, run_id: str, project_id: str, context: dict) -> tuple[str | None, dict]:
        """Load the immutable binding for a claimed V2 run before any stage.

        The claim RPC is intentionally generic for legacy compatibility. This
        second server-side read makes a missing/cross-project V2 binding fail
        before reconciliation or a model invocation, never by consulting the
        mutable project manifest.
        """
        manifest = context.get("manifest")
        enabled = (isinstance(manifest, dict) and isinstance(manifest.get("journey_delivery_binding_v2"), dict)
                   and manifest["journey_delivery_binding_v2"].get("enabled") is True)
        if not enabled:
            return None, context
        runs = self._get("factory_runs?select=journey_id&id=eq." + quote(run_id, safe="") + "&limit=1")
        if not isinstance(runs, list) or len(runs) != 1:
            raise JourneyBindingBlocked("journey_claim_unverifiable")
        journey_id = runs[0].get("journey_id")
        if journey_id is None:
            return None, context
        if not isinstance(journey_id, str):
            raise JourneyBindingBlocked("journey_claim_identity_invalid")
        projects = self._get("factory_projects?select=repository&id=eq." + quote(project_id, safe="") + "&limit=1")
        if not isinstance(projects, list) or len(projects) != 1 or not isinstance(projects[0], dict):
            raise JourneyBindingBlocked("journey_project_unverifiable")
        repository = projects[0].get("repository")
        rows = self._get(
            "factory_journeys?select=id,project_id,request_id,state,binding,execution_generation"
            "&id=eq." + quote(journey_id, safe="") + "&limit=1"
        )
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise JourneyBindingBlocked("journey_claim_unverifiable")
        row = rows[0]
        if row.get("id") != journey_id or row.get("project_id") != project_id:
            raise JourneyBindingBlocked("journey_binding_cross_project")
        if row.get("state") not in ("source_bound", "executing"):
            raise JourneyBindingBlocked("journey_not_executable")
        binding = JourneyBinding.parse(row.get("binding"), project_id=project_id,
                                       request_id=str(row.get("request_id") or ""),
                                       repository=str(repository or ""))
        if row.get("execution_generation") != binding.execution_generation:
            raise JourneyBindingBlocked("journey_binding_generation_invalid")
        return journey_id, {**context, "journey_binding_v2": binding.as_context()}

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
        try:
            journey_id, context = self._v2_journey_context(
                run_id=data["run_id"], project_id=data["project_id"], context=context,
            )
        except JourneyBindingBlocked as exc:
            claimed=WorkItem(run_id=data["run_id"],task_id=data["task_id"],
                project_id=data["project_id"],project_key=data["project_key"],stages=tuple(stages),
                context={},execution_generation=data["execution_generation"],worker_id=worker_id)
            try:
                self.fail(claimed, "journey_" + str(exc))
            except Exception as settlement_error:
                raise RuntimeError("claimed journey binding failure was not settled") from settlement_error
            raise
        if "reconciliation" in stages:
            try:
                context = self._reconciliation_context(data["project_id"], context)
                context = self._live_candidate_context(data["project_id"], context)
            except Exception as exc:
                # The claim is already durable; RuntimeWorker has no WorkItem
                # if this context preparation raises. Settle it with the
                # existing epoch-fenced failure RPC before propagating.
                if isinstance(exc, SourceScopeBlocked):
                    # Do not persist provider responses, issue content or paths
                    # in the run error. The fixed reason code is actionable.
                    reason = "reconciliation_" + exc.code
                elif (isinstance(exc, PermissionError)
                      and str(exc) == "candidate branch moved; reconcile exact SHA before writing"):
                    reason = "reconciliation_source_candidate_sha_drift"
                else:
                    reason = "reconciliation_context_preflight_failed"
                claimed = WorkItem(
                    run_id=data["run_id"], task_id=data["task_id"],
                    project_id=data["project_id"], project_key=data["project_key"],
                    stages=tuple(stages), context={},
                    execution_generation=data["execution_generation"],
                    worker_id=worker_id,
                )
                try:
                    self.fail(claimed, reason)
                except Exception as settlement_error:
                    raise RuntimeError(
                        "claimed reconciliation preflight failed and durable "
                        "failure settlement was not confirmed"
                    ) from settlement_error
                raise
        if stages==["planning"]:
            try:
                context=self._planning_resume_context(
                    data["run_id"],data["task_id"],data["project_id"],
                    data["execution_generation"],context,
                )
                if "_verified_resume_prior_stages" in context:
                    # Recheck the pinned nonproduction candidate using GETs;
                    # a moved branch must not enter a new paid planning call.
                    context=self._live_candidate_context(data["project_id"],context)
                    self._reject_repeat_empty_planning(
                        run_id=data["run_id"],task_id=data["task_id"],context=context,
                    )
            except Exception as exc:
                claimed=WorkItem(
                    run_id=data["run_id"],task_id=data["task_id"],
                    project_id=data["project_id"],project_key=data["project_key"],
                    stages=tuple(stages),context={},
                    execution_generation=data["execution_generation"],
                    worker_id=worker_id,
                )
                reason = (
                    exc.code if isinstance(exc, PlanningReplayBlocked)
                    else "planning_resume_" + exc.code
                    if isinstance(exc, SourceScopeBlocked)
                    else "planning_resume_provenance_preflight_failed"
                )
                try:
                    self.fail(claimed,reason)
                except Exception as settlement_error:
                    raise RuntimeError(
                        "claimed planning resume preflight failed and durable "
                        "failure settlement was not confirmed"
                    ) from settlement_error
                raise PermissionError("planning resume provenance invalid") from None
        return WorkItem(run_id=data["run_id"],task_id=data["task_id"],project_id=data["project_id"],project_key=data["project_key"],stages=tuple(stages),context=context,execution_generation=data.get("execution_generation"),worker_id=worker_id,journey_id=journey_id)

    def record_stage_event(self,item:WorkItem,stage:str,status:str)->None:
        if status not in {"started","failed"}:
            raise ValueError("unsupported runtime stage event status")
        if not isinstance(stage,str) or not stage.strip():
            raise ValueError("invalid stage name")
        self.assert_execution_epoch(item)
        self._rpc("factory_record_runtime_stage",{
            "p_run_id":item.run_id,"p_stage":stage,"p_status":status,"p_output":{}
        })

    def record_non_actionable_planning(self,item:WorkItem)->None:
        """Store fixed evidence of an empty *paid* plan, not arbitrary model text."""
        if "planning" not in item.stages:
            raise ValueError("only a claimed planning stage may record this diagnostic")
        self.assert_execution_epoch(item)
        output=dict(NON_ACTIONABLE_PLANNING_EVIDENCE)
        facts=item.context.get("current_state_facts")
        live=facts.get("live_candidate") if isinstance(facts,dict) else None
        sha=live.get("sha") if isinstance(live,dict) else None
        if isinstance(sha,str) and re.fullmatch(r"[0-9a-f]{40}",sha):
            output["assessed_commit"]=sha
        self._rpc("factory_record_runtime_stage",{
            "p_run_id":item.run_id,
            "p_stage":"planning",
            "p_status":"failed",
            "p_output":output,
        })

    def record_stage(self,item:WorkItem,evidence:StageEvidence)->None:
        if evidence.status != "completed":
            raise ValueError("only completed stage evidence may be persisted")
        if not isinstance(evidence.stage,str) or not evidence.stage.strip():
            raise ValueError("invalid stage name")
        if not isinstance(evidence.output,dict):
            raise ValueError("stage output must be a mapping")
        # Keep the durable adapter fail-closed even if a caller bypasses
        # RuntimeWorker and constructs StageEvidence directly.
        assert_executed_product_stage_output(evidence.output)
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
