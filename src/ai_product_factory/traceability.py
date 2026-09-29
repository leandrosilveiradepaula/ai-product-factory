from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass


def _normalize(value:str)->str:
    return re.sub(r"\s+"," ",value.strip()).lower()


def _task_external_key(title:str)->str:
    return "plan-"+hashlib.md5(title.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class RequirementTrace:
    requirements:tuple[dict,...]

    @property
    def count(self)->int:
        return len(self.requirements)


def _criterion_text(value:object)->tuple[str,str|None]:
    if isinstance(value,str):
        return value.strip(),None
    if isinstance(value,dict):
        key=value.get("requirement_key") or value.get("key") or value.get("id")
        for field in ("statement","criterion","text","description","outcome"):
            text=value.get(field)
            if isinstance(text,str) and text.strip():
                return text.strip(),str(key).strip() if key else None
    return "",None


def build_requirement_trace(engineering_plan:dict)->RequirementTrace:
    raw_tasks=engineering_plan.get("tasks")
    tasks=[x for x in raw_tasks if isinstance(x,dict)] if isinstance(raw_tasks,list) else []
    out:list[dict]=[]
    seen:set[str]=set()
    for index,task in enumerate(tasks):
        task_key=str(task.get("task_key") or task.get("key") or f"task-{index+1}").strip()
        title=str(task.get("title") or task_key).strip()
        criteria=task.get("acceptance_criteria")
        if not isinstance(criteria,list) or not criteria:
            continue
        for position,value in enumerate(criteria,1):
            statement,explicit_key=_criterion_text(value)
            if not statement:
                continue
            if explicit_key:
                requirement_key=explicit_key
            else:
                digest=hashlib.sha256(
                    f"{task_key}\n{_normalize(statement)}".encode("utf-8")
                ).hexdigest()[:12]
                requirement_key=f"REQ-{digest.upper()}"
            if requirement_key in seen:
                continue
            seen.add(requirement_key)
            out.append({
                "requirement_key":requirement_key,
                "statement":statement,
                "task_key":task_key,
                "task_title":title,
                "task_external_key":_task_external_key(title),
                "criterion_position":position,
                "source_ref":"planning.acceptance_criteria",
            })
    return RequirementTrace(tuple(out))


def trace_as_json(trace:RequirementTrace)->str:
    return json.dumps(list(trace.requirements),ensure_ascii=False,sort_keys=True)
