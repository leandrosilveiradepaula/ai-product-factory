"""Exact-SHA non-production source policy for existing-product development."""
from __future__ import annotations

from dataclasses import dataclass
import re


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
_REF = re.compile(r"preview/[A-Za-z0-9_./-]{1,170}\Z")


@dataclass(frozen=True)
class PinnedNonproductionTarget:
    repository: str
    branch: str
    sha: str
    candidate_pr_number: int

    @classmethod
    def parse(cls, value: object, *, repository: str) -> "PinnedNonproductionTarget":
        if not isinstance(value, dict):
            raise PermissionError("existing project requires an explicit verified delivery target")
        if value.get("schema_version") != 1 or value.get("mode") != "open_pr_candidate":
            raise PermissionError("unsupported delivery target policy")
        repo, branch, sha = value.get("repository"), value.get("branch"), value.get("sha")
        number = value.get("candidate_pr_number")
        if not isinstance(repo, str) or not _REPO.fullmatch(repo) or repo != repository:
            raise PermissionError("delivery target repository does not match project")
        if (not isinstance(branch, str) or not _REF.fullmatch(branch)
            or "//" in branch or ".." in branch or "/." in branch or branch.endswith(("/", "."))
            or branch.endswith(".lock") or "@{" in branch):
            raise PermissionError("delivery target is not a safe non-production Preview branch")
        if not isinstance(sha, str) or not _SHA.fullmatch(sha):
            raise PermissionError("delivery target requires an exact lowercase commit SHA")
        if type(number) is not int or number < 1:
            raise PermissionError("delivery target requires a positive candidate PR number")
        return cls(repo, branch, sha, number)

    def verify(self, github: object) -> None:
        if getattr(github, "repository", None) != self.repository:
            raise PermissionError("GitHub adapter repository differs from the pinned delivery target")
        if github.get_branch_sha(self.branch) != self.sha:
            raise PermissionError("candidate branch moved; reconcile exact SHA before writing")
        pr = github.get_pull_request(self.candidate_pr_number)
        if (getattr(pr, "state", None) != "open"
            or bool(getattr(pr, "merged", False))
            or getattr(pr, "head_sha", None) != self.sha
            or getattr(pr, "head_ref", None) != self.branch
            or getattr(pr, "head_repository", None) != self.repository
            or getattr(pr, "base_ref", None) != "main"):
            raise PermissionError("delivery target PR is not the verified, open non-production candidate")
