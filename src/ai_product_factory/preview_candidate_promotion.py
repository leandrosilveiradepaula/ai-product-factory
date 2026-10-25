"""Explicit, opt-in Vercel Preview branch promotion for external repositories.

The ordinary GitHub Vercel adapter only discovers existing deployments.  This
module never promotes unless a trusted, server-side project manifest explicitly
authorizes a Preview-only branch. Production refs and PR merges are unreachable.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Callable

from .github_loop import CIState
from .github_rest import GitHubRequestError, GitHubRestAdapter


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_PREFIX = re.compile(r"preview/[a-z0-9][a-z0-9/_-]{0,63}\Z")


class PreviewPromotionBlocked(RuntimeError):
    """Fixed, non-secret reason that keeps the Preview/release gate closed."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class PreviewPromotionPolicy:
    branch_prefix: str
    source: str
    base_ref: str
    max_ahead_commits: int

    @classmethod
    def from_manifest(cls, manifest: dict) -> "PreviewPromotionPolicy | None":
        preview = manifest.get("preview") if isinstance(manifest, dict) else None
        if not isinstance(preview, dict):
            return None
        raw = preview.get("promotion")
        if raw is None:
            return None  # Older projects can only discover existing deployments.
        if not isinstance(raw, dict) or raw.get("mode") != "github_ref_cas":
            raise PreviewPromotionBlocked("invalid_promotion_policy")
        if preview.get("provider") != "vercel" or preview.get("mode") != "github":
            raise PreviewPromotionBlocked("invalid_promotion_provider")
        if raw.get("enabled") is not True:
            raise PreviewPromotionBlocked("promotion_not_authorized")
        prefix = raw.get("branch_prefix")
        source = raw.get("source")
        base_ref = raw.get("base_ref")
        bound = raw.get("max_ahead_commits", 16)
        if (
            not isinstance(prefix, str) or not _PREFIX.fullmatch(prefix)
            or ".." in prefix or "//" in prefix or prefix.endswith(("/", "-"))
            or source not in ("change_set", "pull_request")
            or not isinstance(base_ref, str) or not base_ref
            or base_ref.startswith("refs/")
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/_-]{0,100}", base_ref)
            or ".." in base_ref or "//" in base_ref
            or type(bound) is not int or not 1 <= bound <= 32
        ):
            raise PreviewPromotionBlocked("invalid_promotion_policy")
        return cls(prefix, source, base_ref, bound)

    def branch_for(self, item: object) -> str:
        if self.source == "pull_request":
            number = getattr(item, "pr_number", None)
            if type(number) is not int or number < 1:
                raise PreviewPromotionBlocked("invalid_candidate_identity")
            suffix = str(number)
        else:
            value = getattr(item, "change_set_id", None)
            if not isinstance(value, str):
                raise PreviewPromotionBlocked("missing_change_set_identity")
            try:
                canonical = str(uuid.UUID(value))
            except ValueError as exc:
                raise PreviewPromotionBlocked("invalid_change_set_identity") from exc
            if canonical != value:
                raise PreviewPromotionBlocked("invalid_change_set_identity")
            suffix = value[:8]
        name = f"{self.branch_prefix}-{suffix}"
        if not _PREFIX.fullmatch(name) or name.startswith("preview/../"):
            raise PreviewPromotionBlocked("invalid_preview_branch")
        return name


def _vercel_quota_blocked(statuses: list[dict]) -> bool:
    for row in statuses:
        if "vercel" not in str(row.get("context") or "").lower():
            continue
        text = " ".join(str(row.get(k) or "") for k in ("description", "target_url")).lower()
        if any(marker in text for marker in (
            "api-deployments-free-per-day", "build-rate-limit",
            "deployment rate limit", "deployment rate limited",
        )):
            return True
    return False


def _verify_candidate(github: GitHubRestAdapter, item: object, policy: PreviewPromotionPolicy) -> object:
    candidate = getattr(item, "candidate_commit", "")
    if not isinstance(candidate, str) or not _SHA.fullmatch(candidate):
        raise PreviewPromotionBlocked("invalid_candidate_sha")
    pr = github.get_pull_request(item.pr_number)
    if (
        pr.number != item.pr_number or pr.state != "open" or pr.merged
        or pr.draft is not False or pr.head_sha != candidate
        or pr.head_repository != item.repository
        or pr.head_ref != item.branch or pr.base_ref != policy.base_ref
        or not isinstance(pr.base_sha, str) or not _SHA.fullmatch(pr.base_sha)
    ):
        raise PreviewPromotionBlocked("candidate_pr_drift")
    comparison = github.compare_commits(pr.base_sha, candidate)
    if (
        comparison.get("status") != "ahead"
        or comparison.get("behind_by") != 0
        or type(comparison.get("ahead_by")) is not int
        or not 1 <= comparison["ahead_by"] <= policy.max_ahead_commits
    ):
        raise PreviewPromotionBlocked("candidate_not_bounded_fast_forward")
    return pr


