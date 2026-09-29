from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .agent_scheduler import AgentProfile
from .execution_team_planner import build_execution_team_plan


@dataclass(frozen=True)
class TeamPlannerEvalFailure:
    case_key:str
    code:str
    expected:object
    actual:object


@dataclass(frozen=True)
class TeamPlannerEvalSummary:
    cases:int
    passed:int
    failures:tuple[TeamPlannerEvalFailure,...]

    @property
    def ok(self)->bool:
        return not self.failures


def load_team_planner_cases(path:str|Path)->tuple[dict,...]:
    data=json.loads(Path(path).read_text())
    cases=data.get("cases")
    if not isinstance(cases,list):
        raise ValueError("Team Planner eval corpus requires cases array")
    return tuple(dict(x) for x in cases if isinstance(x,dict))


def evaluate_team_planner_cases(cases:Sequence[dict],profiles:Sequence[AgentProfile])->TeamPlannerEvalSummary:
    failures:list[TeamPlannerEvalFailure]=[]
    passed=0
    for case in cases:
        key=str(case.get("key") or "unnamed")
        expected=case.get("expected") if isinstance(case.get("expected"),dict) else {}
        out=build_execution_team_plan(case.get("plan") if isinstance(case.get("plan"),dict) else {},profiles)
        roles={str(x.get("role")) for x in out.get("selected_agents",[]) if isinstance(x,dict)}
        case_failures=[]

        expected_status=str(expected.get("status") or "ready")
        if out.get("status")!=expected_status:
            case_failures.append(TeamPlannerEvalFailure(key,"status",expected_status,out.get("status")))

        required=set(str(x) for x in expected.get("required_roles",[]))
        missing=sorted(required-roles)
        if missing:
            case_failures.append(TeamPlannerEvalFailure(key,"missing_required_roles",sorted(required),sorted(roles)))

        forbidden=set(str(x) for x in expected.get("forbidden_roles",[]))
        extra=sorted(forbidden & roles)
        if extra:
            case_failures.append(TeamPlannerEvalFailure(key,"forbidden_roles_selected",sorted(forbidden),sorted(roles)))

        max_peak=int(expected.get("max_worker_peak",999))
        actual_peak=int(out.get("planned_worker_peak") or 0)
        if actual_peak>max_peak:
            case_failures.append(TeamPlannerEvalFailure(key,"overstaffed_worker_peak",max_peak,actual_peak))

        if case_failures:
            failures.extend(case_failures)
        else:
            passed+=1

    return TeamPlannerEvalSummary(len(cases),passed,tuple(failures))
