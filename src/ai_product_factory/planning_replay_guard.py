"""Prevent repeat paid planning only with a complete, exact-SHA empty receipt.

Historical empty plans do not prove that a product has no work. A missing,
malformed, out-of-epoch or different-source receipt never certifies no work.
"""
from __future__ import annotations
import re
_SHA=re.compile(r"[0-9a-f]{40}\Z")
_ERROR="planning has no actionable tasks or decisions"

class PlanningReplayBlocked(PermissionError):
    code="planning_resume_no_current_eligible_work_same_sha"
    def __init__(self):
        super().__init__(self.code)

def find_same_source_empty_planning(
    rows: object, *, current_run_id: str, task_id: str, origin: dict,
    current_commit: str, current_request: dict,
) -> bool:
    if (not isinstance(rows,list) or len(rows)>40
        or not isinstance(current_run_id,str) or not current_run_id
        or not isinstance(task_id,str) or not task_id
        or not isinstance(current_commit,str) or not _SHA.fullmatch(current_commit)
        or not isinstance(origin,dict) or not isinstance(current_request,dict)
        or type(origin.get("generation")) is not int or origin["generation"]<1
        or any(not isinstance(origin.get(k),str) or not origin[k]
               for k in ("source_run_id","snapshot_id","request_id"))):
        raise ValueError("invalid bounded planning replay identity")
    for row in rows:
        if (not isinstance(row,dict) or row.get("task_id")!=task_id
            or row.get("status")!="failed" or not isinstance(row.get("id"),str)):
            raise RuntimeError("malformed planning replay inventory")
        if row["id"]==current_run_id:
            continue
        m=row.get("metadata")
        if not isinstance(m,dict):
            raise RuntimeError("malformed historical planning metadata")
        p=m.get("resume_checkpoint")
        if not isinstance(p,dict) or p.get("schema")!="checkpointed_product_planning_v1":
            continue
        if not (p.get("source_run_id")==origin["source_run_id"]
            and p.get("snapshot_id")==origin["snapshot_id"]
            and p.get("request_id")==origin["request_id"]
            and p.get("source_generation")==origin["generation"]
            and m.get("execution_generation")==origin["generation"]
            and m.get("continuation_request_id")==origin["request_id"]
            and m.get("continuation_request")==current_request
            and m.get("error")==_ERROR):
            continue
        stages=m.get("stage_evidence")
        stage=stages.get("planning") if isinstance(stages,dict) else None
        if not isinstance(stage,dict) or stage.get("status")!="failed":
            continue
        receipt=stage.get("output")
        if not isinstance(receipt,dict):
            continue
        if (receipt.get("reason_code")=="planning_non_actionable"
            and receipt.get("observed_model_response") is True
            and type(receipt.get("tasks_count")) is int and receipt["tasks_count"]==0
            and type(receipt.get("decisions_count")) is int and receipt["decisions_count"]==0
            and receipt.get("requires_scope_reconciliation") is True
            and receipt.get("implementation_completed") is False
            and receipt.get("assessed_commit")==current_commit):
            return True
    return False