def promote_preview_candidate(
    *,
    item: object,
    github: GitHubRestAdapter,
    check_epoch: Callable[[], object],
    audit: Callable[[str, dict], object],
) -> dict:
    """One bounded, SHA-exact promotion. Never creates a production branch.

    The immutable manifest policy and the control-plane execution epoch are
    required before *every* GitHub write. GraphQL updateRef(expectedOid) is the
    atomic compare-and-swap; REST PATCH without a lease is deliberately forbidden.
    """
    policy = PreviewPromotionPolicy.from_manifest(item.manifest)
    if policy is None:
        return {"status": "not_configured"}
    branch = policy.branch_for(item)
    candidate = item.candidate_commit
    pr = _verify_candidate(github, item, policy)
    if github.get_ci_state(item.pr_number) is not CIState.SUCCESS:
        raise PreviewPromotionBlocked("candidate_native_ci_not_green")
    statuses = github.get_commit_statuses(candidate)
    if _vercel_quota_blocked(statuses):
        raise PreviewPromotionBlocked("vercel_quota_blocked")
    if any(
        "vercel" in str(row.get("context") or "").lower()
        and row.get("state") == "success" for row in statuses
    ):
        audit("preview.promotion_reused_deployment_status", {
            "candidate_commit": candidate, "pr_number": item.pr_number,
        })
        return {"status": "existing_vercel_status", "branch": branch}

    audit("preview.promotion_intent", {
        "candidate_commit": candidate, "pr_number": item.pr_number,
        "base_sha": pr.base_sha, "branch": branch, "mode": "github_ref_cas",
    })
    check_epoch()
    fresh = _verify_candidate(github, item, policy)
    if fresh.base_sha != pr.base_sha:
        raise PreviewPromotionBlocked("candidate_base_drift")
    if github.get_ci_state(item.pr_number) is not CIState.SUCCESS:
        raise PreviewPromotionBlocked("candidate_ci_changed")
    if _vercel_quota_blocked(github.get_commit_statuses(candidate)):
        raise PreviewPromotionBlocked("vercel_quota_blocked")
    try:
        current = github.get_branch_sha(branch)
    except GitHubRequestError as exc:
        if exc.status != 404:
            raise
        check_epoch()
        # Creating at the trusted PR base and then advancing is an update
        # event for providers which ignore first-time branch creation.
        try:
            github.create_branch_at_sha(branch, pr.base_sha)
        except GitHubRequestError as create_exc:
            # Never adopt a concurrently created ref without a fresh preflight.
            raise PreviewPromotionBlocked("preview_ref_create_conflict") from create_exc
        current = github.get_branch_sha(branch)
    if current == candidate:
        audit("preview.promotion_ref_reused", {
            "candidate_commit": candidate, "pr_number": item.pr_number, "branch": branch,
        })
        return {"status": "ref_already_candidate", "branch": branch}
    if current != pr.base_sha:
        raise PreviewPromotionBlocked("preview_ref_drift")
    check_epoch()
    final = _verify_candidate(github, item, policy)
    if final.base_sha != pr.base_sha:
        raise PreviewPromotionBlocked("candidate_base_drift")
    if _vercel_quota_blocked(github.get_commit_statuses(candidate)):
        raise PreviewPromotionBlocked("vercel_quota_blocked")
    # GitHub checks/quality were observed before the first write; no model
    # invocation, Vercel API token or GitHub production-branch update occurs.
    github.fast_forward_preview_ref_cas(
        branch=branch, expected_sha=pr.base_sha, candidate_sha=candidate,
    )
    if github.get_branch_sha(branch) != candidate:
        raise PreviewPromotionBlocked("preview_ref_postwrite_mismatch")
    audit("preview.promotion_completed", {
        "candidate_commit": candidate, "pr_number": item.pr_number,
        "branch": branch, "previous_sha": pr.base_sha,
    })
    return {"status": "promoted", "branch": branch}
