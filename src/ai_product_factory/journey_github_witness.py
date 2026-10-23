"""Read-only, twice-observed GitHub candidate witness for E2E certification.

The first PR response does not pin subsequent changed-file, Git ancestry and
CI reads. A second complete response and, before merge, the current ref must
still represent the same candidate. This module performs no mutations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class CandidateWitness:
    number: int
    head_sha: str
    head_repository: str
    head_ref: str
    base_ref: str
    base_sha: str
    state: str
    draft: bool
    merged: bool
    merge_sha: str | None


def observe_candidate(
    github, *, number: int, sha: str, repository: str, branch: str,
) -> CandidateWitness:
    """Read one exact PR snapshot and, for an open PR, its real branch SHA.

    Merged branches can legitimately be deleted; the verified merge commit and
    immutable release receipts supply the merged-path proof instead.
    """
    if (type(number) is not int or number < 1
        or not isinstance(sha, str) or not _SHA.fullmatch(sha)
        or not isinstance(repository, str) or repository.count("/") != 1
        or any(not part for part in repository.split("/"))
        or not isinstance(branch, str) or not branch.strip()
        or branch in {"main", "master"}
        or branch.startswith("/") or "\\" in branch
        or ".." in branch or "//" in branch or "@{" in branch
        or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in branch)):
        raise RuntimeError("candidate witness identity is invalid")

    pr = github.get_pull_request(number)
    if (type(getattr(pr, "number", None)) is not int
        or pr.number != number
        or getattr(pr, "head_sha", None) != sha
        or getattr(pr, "head_repository", None) != repository
        or getattr(pr, "head_ref", None) != branch
        or not isinstance(getattr(pr, "base_ref", None), str)
        or not pr.base_ref
        or not isinstance(getattr(pr, "base_sha", None), str)
        or not _SHA.fullmatch(pr.base_sha)
        or getattr(pr, "draft", None) is not False
        or type(getattr(pr, "merged", None)) is not bool):
        raise RuntimeError("candidate PR origin, state or SHA is unverified")

    state = getattr(pr, "state", None)
    merged = pr.merged
    merge_sha = getattr(pr, "merge_commit_sha", None)
    if merged:
        if state != "closed" or not isinstance(merge_sha, str) or not _SHA.fullmatch(merge_sha):
            raise RuntimeError("merged candidate lacks verified release identity")
    elif state != "open":
        raise RuntimeError("candidate PR is not an open, unmerged delivery")
    else:
        if github.get_branch_sha(branch) != sha:
            raise RuntimeError("candidate branch changed during read-only audit")

    return CandidateWitness(
        number=number, head_sha=sha, head_repository=repository,
        head_ref=branch, base_ref=pr.base_ref, base_sha=pr.base_sha,
        state=state, draft=False, merged=merged,
        merge_sha=merge_sha if isinstance(merge_sha, str) else None,
    )


def require_unchanged_candidate(github, original: CandidateWitness) -> None:
    """Refuse evidence combined from two different GitHub PR snapshots."""
    updated = observe_candidate(
        github, number=original.number, sha=original.head_sha,
        repository=original.head_repository, branch=original.head_ref,
    )
    if updated != original:
        raise RuntimeError("candidate PR identity drifted during E2E evidence collection")
