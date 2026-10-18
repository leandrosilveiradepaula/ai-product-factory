from __future__ import annotations

import re
from typing import Any


_SHA = re.compile(r"^[0-9a-f]{40}$")


def _ordered_line_subset(subset: str, whole: str) -> bool:
    """Return True only if every original line survives in the same order."""
    source = iter(whole.splitlines(keepends=True))
    for target in subset.splitlines(keepends=True):
        for actual in source:
            if actual == target:
                break
        else:
            return False
    return True


def verify_preview_base_compatibility(github: Any, pr: Any) -> dict:
    """Bounded exception for a benign *additive* CI workflow change on a preview base.

    When the PR base branch moves, strict fail-closed behavior remains the
    default. A one-commit preview-base advance touching only GitHub Actions
    workflow files can be accepted if the complete updated base workflow is
    already contained, in the same order, in the exact tested PR HEAD.

    This does not update the release candidate, skip CI, deploy to production,
    or authorize a merge. A second branch read rejects concurrent base drift.
    """
    ref = str(getattr(pr, "base_ref", None) or "")
    old = str(getattr(pr, "base_sha", None) or "")
    if not ref or not old:
        return {}

    current = github.get_branch_sha(ref)
    if current == old:
        return {}

    reason = (
        f"GitHub PR base is stale: {ref} moved from {old} to {current}. "
        "Update the PR branch and rerun CI before Preview."
    )
    head = str(getattr(pr, "head_sha", None) or "")
    if (not ref.startswith("preview/") or not _SHA.fullmatch(old)
            or not _SHA.fullmatch(current) or not _SHA.fullmatch(head)):
        raise RuntimeError(reason)

    comparison = github.compare_commits(old, current)
    paths = comparison.get("files")
    if (comparison.get("status") != "ahead" or comparison.get("behind_by") != 0
            or comparison.get("ahead_by") != 1
            or not isinstance(paths, list) or not 0 < len(paths) <= 3
            or any(not isinstance(path, str)
                   or not path.startswith(".github/workflows/")
                   or not path.endswith((".yml", ".yaml"))
                   for path in paths)):
        raise RuntimeError(reason)

    additions = 0
    for path in paths:
        original = github.get_file_text(path, ref=old)
        updated = github.get_file_text(path, ref=current)
        candidate = github.get_file_text(path, ref=head)
        original_lines = original.splitlines(keepends=True)
        updated_lines = updated.splitlines(keepends=True)
        delta = len(updated_lines) - len(original_lines)
        if (delta < 1 or delta > 5
                or not _ordered_line_subset(original, updated)
                or not _ordered_line_subset(updated, candidate)):
            raise RuntimeError(reason)
        additions += delta

    if additions > 6 or github.get_branch_sha(ref) != current:
        raise RuntimeError(reason)

    return {
        "verification_mode": "preview_base_additive_workflow_subsequence",
        "base_ref": ref,
        "reported_base_sha": old,
        "current_base_sha": current,
        "candidate_commit": head,
        "changed_files": paths,
        "ahead_by": 1,
        "added_lines": additions,
    }
