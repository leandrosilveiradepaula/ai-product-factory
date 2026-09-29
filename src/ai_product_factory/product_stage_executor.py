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
    reconciliation: str = "Reconcile the existing project from the durable state snapshot and approved intake. Return JSON only with observed_stage, summary, evidence, gaps, constraints, source_status. Preserve confirmed work and do not claim repository checks that are absent from the supplied evidence."
    gap_analysis: str = "Compare the reconciled existing-project state with the continuation brief and constraints. Return JSON only with completed, gaps, risks, decisions_needed, recommended_next_work. Do not invent missing evidence or business decisions."
    planning: str = "Create an actionable engineering plan. Return JSON only with architecture, workstreams, tasks, dependencies, test_strategy, release_strategy, risks. Every task must include task_key (stable short identifier), required_capabilities (array of semantic capabilities such as implementation, ui, security_review, tests, ci), scope_keys (array of repository scope roots it may modify), depends_on (array of task_key values), and may include preferred_agent_role only when a specific specialist role is materially required. Each task must be ownable by one specialist profile; represent cross-specialist review or validation as separate tasks rather than combining incompatible capabilities. Do not assume a fixed number of agents."


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
        context=json.dumps(
            {
                "project_key":item.project_key,
                "intake":item.context,
                "prior_stages":prior,
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
                    "Record assumptions explicitly.",
                ),
            ),
        )
        try:
            output=json.loads(result.output)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{stage} returned invalid JSON") from exc
        if not isinstance(output,dict):
            raise ValueError(f"{stage} output must be a JSON object")
        if stage=="planning" and self.team_profiles is not None:
            output["_team_plan"]=build_execution_team_plan(output,self.team_profiles)
        output["_evidence"]={"provider_ref":result.provider_ref,"role":result.role.value,"usage":result.usage or {}}
        self.outputs[(item.run_id,stage)]=output
        return output
