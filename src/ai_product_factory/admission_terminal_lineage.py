"""Read-only, bounded diagnosis of a terminal root's Change Set lineage.

A completed Product Stage/Console continuation is not evidence that its
descendant Work Units reached CI, Preview or a human release. This file
classifies exact root receipt + project-owned Change Set; it never claims work,
reopens retired artifacts or certifies a product/release.
"""
from __future__ import annotations

import re
from typing import Any

_UUID=re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
_SHA=re.compile(r"^[0-9a-f]{40}$")
_TERMINAL=frozenset({"blocked","completed","superseded","failed","cancelled"})
_ACTIVE=frozenset({
    "created","queued","pending","ready","building","integrating",
    "ci_pending","preview_ready","awaiting_release",
})
_STATES=_TERMINAL|_ACTIVE
_UNIT_STATES=frozenset({
    "pending","queued","assigned","running","completed","integrated",
    "blocked","cancelled","failed","superseded",
})
_LIMIT=30


def _uuid(value: Any)->str:
    if not isinstance(value,str) or _UUID.fullmatch(value) is None:
        raise RuntimeError("invalid terminal lineage identity")
    return value


def terminal_root_lineage(
    *, project_id:str, root_task_id:str, root_run:dict,
    current_generation:int|None, change_sets:list[dict], work_units:list[dict],
)->dict|None:
    """Return sanitized evidence and next step, not an authorization.

    Only the selected terminal run, project-owned root task and its exact
    Change Sets qualify. A missing Change Set is not proof of release.
    """
    pid=_uuid(project_id)
    root=_uuid(root_task_id)
    if (not isinstance(root_run,dict)
        or root_run.get("task_id")!=root
        or root_run.get("status") not in {"completed","integrated","merged","blocked","failed","cancelled"}):
        raise RuntimeError("terminal root run identity mismatch")
    if (not isinstance(change_sets,list) or not isinstance(work_units,list)
        or len(change_sets)>_LIMIT or len(work_units)>_LIMIT):
        raise RuntimeError("terminal lineage evidence is unbounded")
    if not change_sets:
        if work_units:
            raise RuntimeError("orphaned work unit evidence")
        return None

    ids:set[str]=set()
    for row in change_sets:
        if not isinstance(row,dict):
            raise RuntimeError("malformed terminal Change Set")
        cs_id=_uuid(row.get("id"))
        if (cs_id in ids or row.get("project_id")!=pid
            or row.get("root_task_id")!=root
            or row.get("status") not in _STATES
            or not isinstance(row.get("created_at"),str)
            or not row["created_at"]):
            raise RuntimeError("cross-root or invalid terminal Change Set")
        if row.get("release_run_id") is not None:
            _uuid(row["release_run_id"])
        ids.add(cs_id)

    units_by_cs={c:[] for c in ids}
    observed_units:set[str]=set()
    for row in work_units:
        if not isinstance(row,dict):
            raise RuntimeError("malformed Work Unit evidence")
        uid=_uuid(row.get("id"))
        cs=_uuid(row.get("change_set_id"))
        if (uid in observed_units or cs not in ids
            or row.get("status") not in _UNIT_STATES):
            raise RuntimeError("orphaned or invalid Work Unit evidence")
        output=row.get("output_commit")
        if output is not None and (not isinstance(output,str) or _SHA.fullmatch(output) is None):
            raise RuntimeError("invalid immutable Work Unit output")
        observed_units.add(uid)
        units_by_cs[cs].append(row)

    # Current root lineage is the latest created Change Set (not a random
    # project-level terminal run, another continuation or an old release).
    latest=max(change_sets,key=lambda row:(row["created_at"],row["id"]))
    cs_id=latest["id"]
    status=latest["status"]
    release_id=latest.get("release_run_id")
    selected_units=units_by_cs[cs_id]
    outputs=sum(
        row.get("status") in {"completed","integrated"}
        and isinstance(row.get("output_commit"),str)
        for row in selected_units
    )
    metadata=root_run.get("metadata")
    if metadata is not None and not isinstance(metadata,dict):
        raise RuntimeError("malformed terminal execution generation")
    epoch=(metadata or {}).get("execution_generation")
    if epoch is not None and (type(epoch) is not int or epoch<1):
        raise RuntimeError("invalid terminal execution generation")
    if current_generation is not None and (type(current_generation) is not int or current_generation<1):
        raise RuntimeError("invalid active execution generation")
    revoked=bool(epoch is not None and current_generation is not None and epoch!=current_generation)

    evidence={
        "change_set_id":cs_id,
        "change_set_status":status,
        "historical_change_set_count":len(change_sets)-1,
        "work_unit_count":len(selected_units),
        "work_units_with_recorded_output_sha":outputs,
        "release_run_recorded":release_id is not None,
        "execution_epoch_revoked":revoked,
        # The output SHA only proves a Work Unit was completed, NOT that
        # the commit was integrated, tested, previewed or merged.
        "delivery_verified":False,
    }
    if status=="superseded":
        state,reason,action="blocked","root_change_set_superseded","review_obsolete_change_set_evidence"
    elif status=="blocked":
        state,reason,action="blocked","root_change_set_blocked","review_blocked_change_set"
    elif status in {"failed","cancelled"}:
        state,reason,action="blocked","root_change_set_"+status,"review_terminal_change_set"
    elif status in _ACTIVE:
        state,reason,action="waiting","root_change_set_handoff_pending","inspect_change_set_eligibility"
    elif status=="completed":
        state,reason,action="waiting","root_change_set_completed","verify_release_boundary"
    else:
        raise RuntimeError("unknown Change Set state")
    if revoked and status in _ACTIVE:
        state,reason,action="blocked","root_change_set_execution_epoch_revoked","review_new_human_continuation"
    # Neither a completed Work Unit nor a completed Change Set is an
    # authorization to restart an old run. Exact next action is evidence
    # review; a NEW authenticated human continuation is a separate control.
    return {"status":state,"reason_code":reason,"next_step":action,
            "evidence":evidence}
