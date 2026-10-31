from __future__ import annotations

import json
from dataclasses import dataclass

from .model_executor import ModelExecutor, ModelRequest
from .models import ExecutionRoute
from .product_stage_output_contract import (
    assert_executed_product_stage_output, PlanningNoActionableWork,
)
from .runtime_worker import WorkItem
from .agent_scheduler import AgentProfile
from .execution_team_planner import build_execution_team_plan, _canonical_routing_task, _choose_agent, _execution_lane


@dataclass(frozen=True)
class ProductStagePrompts:
    discovery: str = "Structure the product discovery from the approved intake. Return JSON only with problem, users, outcomes, assumptions, open_questions, risks."
    specification: str = "Create an implementable product specification. Return JSON only with scope, user_flows, requirements, non_functional_requirements, acceptance_criteria, exclusions, assumptions."
    reconciliation: str = "Reconcile the existing project from the durable state snapshot, approved intake, and deterministic current_state_facts. Return JSON only with observed_stage, summary, evidence, gaps, constraints, source_status. Preserve confirmed work and do not claim repository checks that are absent from the supplied evidence. When current_state_facts conflict with older intake or snapshot state, treat current_state_facts as the newer operational evidence. A completed/cancelled/failed task is not active work. Verified GitHub capabilities in current_state_facts must not be reported as unverified. Treat intake_spec known_pending and other historical pending labels as unverified historical references only: never call them active work, create a business-priority decision from them, or require a human to resolve their status unless current_state_facts or other supplied current evidence independently confirms they are still active."
    gap_analysis: str = "Compare the reconciled existing-project state with the continuation brief and constraints. Return JSON only with completed, gaps, risks, decisions_needed, recommended_next_work. Do not invent missing evidence or business decisions."
    planning: str = "Return explicit tasks array for implementation, or decisions_needed for a real unresolved product/scope decision. If neither exists, return tasks=[] and decisions_needed=[] rather than inventing work: runtime will report non-actionable planning, never a completed development run. Use current_state_facts.live_candidate.verified_open_pr and source_evidence for exact-SHA repository facts. For tasks combining implementation or UI changes with unit tests, tests/regression are acceptance deliverables, not independent required_capabilities: route to one write-capable development or ui agent using capabilities from execution_registry, and put independent QA checks in specialist_reviews. If preferred_agent_role is omitted, choose an actual active write-capable builder role; never mix unrelated builder and specialist capabilities in a single task. Do not invent additional capability labels. Inspect the supplied authorized code snippets and test snippets before choosing a change; historical CURRENT_TASK and open issue descriptions are not proof a defect remains. When a scoped defect is visibly supported by the current code and not covered by existing tests, create a concrete implementation task within that scope. An existing deployed RPC call is not a request to introduce a new SQL RPC: a no-new-RPC constraint forbids creating or modifying database functions, not preserving an existing invocation. Resolve such current-code versus historical-task ambiguity autonomously; do not ask a human for scope authorization merely to retain existing behavior. A scope decision is warranted only if the proposed change genuinely exceeds authorized files, data access, permissions or requirements. Do not require working-tree status before planning (that is checked at worker checkout), and do not confuse a verified remote PR head with unverified CI, Preview, or release. If all inspected scope is implemented, state the remaining evidence gaps instead of inventing code work. If current_state_facts.global_product_readiness exists, treat it as an evidence obligation from a prior release: never interpret the candidate release as global product completion, never create implementation tasks merely because an audit domain is unassessed, and never turn previously completed tasks into new work. Correlate pending readiness dimensions with concrete current repository gaps; put verification-only work in test_strategy or specialist_reviews, and propose executable builder tasks only for substantiated missing functionality or defects inside the operator-requested scope. Create an actionable engineering plan. Return JSON only with architecture, workstreams, tasks, specialist_reviews, dependencies, test_strategy, release_strategy, risks, decisions_needed. The tasks array is strictly pre-PR implementation work and must contain only work executable by a write-capable builder profile from execution_registry (normally development or ui). Do not create product/reconciliation/planning tasks: resolve analysis from supplied evidence in this response. Do not create Security, QA, Operations, CI, Preview, deployment, or human-release tasks in tasks; list required post-candidate specialist roles in specialist_reviews using only security, qa, operations. Human approval/release is always a later gate, never a planning decision or task. If manifest.human_decisions contains human-approved answers to an earlier planning gate, treat those answers as authoritative product constraints. Continue from the existing manifest.engineering_plan, preserve stable task keys and accepted requirements when possible, and never re-ask an already answered decision unless new evidence reveals an actual contradiction. If a genuine current human decision is unresolved, put it in decisions_needed and do not make implementation depend on an invented executable task. Each decisions_needed item must be an object with decision_key, decision_kind, question, why_needed, and suggested_response. question, why_needed, and suggested_response must be concise, user-facing Brazilian Portuguese (pt-BR). suggested_response is an advisory draft only: it must preserve least privilege, stay within the supplied user intent, never claim approval already happened, and remain safe for the human to edit before explicitly approving. Avoid internal identifiers and implementation jargon in the question. A business_priority decision must also include candidate_work_keys with at least two external_key values that are currently active in current_state_facts.recent_tasks; historical references and terminal tasks are forbidden candidates. decision_kind must be one of product_requirement, scope_authorization, business_priority. Never ask a human to confirm repository facts, CI/readiness state, credentials/capabilities, already-closed work, or future production/release approval in decisions_needed; resolve supplied evidence autonomously or report a technical blocker outside decisions_needed. Every task must include task_key (stable short identifier), acceptance_criteria (non-empty array of independently verifiable outcomes), required_capabilities, scope_keys, depends_on, and may include preferred_agent_role and context_paths. scope_keys may be semantic when repository paths are not yet known, but prefer explicit repository-relative paths or prefixes when supported by supplied evidence. context_paths, when known, must contain repository-relative existing files that should be read before implementation; never invent a path not supported by supplied evidence. task_key values must be unique. depends_on may contain only task_key values from other tasks in this same output; never put decisions, gates, approvals, credentials, or external conditions in depends_on. Every task must be ownable by one write-capable builder profile. Each scope_keys item must be a repository-relative exact path or recognized concise semantic identifier; NEVER append prose to a path (for example 'somente se' or 'testes relacionados'). Put conditional requirements only in acceptance_criteria. For tests use an explicit, narrowly co-located test filename such as src/lib/example.test.ts or src/components/Example.test.tsx, never a descriptive test phrase or a broad repository test root. Do not assume a fixed number of agents."


