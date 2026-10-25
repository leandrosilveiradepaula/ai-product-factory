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
from datetime import datetime, timezone

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


def _attested_utc(value: object) -> datetime | None:
    """Accept timestamps only when PostgREST supplied an aware instant."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def verify_copied_work_unit_waves(
    github, *, final_candidate: str, units: Sequence[Mapping],
    receipts: Sequence[Mapping], change_set_id: str, pr_number: int,
) -> bool:
    """Certify each Work Unit at the FIRST immutable PR candidate after it.

    CI repair waves legitimately replace earlier files. Comparing every
    Work Unit to the *last* PR candidate yields a false failure; comparing
    only to an arbitrary old candidate risks a false pass. Require ordered,
    exact-PR create_pr receipts, the closest subsequent candidate for each
    Work Unit, identical source bytes at that wave, and fast-forward ancestry
    from EVERY wave to the final candidate. No agent, mutation or release.
    """
    if (not isinstance(final_candidate, str) or not SHA.fullmatch(final_candidate)
        or type(pr_number) is not int or pr_number < 1
        or not isinstance(change_set_id, str) or not change_set_id
        or not isinstance(units, (tuple, list)) or not 1 <= len(units) <= 30
        or not isinstance(receipts, (tuple, list)) or not 2 <= len(receipts) <= 16):
        return False
    if any(not isinstance(row, Mapping) or type(row.get("id")) is not int
           for row in receipts):
        return False
    ordered = sorted(receipts, key=lambda row: row["id"])
    candidates: list[str] = []
    stamps: list[datetime] = []
    previous_id = 0
    for entry in ordered:
        meta = entry.get("metadata")
        stamp = _attested_utc(entry.get("created_at"))
        if (not isinstance(meta, Mapping)
            or entry["id"] <= previous_id
            or stamp is None or (stamps and stamp <= stamps[-1])
            or meta.get("change_set_id") != change_set_id
            or type(meta.get("pr")) is not int or meta["pr"] != pr_number
            or not isinstance(meta.get("head_sha"), str)
            or not SHA.fullmatch(meta["head_sha"])
            or meta["head_sha"] in candidates):
            return False
        previous_id = entry["id"]
        candidates.append(meta["head_sha"])
        stamps.append(stamp)
    if candidates[-1] != final_candidate:
        return False
    # Reject forks, replaced branch histories and a candidate reconstructed
    # without the original integration commits.
    if any(not verified_fast_forward(github, older, newer)
           for older, newer in zip(candidates, candidates[1:])):
        return False
    assigned: list[list[Mapping]] = [[] for _ in ordered]
    for unit in units:
        if not isinstance(unit, Mapping):
            return False
        stamp = _attested_utc(unit.get("created_at"))
        if stamp is None:
            return False
        wave = next((i for i, until in enumerate(stamps) if stamp <= until), None)
        if wave is None or (wave and stamp <= stamps[wave - 1]):
            return False
        assigned[wave].append(unit)
    # An unexplained receipt/wave must not be used to inherit earlier proofs.
    if any(not wave for wave in assigned):
        return False
    return all(
        verify_copied_work_units(
            github, original_candidate=sha, final_candidate=final_candidate,
            units=wave,
        )
        for sha, wave in zip(candidates, assigned)
    )
