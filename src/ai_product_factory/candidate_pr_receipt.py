"""Validate a bounded, contiguous chain from the original PR receipt to the current SHA.

Each reconciliation receipt is immutable and independently tied to the same
run/change-set/PR. An arbitrary latest SHA or a single unverified intermediate
SHA must not create a new Factory delivery candidate.
"""
from __future__ import annotations

import re
from urllib.parse import quote

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_MAX_RECONCILIATIONS = 8


def validate_create_pr_candidate(*, read, run_id: str, pr_number: int,
                                 original_head: str, candidate_commit: str,
                                 run_metadata: dict) -> None:
    if (type(pr_number) is not int or pr_number < 1
        or not isinstance(original_head, str) or not _SHA.fullmatch(original_head)
        or not isinstance(candidate_commit, str) or not _SHA.fullmatch(candidate_commit)):
        raise RuntimeError("durable PR evidence missing identity")
    if original_head == candidate_commit:
        return
    change_set_id = run_metadata.get("change_set_id") if isinstance(run_metadata, dict) else None
    if (not isinstance(run_metadata, dict) or run_metadata.get("source") != "change-set"
        or not isinstance(change_set_id, str) or not change_set_id.strip()):
        raise RuntimeError("durable PR evidence does not match candidate commit")

    receipts = read(
        "factory_tool_usage?select=metadata&run_id=eq." + quote(run_id, safe="")
        + "&operation=eq.reconcile_pr_candidate&order=created_at.desc,id.desc&limit="
        + str(_MAX_RECONCILIATIONS + 1)
    )
    if (not isinstance(receipts, list) or not 1 <= len(receipts) <= _MAX_RECONCILIATIONS
        or any(not isinstance(x, dict) or not isinstance(x.get("metadata"), dict)
               for x in receipts)):
        raise RuntimeError("audited candidate reconciliation receipt missing or unbounded")

    current = candidate_commit
    visited = {current}
    for row in receipts:
        evidence = row["metadata"]
        previous = evidence.get("previous_commit")
        new = evidence.get("candidate_commit")
        if (new != current or evidence.get("old_sha") != previous
            or evidence.get("new_sha") != new
            or not isinstance(previous, str) or not _SHA.fullmatch(previous)
            or previous in visited
            or evidence.get("change_set_id") != change_set_id
            or str(evidence.get("pr_number")) != str(pr_number)
            or evidence.get("compare_status") != "ahead"
            or str(evidence.get("behind_by")) != "0"
            or not str(evidence.get("ahead_by") or "").isdigit()
            or int(str(evidence.get("ahead_by") or "0")) < 1):
            raise RuntimeError("audited candidate reconciliation chain has drift or a cycle")
        if previous == original_head:
            return
        visited.add(previous)
        current = previous
    raise RuntimeError("audited candidate reconciliation chain does not reach original PR")
