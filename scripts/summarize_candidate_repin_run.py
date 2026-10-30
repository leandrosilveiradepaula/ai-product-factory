"""Validate and summarize only bounded existing-candidate reconciliation receipts.

No Control Plane writes, network requests, model calls, or full manifest/secret
logging. The GitHub Actions job summary itself is the durable no-op witness.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
_SHA = re.compile(r"^[a-f0-9]{40}$")
_STATUSES = {"unchanged", "updated", "deferred", "blocked", "error"}
_REASON_CODES = {"candidate_draft_hold", "candidate_source_consumed", "candidate_cas_conflict", "candidate_preflight_blocked",
                 "candidate_transport_error"}


def summarize(payload: object) -> tuple[dict, str]:
    if not isinstance(payload, dict):
        raise ValueError("candidate receipt must be an object")
    status = payload.get("status")
    scanned, eligible, disabled, limit = (
        payload.get(k) for k in ("scanned", "eligible", "policy_disabled", "limit")
    )
    if status not in {"idle", "completed", "deferred", "completed_with_deferrals", "partial_failure"}:
        raise ValueError("candidate receipt status invalid")
    if any(type(x) is not int for x in (scanned, eligible, disabled, limit)):
        raise ValueError("candidate counts missing")
    if not (0 <= scanned <= 100 and 0 <= eligible <= scanned
            and 0 <= disabled <= scanned and eligible + disabled == scanned
            and 1 <= limit <= 5):
        raise ValueError("candidate receipt counts inconsistent")
    group, groups, more = (payload.get(k) for k in
                           ("rotation_group", "total_groups", "next_page"))
    expected_groups = (eligible + limit - 1) // limit
    if (type(groups) is not int or groups != expected_groups
            or type(more) is not bool or more != (groups > 1)):
        raise ValueError("candidate receipt group count inconsistent")
    if groups == 0:
        if group is not None or status != "idle":
            raise ValueError("idle candidate receipt invalid")
        expected_count = 0
    else:
        if type(group) is not int or not (0 <= group < groups) or status == "idle":
            raise ValueError("candidate rotation identity invalid")
        expected_count = min(limit, eligible - group * limit)
    results = payload.get("results")
    if not isinstance(results, list) or len(results) != expected_count:
        raise ValueError("candidate result inventory incomplete")
    safe = []
    seen = set()
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("candidate result malformed")
        key, outcome = result.get("project_key"), result.get("status")
        if not isinstance(key, str) or not _KEY.fullmatch(key) or key in seen:
            raise ValueError("candidate project identity invalid")
        seen.add(key)
        if outcome not in _STATUSES:
            raise ValueError("candidate outcome invalid")
        sha = (result.get("sha") if outcome == "unchanged" else
               result.get("observed_sha") if outcome == "deferred" else result.get("new_sha"))
        if outcome in {"unchanged", "updated", "deferred"} and (
            not isinstance(sha, str) or not _SHA.fullmatch(sha)
        ):
            raise ValueError("candidate successful SHA missing")
        reason_code = result.get("reason_code")
        if outcome in {"blocked", "error", "deferred"}:
            # Accept only a closed, publicly documented vocabulary. Historical
            # arbitrary 'reason' strings or upstream HTTP bodies never enter
            # the job summary.
            if reason_code is not None and reason_code not in _REASON_CODES:
                raise ValueError("unknown candidate reconciliation reason_code")
        else:
            reason_code = None
        if outcome == "deferred" and reason_code not in {"candidate_draft_hold", "candidate_source_consumed"}:
            raise ValueError("unrecognized candidate deferral")
        if outcome in {"blocked", "error"} and reason_code in {"candidate_draft_hold", "candidate_source_consumed"}:
            raise ValueError("draft hold cannot mask candidate failure")
        safe.append({"project_key": key, "status": outcome, "sha": sha if outcome in
                     {"unchanged", "updated", "deferred"} else None,
                     **({"reason_code": reason_code} if reason_code is not None else {})})
    failed = any(item["status"] in {"blocked", "error"} for item in safe)
    if status == "partial_failure" and not failed:
        raise ValueError("failure receipt has no failing candidate")
    deferred = sum(item["status"] == "deferred" for item in safe)
    if status != ("partial_failure" if failed else
                  "deferred" if deferred == len(safe) and deferred else
                  "completed_with_deferrals" if deferred else
                  "completed" if safe else "idle"):
        raise ValueError("candidate batch status does not match outcomes")
    output = {
        "status": status,
        "scanned": scanned,
        "eligible": eligible,
        "policy_disabled": disabled,
        "rotation_group": group,
        "total_groups": groups,
        "results": safe,
    }
    lines = [
        "### Existing-project candidate reconciliation",
        "",
        f"- Result: **{status}**",
        f"- Inventory: {scanned} active existing projects; {eligible} policy-enabled; {disabled} policy-disabled",
        f"- Rotation group: {group if group is not None else 'N/A'} of {groups} groups; up to {limit} candidates per run",
        "- Scope: exact-SHA GitHub / native CI, non-production repin only; no model, task, merge or release",
        "",
        "| Project | Result | Candidate SHA | Reason code |",
        "|---|---|---|---|",
    ]
    for result in safe:
        lines.append(f"| {result['project_key']} | {result['status']} | {result['sha'] or 'N/A'} | {result.get('reason_code') or '—'} |")
    if not safe:
        lines.append("| — | idle (no eligible policies) | — | — |")
    lines.extend(("", "This receipt proves only the observed candidates and outcomes in this run; not global product readiness.", ""))
    return output, "\n".join(lines)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Expected one local JSON receipt path")
    path = Path(sys.argv[1])
    if not path.is_file() or path.stat().st_size > 65536:
        raise SystemExit("Candidate receipt missing or oversized")
    output, summary = summarize(json.loads(path.read_text(encoding="utf-8")))
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    destination = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if destination:
        with open(destination, "a", encoding="utf-8") as f:
            f.write(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
