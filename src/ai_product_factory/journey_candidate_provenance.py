"""Strict, GET-only provenance for Change Set integration + SHA reconciliation.

An integrator copies verified Work Unit *contents* into a new integration
commit, rather than making the Work Unit commit an ancestor. Compare exact
source bytes against that first candidate, then require a fast-forward
candidate reconciliation for any later repair commit. A merely existing
commit, a moved branch, or a passing unrelated CI run proves nothing.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence

SHA = re.compile(r"[0-9a-f]{40}\Z")
PATH = re.compile(r"(?:[A-Za-z0-9_.()-]+/)*[A-Za-z0-9_.()-]+\Z")


def verified_fast_forward(github, original: str, candidate: str) -> bool:
    if not isinstance(original,str) or not SHA.fullmatch(original):
        return False
    if not isinstance(candidate,str) or not SHA.fullmatch(candidate):
        return False
    if original == candidate:
        return True
    result = github.compare_commits(original,candidate)
    return bool(isinstance(result,dict)
                and result.get("status")=="ahead"
                and type(result.get("ahead_by")) is int
                and result["ahead_by"]>=1
                and type(result.get("behind_by")) is int
                and result["behind_by"]==0)


def verify_copied_work_units(
    github, *, original_candidate: str, final_candidate: str,
    units: Sequence[Mapping],
) -> bool:
    """Verify integration by exact bytes and repaired candidate by ancestry.

    Reject missing paths, partial claims, disjoint commits and excessive
    verification scope. This returns no code or repository text.
    """
    if not verified_fast_forward(github,original_candidate,final_candidate):
        return False
    if not isinstance(units,(tuple,list)) or not (1 <= len(units) <= 30):
        return False
    total_paths=0
    for unit in units:
        if not isinstance(unit,Mapping):
            return False
        if unit.get("status") not in ("completed","integrated"):
            return False
        output=unit.get("output_commit")
        changed=unit.get("changed_files")
        if (not isinstance(output,str) or not SHA.fullmatch(output)
            or not isinstance(changed,list) or not changed or len(changed)>30):
            return False
        if not github.commit_exists(output):
            return False
        if len(set(changed))!=len(changed):
            return False
        total_paths+=len(changed)
        if total_paths>90:
            return False
        for path in changed:
            if (not isinstance(path,str) or len(path)>220
                or not PATH.fullmatch(path) or path.startswith("/")
                or ".." in path.split("/") or path.endswith("/")):
                return False
            # Get two pinned blobs, never an untrusted branch. A changed
            # work-unit blob must be present verbatim in the initial
            # integrated candidate, even if a subsequent audited repair
            # legitimately changes that file before the final CI.
            try:
                work_text=github.get_file_text(path,ref=output)
                integrated_text=github.get_file_text(path,ref=original_candidate)
            except (OSError,RuntimeError,ValueError):
                return False
            if (not isinstance(work_text,str) or not isinstance(integrated_text,str)
                or not work_text or len(work_text.encode("utf-8"))>256000
                or len(integrated_text.encode("utf-8"))>256000):
                return False
            if hashlib.sha256(work_text.encode("utf-8")).digest()!=hashlib.sha256(
                integrated_text.encode("utf-8")
            ).digest():
                return False
    return True


def validate_reconciliation_receipt(
    github, *, receipt: Mapping, old_sha: str, candidate_sha: str,
    pr_number: int, repository: str, change_set_id: str, branch: str,
) -> bool:
    """Validate a Control Plane RPC receipt AND read-only Git ancestry."""
    if not isinstance(receipt,Mapping):
        return False
    if (
        receipt.get("previous_commit")!=old_sha
        or receipt.get("candidate_commit")!=candidate_sha
        or receipt.get("old_sha")!=old_sha
        or receipt.get("new_sha")!=candidate_sha
        or str(receipt.get("pr_number"))!=str(pr_number)
        or receipt.get("repository")!=repository
        or receipt.get("branch")!=branch
        or receipt.get("change_set_id")!=change_set_id
        or receipt.get("compare_status")!="ahead"
        or not isinstance(receipt.get("changed_files"),list)
        or not (1 <= len(receipt["changed_files"]) <= 300)
        or any(not isinstance(p,str) or not PATH.fullmatch(p) for p in receipt["changed_files"])
        or len(set(receipt["changed_files"]))!=len(receipt["changed_files"])
    ):
        return False
    ahead=receipt.get("ahead_by")
    if not isinstance(ahead,(str,int)) or isinstance(ahead,bool):
        return False
    if not re.fullmatch(r"[1-9][0-9]{0,5}",str(ahead)):
        return False
    if not verified_fast_forward(github,old_sha,candidate_sha):
        return False
    comparison=github.compare_commits(old_sha,candidate_sha)
    actual=comparison.get("files") if isinstance(comparison,dict) else None
    # The exact changed-path inventory is the scope of the controlled repair.
    return bool(isinstance(actual,list)
                and set(actual)==set(receipt["changed_files"])
                and comparison.get("ahead_by")==int(ahead))
