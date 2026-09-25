from __future__ import annotations

import json
from dataclasses import dataclass

from .model_executor import ModelExecutor, ModelRequest
from .models import ExecutionRoute
from .runtime_worker import WorkItem


@dataclass(frozen=True)
class ProductStagePrompts:
    discovery: str = "Structure the product discovery from the approved intake. Return JSON only with problem, users, outcomes, assumptions, open_questions, risks."
    specification: str = "Create an implementable product specification. Return JSON only with scope, user_flows, requirements, non_functional_requirements, acceptance_criteria, exclusions, assumptions."
    planning: str = "Create an actionable engineering plan. Return JSON only with architecture, workstreams, tasks, dependencies, test_strategy, release_strategy, risks."


class ProductStageExecutor:
    """Executes bootstrap product stages through the primary provider only."""
    def __init__(self, executor: ModelExecutor, prompts: ProductStagePrompts | None = None) -> None:
        self.executor=executor
        self.prompts=prompts or ProductStagePrompts()
        self.outputs: dict[tuple[str,str],dict] = {}

    def execute(self,item:WorkItem,stage:str)->dict:
        if stage not in {"discovery","specification","planning"}:
            raise ValueError(f"unsupported product stage: {stage}")
        prior={s:self.outputs[(item.run_id,s)] for s in ("discovery","specification") if (item.run_id,s) in self.outputs}
        objective=getattr(self.prompts,stage)
        context=json.dumps({"project_key":item.project_key,"intake":item.context,"prior_stages":prior},ensure_ascii=False,sort_keys=True)
        result=self.executor.execute(ExecutionRoute.DIRECT,ModelRequest(task_id=item.task_id,objective=objective,context=context,constraints=("Return valid JSON only.","Do not invent unavailable business decisions.","Record assumptions explicitly.")))
        try: output=json.loads(result.output)
        except json.JSONDecodeError as exc: raise ValueError(f"{stage} returned invalid JSON") from exc
        if not isinstance(output,dict): raise ValueError(f"{stage} output must be a JSON object")
        output["_evidence"]={"provider_ref":result.provider_ref,"role":result.role.value,"usage":result.usage or {}}
        self.outputs[(item.run_id,stage)]=output
        return output
