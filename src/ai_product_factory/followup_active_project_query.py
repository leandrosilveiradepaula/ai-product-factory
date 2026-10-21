"""Filter paused projects in PostgREST before bounded FIFO lookahead.

Existing foreign keys connect run -> task -> project -> execution-control.
Every !inner is intentional: inactive, draft, paused, stopped, missing-control
or zero-generation projects must not consume the finite observation window.
This query is not authorization: effectful workers still recheck identity and
generation in the privileged transactional epoch RPC.
"""
from __future__ import annotations


_ALLOWED_STATUS = frozenset({"ci_pending", "preview_ready", "awaiting_release"})

_ACTIVE_EMBED = (
    "factory_tasks!inner("
    "factory_projects!inner("
    "is_active,"
    "factory_project_execution_controls!inner(state,generation)"
    "))"
)
_ACTIVE_PREDICATE = (
    "&factory_tasks.factory_projects.is_active=eq.true"
    "&factory_tasks.factory_projects.factory_project_execution_controls.state=eq.running"
    "&factory_tasks.factory_projects.factory_project_execution_controls.generation=gt.0"
)


def active_project_followup_query(*, status: str, limit: int, offset: int = 0) -> str:
    if status not in _ALLOWED_STATUS:
        raise ValueError("unsupported follow-up state")
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("invalid bounded active follow-up window")
    if type(offset) is not int or not 0 <= offset <= 1000000:
        raise ValueError("invalid bounded follow-up offset")
    return (
        "factory_runs?select=id,task_id,branch_name,candidate_commit,"
        "execution_route,metadata," + _ACTIVE_EMBED
        + "&status=eq." + status
        + _ACTIVE_PREDICATE
        + "&order=created_at.asc,id.asc&limit=" + str(limit)
        + ("&offset=" + str(offset) if offset else "")
    )