def _drop_unsubstantiated_business_priorities(output: dict, current_state_facts: dict | None) -> None:
    decisions=output.get("decisions_needed")
    if not isinstance(decisions,list):
        return
    facts=current_state_facts if isinstance(current_state_facts,dict) else {}
    recent_tasks=facts.get("recent_tasks")
    active_statuses={"queued","running","awaiting_human","blocked"}
    active_keys={
        str(task.get("external_key") or "").strip()
        for task in recent_tasks or []
        if isinstance(task,dict)
        and str(task.get("status") or "").strip() in active_statuses
        and str(task.get("external_key") or "").strip()
    }
    kept=[]
    for decision in decisions:
        if not isinstance(decision,dict) or str(decision.get("decision_kind") or "").strip()!="business_priority":
            kept.append(decision)
            continue
        candidates=decision.get("candidate_work_keys")
        candidate_keys={
            str(key).strip() for key in candidates or []
            if str(key).strip()
        } if isinstance(candidates,list) else set()
        if len(candidate_keys)>=2 and candidate_keys.issubset(active_keys):
            kept.append(decision)
    output["decisions_needed"]=kept


def _validate_pre_pr_planning_tasks(output: dict, profiles: tuple[AgentProfile,...]) -> None:
    tasks=output.get("tasks")
    if not isinstance(tasks,list):
        return
    builders=[
        profile for profile in profiles
        if profile.is_active
        and profile.role in {"development","ui"}
        and "github_write" in set(profile.allowed_tools)
    ]
    task_keys=[]
    for task in tasks:
        if not isinstance(task,dict):
            raise ValueError("planning tasks must be JSON objects")
        task_key=str(task.get("task_key") or "").strip()
        if not task_key:
            raise ValueError("planning task requires task_key")
        if task_key in task_keys:
            raise ValueError(f"duplicate planning task_key: {task_key}")
        task_keys.append(task_key)
        routed=_canonical_routing_task(task)
        required={str(x).strip() for x in (routed.get("required_capabilities") or []) if str(x).strip()}
        scopes=task.get("scope_keys")
        if not isinstance(scopes,list) or not any(str(x).strip() for x in scopes):
            raise ValueError(f"planning task requires non-empty scope_keys: {task_key}")
        context_paths=task.get("context_paths")
        if context_paths is not None:
            if not isinstance(context_paths,list):
                raise ValueError(f"planning task context_paths must be an array: {task_key}")
            for raw_path in context_paths:
                path=str(raw_path).strip().replace("\\","/").removeprefix("./")
                if not path or path.startswith("/") or path.startswith("../") or "/../" in path:
                    raise ValueError(f"planning task has invalid context path: {task_key}")
        preferred=str(routed.get("preferred_agent_role") or "").strip()
        agent,blocker=_choose_agent(routed,builders)
        if agent is None or _execution_lane(agent)!="builder":
            # Durable error explains exact routing mismatch, without logging
            # model output, source code, secrets or an entire provider response.
            reason=blocker.get("code") if isinstance(blocker,dict) else "no_builder_lane"
            raise ValueError(
                f"planning task is not executable in a pre-PR builder lane: {task_key}; "
                f"preferred_role={preferred or 'unspecified'}; "
                f"required_capabilities={sorted(required)}; blocker={reason}"
            )
    decisions=output.get("decisions_needed") or []
    if not isinstance(decisions,list):
        raise ValueError("decisions_needed must be an array")
    allowed_decision_kinds={"product_requirement","scope_authorization","business_priority"}
    seen_decision_keys=set()
    for decision in decisions:
        if not isinstance(decision,dict):
            raise ValueError("planning decisions must be JSON objects")
        decision_key=str(decision.get("decision_key") or "").strip()
        decision_kind=str(decision.get("decision_kind") or "").strip()
        question=str(decision.get("question") or "").strip()
        why_needed=str(decision.get("why_needed") or "").strip()
        suggested_response=str(decision.get("suggested_response") or "").strip()
        if not decision_key:
            raise ValueError("planning decision requires decision_key")
        if decision_key in seen_decision_keys:
            raise ValueError(f"duplicate planning decision_key: {decision_key}")
        seen_decision_keys.add(decision_key)
        if decision_kind not in allowed_decision_kinds:
            raise ValueError(f"unsupported planning decision_kind: {decision_kind or '<empty>'}")
        if not question or not why_needed or not suggested_response:
            raise ValueError(f"planning decision requires question, why_needed, and suggested_response: {decision_key}")
    known_task_keys=set(task_keys)
    if not decisions:
        for task in tasks:
            task_key=str(task.get("task_key") or "").strip()
            dependencies=task.get("depends_on") or []
            if not isinstance(dependencies,list):
                raise ValueError(f"planning task depends_on must be an array: {task_key}")
            unknown=[str(dep).strip() for dep in dependencies if str(dep).strip() not in known_task_keys]
            if unknown:
                raise ValueError(
                    f"planning task has unresolved dependency: {task_key} -> {', '.join(unknown)}"
                )
    reviews=output.get("specialist_reviews")
    if reviews is None:
        return
    if not isinstance(reviews,list):
        raise ValueError("specialist_reviews must be an array")
    allowed={"security","qa","operations"}
    invalid=[]
    for review in reviews:
        if isinstance(review,str):
            role=review.strip()
        elif isinstance(review,dict):
            role=str(review.get("role") or "").strip()
        else:
            role=""
        if role not in allowed:
            invalid.append(role or str(review))
    if invalid:
        raise ValueError("unsupported specialist review role: "+", ".join(invalid))


