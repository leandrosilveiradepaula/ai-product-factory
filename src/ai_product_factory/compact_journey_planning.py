"""Bounded structured planning for source-bound V2 greenfield continuations.

The full authorized request, discovery/specification, human decisions and
exact-source facts remain available. Reduce historical plan narration, not
authorization or independent delivery gates.
"""
from __future__ import annotations

from .models import RiskProfile

_ACTIVE = {"queued", "running", "awaiting_human", "blocked"}
_RISK_KEYS = tuple(RiskProfile.__dataclass_fields__)


def linked_greenfield_planning(context: dict, stage: str) -> bool:
    manifest = context.get("manifest")
    binding = context.get("journey_binding_v2")
    return (stage == "planning" and isinstance(manifest, dict)
            and manifest.get("onboarding_mode") == "greenfield"
            and isinstance(binding, dict))


def compact_context(context: dict) -> dict:
    """Keep all requirements, evidence, task scopes, risks and prior decisions.

    The old manifest engineering plan is not current journey authority. Its
    long narrative sections can be repeated in the new discovery/specification
    and current source receipts. Keep the task array and all decisions, and
    preserve every other top-level context field.
    """
    out = dict(context)
    manifest = out.get("manifest")
    if not isinstance(manifest, dict):
        return out
    manifest = dict(manifest)
    old = manifest.get("engineering_plan")
    if isinstance(old, dict):
        manifest["engineering_plan"] = {
            key: value for key, value in old.items()
            if key not in {"architecture", "workstreams", "dependencies",
                           "test_strategy", "release_strategy", "risks"}
        }
        manifest["historical_plan_context_note"] = (
            "Historical plan narrative omitted to avoid duplicate planning; "
            "all prior tasks, decisions, current authorized request, checkpoint "
            "and exact source evidence are retained. Do not infer completion."
        )
    out["manifest"] = manifest
    return out


def compact_objective(*, retry: bool = False) -> str:
    size = (
        "Use one to three cohesive tasks where work is needed. Target at most "
        "1600 output tokens; group related requirements, never discard them."
        if retry else
        "Use one to six cohesive tasks where work is needed. Target at most "
        "2500 output tokens; group related requirements, never discard them."
    )
    return (
        "Return explicit tasks array for implementation, or decisions_needed "
        "for a genuine unresolved material decision. LINKED GREENFIELD CONTINUATION: "
        "complete the immutable journey_request using the exact-SHA source and "
        "test evidence, approved human decisions and completed discovery/specification. "
        "Historical plans and task statuses are not proof of current functionality. "
        "Preserve stable keys where appropriate, but do not reopen completed work, "
        "repeat historical implementation or claim unseen tests or deployments. "
        "Use concrete code changes only for source-supported gaps in the authorized "
        "scope; if an authorized source audit is requested, its versioned report is "
        "a legitimate builder deliverable. Use actual repository-relative paths, "
        "with narrow co-located test files; context_paths must be existing files "
        "supported by the supplied inventory. Read-only evidence is not write "
        "authorization. Use only active development or ui builder profiles with "
        "github_write and their registered capabilities. Tests are builder acceptance "
        "deliverables; independent security, qa and operations belong in "
        "specialist_reviews. Do not schedule analysis, specialist reviews, CI, Preview, "
        "deployment or release as builder tasks. Preserve all human release, access, "
        "cost, security and destructive-change gates. A decision is permitted only for "
        "a genuinely unresolved product requirement, scope authorization or current "
        "business priority; never ask the operator to confirm technical facts or "
        "already approved answers. Decisions use concise Brazilian Portuguese and "
        "business_priority needs two real active candidate_work_keys. If there is no "
        "executable task or genuine decision, return both arrays empty; never invent "
        "work. Every task has a stable unique key, title, short description, explicit "
        "scope_keys, registered required_capabilities, depends_on containing only "
        "other task keys, and two to four concise independently verifiable acceptance "
        "criteria. Scope keys are paths or recognized semantic identifiers, never prose. "
        "Report unknown evidence as unknown. Do not repeat specifications or source "
        "excerpts. Return only one complete JSON object matching output_schema, "
        "without Markdown, commentary, reasoning or code blocks. Architecture, "
        "workstreams, dependencies, tests, release and risks must be concise. "
        + size
    )


def _object(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def _strings():
    return {"type": "array", "items": {"type": "string"}}


def planning_schema() -> dict:
    string = {"type": "string"}
    risk = _object({key: {"type": "boolean"} for key in _RISK_KEYS})
    task = _object({
        "task_key": string, "title": string, "description": string,
        "complexity": {"type": "string", "enum": ["low", "medium", "high", "very_high"]},
        "preferred_agent_role": {"type": "string", "enum": ["development", "ui"]},
        "required_capabilities": _strings(), "scope_keys": _strings(),
        "context_paths": _strings(), "depends_on": _strings(),
        "acceptance_criteria": _strings(), "risk": risk,
    })
    decision = _object({
        "decision_key": string,
        "decision_kind": {"type": "string", "enum": [
            "product_requirement", "scope_authorization", "business_priority"]},
        "question": string, "why_needed": string, "suggested_response": string,
        "candidate_work_keys": _strings(),
    })
    return _object({
        "architecture": string, "workstreams": _strings(),
        "tasks": {"type": "array", "items": task},
        "specialist_reviews": {"type": "array", "items": {
            "type": "string", "enum": ["security", "qa", "operations"]}},
        "dependencies": _strings(), "test_strategy": _strings(),
        "release_strategy": string, "risks": _strings(),
        "decisions_needed": {"type": "array", "items": decision},
    })


def validate_compact_tasks(output: dict) -> None:
    """Enforce executable acceptance deliverables independently of the model.

    Do not reject complete output solely because a model includes more coherent
    tasks than requested or leaves optional narrative sections empty.
    """
    tasks = output.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("planning requires an explicit tasks array")
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("planning tasks must be JSON objects")
        criteria = task.get("acceptance_criteria")
        if not isinstance(criteria, list) or not criteria or not all(
                isinstance(x, str) and x.strip() for x in criteria):
            raise ValueError("linked planning task requires verifiable acceptance criteria")
        for field in ("scope_keys", "required_capabilities", "depends_on"):
            value = task.get(field)
            if not isinstance(value, list) or not all(
                    isinstance(x, str) and x.strip() for x in value):
                raise ValueError("linked planning task has malformed routing fields")
        if not task["scope_keys"] or not task["required_capabilities"]:
            raise ValueError("linked planning task has empty builder scope or capabilities")
        risk = task.get("risk")
        if risk is not None and (not isinstance(risk, dict)
                or any(key not in _RISK_KEYS or type(value) is not bool
                       for key, value in risk.items())):
            raise ValueError("linked planning task has malformed risk flags")
