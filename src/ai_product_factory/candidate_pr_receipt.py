"""Exact, durable original-PR-to-current-candidate evidence validation.

Only service-side receipt readers call this helper. GitHub HEAD must still be
verified independently before evaluation or deployment.
"""
from __future__ import annotations

from urllib.parse import quote


def validate_create_pr_candidate(*,read,run_id:str,pr_number:int,original_head:str,
                                 candidate_commit:str,run_metadata:dict)->None:
    if pr_number<1 or not original_head or not candidate_commit:
        raise RuntimeError("durable PR evidence missing identity")
    if original_head==candidate_commit:
        return
    change_set_id=run_metadata.get("change_set_id")
    if run_metadata.get("source")!="change-set" or not isinstance(change_set_id,str) or not change_set_id.strip():
        raise RuntimeError("durable PR evidence does not match candidate commit")
    receipts=read(
        "factory_tool_usage?select=metadata&run_id=eq."+quote(run_id)
        +"&operation=eq.reconcile_pr_candidate&order=created_at.desc&limit=1"
    )
    if not isinstance(receipts,list) or len(receipts)!=1 or not isinstance(receipts[0],dict):
        raise RuntimeError("audited candidate reconciliation receipt missing")
    meta=receipts[0].get("metadata") or {}
    if (not isinstance(meta,dict) or meta.get("previous_commit")!=original_head
        or meta.get("candidate_commit")!=candidate_commit
        or meta.get("change_set_id")!=change_set_id
        or meta.get("pr_number")!=str(pr_number)
        or meta.get("old_sha")!=original_head
        or meta.get("new_sha")!=candidate_commit
        or meta.get("compare_status")!="ahead"):
        raise RuntimeError("audited candidate reconciliation receipt does not match PR")
