"""Read-only, fail-closed evidence for a merged nonproduction GitHub PR.

This module NEVER calls GitHub merge APIs or treats a preview-branch merge
as a production release. The Control Plane atomically records the distinction.
"""
from __future__ import annotations

import re
from typing import Any


_SHA = re.compile(r"^[0-9a-f]{40}$")


def verify_nonproduction_preview_merge(github: Any, item: Any, pr: Any) -> dict | None:
    """Return exact merged-preview evidence or None while Vercel is not READY.

    The queue has already verified the *candidate* CI/quality/Preview receipt.
    A merge into preview/** is a separate integration; its new merge SHA must
    be present in the target branch and have an exact successful Vercel status.
    """
    base_ref = str(getattr(pr, "base_ref", "") or "")
    if not base_ref.startswith("preview/") or base_ref == "preview/":
        raise RuntimeError("nonproduction observer accepts only preview/** PR targets")
    if getattr(pr, "head_sha", None) != item.candidate_commit:
        raise RuntimeError("nonproduction merge PR head drifted from validated candidate")
    if (getattr(pr, "head_ref", None) != item.branch
            or getattr(pr, "head_repository", None) != item.repository
            or getattr(pr, "number", None) != item.pr_number):
        raise RuntimeError("nonproduction merge PR identity mismatch")
    if getattr(pr, "state", None) != "closed" or not getattr(pr, "merged", False):
        return None
    merge_sha = str(getattr(pr, "merge_commit_sha", "") or "")
    if not _SHA.fullmatch(item.candidate_commit) or not _SHA.fullmatch(merge_sha):
        raise RuntimeError("nonproduction merge does not have valid exact SHAs")
    if merge_sha == item.candidate_commit:
        raise RuntimeError("nonproduction merge must produce a distinct target merge SHA")
    base_tip = github.get_branch_sha(base_ref)
    if not _SHA.fullmatch(str(base_tip)):
        raise RuntimeError("nonproduction merge target branch returned invalid SHA")
    if base_tip != merge_sha:
        compare = github.compare_commits(merge_sha, base_tip)
        if (compare.get("status") != "ahead" or compare.get("behind_by") != 0
                or type(compare.get("ahead_by")) is not int
                or not 1 <= compare["ahead_by"] <= 20):
            raise RuntimeError("nonproduction merge SHA is not a bounded ancestor of target branch")

    statuses = github.get_commit_statuses(merge_sha)
    if not isinstance(statuses, list):
        raise RuntimeError("exact merge SHA has no verifiable status collection")
    vercel = [row for row in statuses
              if isinstance(row, dict) and row.get("context") == "Vercel"]
    if len(vercel) != 1:
        return None
    state = str(vercel[0].get("state") or "")
    if state in {"failure", "error"}:
        raise RuntimeError("nonproduction merge Vercel deployment failed")
    if state != "success":
        return None
    main_sha = github.get_branch_sha("main")
    if not _SHA.fullmatch(str(main_sha)) or main_sha == merge_sha:
        raise RuntimeError("nonproduction merge overlaps production main")
    if github.get_branch_sha(base_ref) != base_tip:
        raise RuntimeError("nonproduction target moved during verification")
    return {
        "repository": item.repository,
        "pr_number": str(item.pr_number),
        "candidate_commit": item.candidate_commit,
        "head_sha": pr.head_sha,
        "head_ref": pr.head_ref,
        "base_ref": base_ref,
        "merge_sha": merge_sha,
        "merged": True,
        "vercel_state": "success",
        "observed_base_tip": base_tip,
        "merge_is_ancestor": True,
        "production_main_sha": main_sha,
        "production_released": False,
        "evidence_source": "github_exact_pr_and_merge_commit_status",
    }