def _verified_greenfield_source_for_reconciliation(context: object) -> bool:
    """Accept exact current read-only greenfield code, never a fake snapshot.

    Caller already re-read project manifest and GitHub source after the
    run was atomically claimed. This guard independently rejects malformed
    current-state evidence before any paid Product Stage invocation.
    """
    import re

    if not isinstance(context, dict):
        return False
    manifest = context.get("manifest")
    facts = context.get("current_state_facts")
    if not isinstance(manifest, dict) or not isinstance(facts, dict):
        return False
    owner = manifest.get("continuation_request")
    if (manifest.get("source") != "factory-console"
        or manifest.get("onboarding_mode") != "greenfield"
        or not isinstance(manifest.get("bootstrap_request_id"), str)
        or not isinstance(owner, dict)
        or owner.get("source") != "github-owner"
        or not isinstance(owner.get("github"), dict)
        or owner["github"].get("repository") != "leandrosilveiradepaula/ai-product-factory"
        or owner["github"].get("issue_number") != 1055
        or owner["github"].get("actor_id") != 256917842):
        return False

    candidate = facts.get("live_candidate")
    if not isinstance(candidate, dict):
        return False
    sha = candidate.get("sha")
    if (candidate.get("observed_from") != "live_greenfield_main_exact_sha"
        or candidate.get("branch") != "main"
        or not isinstance(sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", sha) is None
        or candidate.get("main_sha") != sha
        or candidate.get("verified_open_pr", False) is not None):
        return False
    governance = candidate.get("governance")
    if (not isinstance(governance, dict)
        or not all(isinstance(governance.get(k), str) and governance[k].strip()
                   for k in ("README.md", "package.json"))):
        return False

    source = candidate.get("source_evidence")
    if (not isinstance(source, dict)
        or source.get("status") != "bounded_source_inspected"
        or source.get("assessed_commit") != sha):
        return False
    files = source.get("inspected_files")
    if (not isinstance(files, list) or not 1 <= len(files) <= 4
        or not all(
            isinstance(f, dict)
            and isinstance(f.get("path"), str)
            and isinstance(f.get("content"), str)
            and bool(f["content"].strip())
            and f.get("assessed_commit") == sha
            for f in files)):
        return False
    return True


class ProductStageExecutor:
    """Executes product/reconciliation stages through the primary provider only."""

    _supported = {"discovery", "specification", "reconciliation", "gap_analysis", "planning"}

    def __init__(self, executor: ModelExecutor, prompts: ProductStagePrompts | None = None, *, team_profiles: tuple[AgentProfile,...] | None = None) -> None:
        self.executor=executor
        self.prompts=prompts or ProductStagePrompts()
        self.team_profiles=team_profiles
        self.outputs: dict[tuple[str,str],dict] = {}

    def execute(self,item:WorkItem,stage:str)->dict:
        if stage not in self._supported:
            raise ValueError(f"unsupported product stage: {stage}")

        verified_greenfield = False
        if stage == "reconciliation":
            snapshot=item.context.get("state_snapshot")
            if not isinstance(snapshot,dict) or not snapshot.get("summary"):
                # Existing projects retain their durable-snapshot contract.
                # Only a source-pinned authenticated Console greenfield can
                # reconcile from live code without inventing a DB snapshot.
                verified_greenfield = _verified_greenfield_source_for_reconciliation(item.context)
                if not verified_greenfield:
                    raise ValueError("existing-project reconciliation requires a durable state snapshot")
            else:
                evidence=snapshot.get("evidence")
                source_status=snapshot.get("source_status")
                if not evidence and not source_status:
                    raise ValueError("existing-project reconciliation requires source evidence")

        order=("discovery","specification","reconciliation","gap_analysis")
        prior={s:self.outputs[(item.run_id,s)] for s in order if (item.run_id,s) in self.outputs}
        objective=getattr(self.prompts,stage)
        if verified_greenfield:
            objective = (
                "Reconcile this already-created Console greenfield using only "
                "the exact-SHA live Github source receipt, verified current "
                "project facts and authorized OWNER continuation. No durable "
                "historical project snapshot is available, so do not invent "
                "one or promote any Preview/PR as complete. Return JSON only "
                "with observed_stage, summary, evidence, gaps, constraints, "
                "source_status. Only inspected source files can substantiate "
                "code deficiencies; selected read paths are not write authority."
            )
        intake_context=item.context
        resume=item.context.get("_verified_resume_prior_stages")
        if resume is not None:
            origin=item.context.get("_verified_resume_origin")
            if (stage!="planning" or tuple(item.stages)!=("planning",)
                or prior or not isinstance(resume,dict)
                or set(resume)!={"reconciliation","gap_analysis"}
                or not isinstance(origin,dict)
                or origin.get("generation")!=item.execution_generation
                or not all(isinstance(v,dict) for v in resume.values())
                or not (
                    (isinstance(resume["reconciliation"].get("summary"), str)
                     and bool(resume["reconciliation"]["summary"].strip()))
                    or (isinstance(resume["reconciliation"].get("summary"), dict)
                        and bool(resume["reconciliation"]["summary"])
                        and isinstance(resume["reconciliation"]["summary"].get("objective"), str)
                        and bool(resume["reconciliation"]["summary"]["objective"].strip()))
                )
                or not isinstance(resume["gap_analysis"].get("recommended_next_work"),list)
                or not resume["gap_analysis"]["recommended_next_work"]):
                raise PermissionError("verified planning checkpoint is invalid")
            for completed in resume.values():
                assert_executed_product_stage_output(completed)
            prior.update(resume)
            # Checkpointed gap analysis is now the canonical prior stage;
            # do not double-bill its tokens by echoing it in the manifest.
            intake_context=dict(item.context)
            intake_context.pop("_verified_resume_prior_stages",None)
            manifest=intake_context.get("manifest")
            if isinstance(manifest,dict):
                manifest=dict(manifest)
                manifest.pop("gap_analysis",None)
                intake_context["manifest"]=manifest
        registry=None
        if stage=="planning" and self.team_profiles is not None:
            registry=[
                {
                    "agent_key":profile.agent_key,
                    "role":profile.role,
                    "capabilities":list(profile.capabilities),
                    "allowed_tools":list(profile.allowed_tools),
                }
                for profile in self.team_profiles if profile.is_active
            ]
        context=json.dumps(
            {
                "project_key":item.project_key,
                "intake":intake_context,
                "prior_stages":prior,
                "execution_registry":registry,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        result=self.executor.execute(
            ExecutionRoute.DIRECT,
            ModelRequest(
                task_id=item.task_id,
                objective=objective,
                context=context,
                run_id=item.run_id,
                constraints=(
                    "Return valid JSON only.",
                    "Do not invent unavailable business decisions.",
                    "Do not claim tests, repository inspection, deployment, or external validation unless supplied as evidence.",
                    "Treat deterministic current_state_facts as newer operational evidence than historical intake or state_snapshot when they conflict.",
                    "Treat intake_spec known_pending as historical/unverified only; it cannot establish active work or justify a planning priority decision without independent current evidence.",
                    "Record assumptions explicitly.",
                    "For planning, use the supplied execution_registry as the canonical vocabulary for preferred_agent_role and required_capabilities; do not invent specialist roles when an existing role can own the task.",
                    "Human approval/release is a gate, not an executable agent task.",
                ),
            ),
        )
        try:
            output=json.loads(result.output)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{stage} returned invalid JSON") from exc
        if not isinstance(output,dict):
            raise ValueError(f"{stage} output must be a JSON object")
        # A response that declares itself deferred, simulated, or dependent on
        # a later model call is not executed Product Stage evidence. Reject it
        # before it can enter in-memory prior-stage context or durable storage.
        assert_executed_product_stage_output(output)
        if stage=="planning":
            tasks=output.get("tasks")
            if isinstance(tasks,list):
                for task in tasks:
                    if not isinstance(task,dict):
                        continue
                    task_key=str(task.get("task_key") or "").strip()
                    title=str(task.get("title") or "").strip()
                    if not title and task_key:
                        task["title"]=task_key
        if stage=="planning":
            _drop_unsubstantiated_business_priorities(output,item.context.get("current_state_facts"))
            # Do not settle a run as completed if no executable task or real
            # decision was produced. Such a result may signal a stale request,
            # but it is not a successful development delivery.
            if not isinstance(output.get("tasks"),list):
                raise ValueError("planning requires an explicit tasks array")
            if not output["tasks"] and not output.get("decisions_needed"):
                raise PlanningNoActionableWork()
        if stage=="planning" and self.team_profiles is not None:
            _validate_pre_pr_planning_tasks(output,self.team_profiles)
            output["_team_plan"]=build_execution_team_plan(output,self.team_profiles)
        output["_evidence"]={"provider_ref":result.provider_ref,"role":result.role.value,"usage":result.usage or {}}
        self.outputs[(item.run_id,stage)]=output
        return output
