from __future__ import annotations

import json
from dataclasses import dataclass

from .model_executor import ModelExecutor, ModelRequest
from .models import ExecutionRoute
from .runtime_worker import WorkItem
from .agent_scheduler import AgentProfile
from .execution_team_planner import build_execution_team_plan


@dataclass(frozen=True)
class ProductStagePrompts:
    discovery: str = "Structure the product discovery from the approved intake. Return JSON only with problem, users, outcomes, assumptions, open_questions, risks."
    specification: str = "Create an implementable product specification. Return JSON only with scope, user_flows, requirements, non_functional_requirements, acceptance_criteria, exclusions, assumptions."
    reconciliation: str = "Reconcile the existing project from the durable state snapshot, approved intake, and deterministic current_state_facts. Return JSON only with observed_stage, summary, evidence, gaps, constraints, source_status. Preserve confirmed work and do not claim repository checks that are absent from the supplied evidence. When current_state_facts conflict with older intake or snapshot state, treat current_state_facts as the newer operational evidence. A completed/cancelled/failed task is not active work. Verified GitHub capabilities in current_state_facts must not be reported as unverified. Treat intake_spec known_pending and other historical pending labels as unverified historical references only: never call them active work, create a business-priority decision from them, or require a human to resolve their status unless current_state_facts or other supplied current evidence independently confirms they are still active."
    gap_analysis: str = "Compare the reconciled existing-project state with the continuation brief and constraints. Return JSON only with completed, gaps, risks, decisions_needed, recommended_next_work. Do not invent missing evidence or business decisions."
    planning: str = "Create an actionable engineering plan. Return JSON only with architecture, workstreams, tasks, specialist_reviews, dependencies, test_strategy, release_strategy, risks, decisions_needed. The tasks array is strictly pre-PR implementation work and must contain only work executable by a write-capable builder profile from execution_registry (normally development or ui). Do not create product/reconciliation/planning tasks: resolve analysis from supplied evidence in this response. Do not create Security, QA, Operations, CI, Preview, deployment, or human-release tasks in tasks; list required post-candidate specialist roles in specialist_reviews using only security, qa, operations. Human approval/release is always a later gate, never a planning decision or task. If a genuine current human decision is unresolved, put it in decisions_needed and do not make implementation depend on an invented executable task. Each decisions_needed item must be an object with decision_key, decision_kind, question, why_needed, and suggested_response. question, why_needed, and suggested_response must be concise, user-facing Brazilian Portuguese (pt-BR). suggested_response is an advisory draft only: it must preserve least privilege, stay within the supplied user intent, never claim approval already happened, and remain safe for the human to edit before explicitly approving. Avoid internal identifiers and implementation jargon in the question. A business_priority decision must also include candidate_work_keys with at least two external_key values that are currently active in current_state_facts.recent_tasks; historical references and terminal tasks are forbidden candidates. decision_kind must be one of product_requirement, scope_authorization, business_priority. Never ask a human to confirm repository facts, CI/readiness state, credentials/capabilities, already-closed work, or future production/release approval in decisions_needed; resolve supplied evidence autonomously or report a technical blocker outside decisions_needed. Every task must include task_key (stable short identifier), acceptance_criteria (non-empty array of independently verifiable outcomes), required_capabilities, scope_keys, depends_on, and may include preferred_agent_role. task_key values must be unique. depends_on may contain only task_key values from other tasks in this same output; never put decisions, gates, approvals, credentials, or external conditions in depends_on. Every task must be ownable by one write-capable builder profile. Do not assume a fixed number of agents."


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
        required={str(x).strip() for x in (task.get("required_capabilities") or []) if str(x).strip()}
        preferred=str(task.get("preferred_agent_role") or "").strip()
        eligible=[
            profile for profile in builders
            if (not required or required.issubset(set(profile.capabilities)))
            and (not preferred or preferred in {profile.agent_key,profile.role})
        ]
        if not eligible:
            raise ValueError(f"planning task is not executable in a pre-PR builder lane: {task_key}")
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

        if stage == "reconciliation":
            snapshot=item.context.get("state_snapshot")
            if not isinstance(snapshot,dict) or not snapshot.get("summary"):
                raise ValueError("existing-project reconciliation requires a durable state snapshot")
            evidence=snapshot.get("evidence")
            source_status=snapshot.get("source_status")
            if not evidence and not source_status:
                raise ValueError("existing-project reconciliation requires source evidence")

        order=("discovery","specification","reconciliation","gap_analysis")
        prior={s:self.outputs[(item.run_id,s)] for s in order if (item.run_id,s) in self.outputs}
        objective=getattr(self.prompts,stage)
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
                "intake":item.context,
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
        if stage=="planning" and self.team_profiles is not None:
            _validate_pre_pr_planning_tasks(output,self.team_profiles)
            output["_team_plan"]=build_execution_team_plan(output,self.team_profiles)
        output["_evidence"]={"provider_ref":result.provider_ref,"role":result.role.value,"usage":result.usage or {}}
        self.outputs[(item.run_id,stage)]=output
        return output
