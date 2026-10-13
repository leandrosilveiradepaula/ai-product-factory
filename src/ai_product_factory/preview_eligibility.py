from __future__ import annotations

def is_delivery_preview_run(run: dict) -> bool:
    """Product-readiness audit rows do not represent a delivery Preview PR."""
    metadata = run.get("metadata")
    return not (isinstance(metadata, dict) and metadata.get("source") == "dogfood_manual_audit")


def is_quota_blocked_candidate(run: dict, deployments: list[dict]) -> bool:
    """24-hour-filtered deployments only block their exact run and candidate SHA."""
    run_id, sha = str(run.get("id") or ""), str(run.get("candidate_commit") or "")
    if not run_id or not sha:
        return False
    return any(
        str(row.get("run_id") or "") == run_id
        and isinstance(row.get("metadata"), dict)
        and str(row["metadata"].get("candidate_commit") or "") == sha
        for row in deployments
    )
