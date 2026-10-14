"""Fail-closed pure checks for trusted, SHA-exact Preview promotion.

This module is preparation for the privileged Actions workflow; it does not
change workflow triggers, mutate GitHub refs or access GitHub credentials.
The protected workflow must independently refetch the PR directly before
any Git mutation when this contract is integrated.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

SHA = re.compile(r"^[0-9a-f]{40}$")
VERIFIED_PROMOTION_ACTIONS = frozenset({"reused", "updated", "created_then_updated"})
REQUIRED_CHECKS = ("test", "factory-acceptance", "validate")


@dataclass(frozen=True)
class PreviewEligibility:
    allowed: bool
    reason: str
    candidate_sha: str


def _sha(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA.fullmatch(value))


def candidate_eligibility(
    pr: Mapping[str, Any],
    *,
    expected_sha: str,
    repository: str,
    checks: Sequence[Mapping[str, Any]],
    require_console_change: bool = True,
    changed_files: Sequence[str] | None = None,
) -> PreviewEligibility:
    """Recheck candidate immediately before mutation from fresh trusted API data.

    Eligibility returned here is advisory until the privileged caller executes
    the read again directly before ref update. Never cache eligibility across
    awaits, polls, review transitions, commits or branch changes.
    """
    if not _sha(expected_sha) or not isinstance(repository, str) or repository.count("/") != 1:
        return PreviewEligibility(False, "invalid_identity", str(expected_sha))
    if not isinstance(pr, Mapping):
        return PreviewEligibility(False, "invalid_pr", expected_sha)
    if pr.get("state") != "open":
        return PreviewEligibility(False, "pr_not_open", expected_sha)
    if pr.get("draft") is not False:
        return PreviewEligibility(False, "pr_draft_or_unknown", expected_sha)
    base = pr.get("base")
    head = pr.get("head")
    if not isinstance(base, Mapping) or not isinstance(head, Mapping):
        return PreviewEligibility(False, "missing_refs", expected_sha)
    base_repo = base.get("repo")
    head_repo = head.get("repo")
    if (not isinstance(base_repo, Mapping) or not isinstance(head_repo, Mapping)
        or base_repo.get("full_name") != repository
        or head_repo.get("full_name") != repository
        or base.get("ref") != "main"):
        return PreviewEligibility(False, "untrusted_repo_or_base", expected_sha)
    if not _sha(head.get("sha")) or head["sha"] != expected_sha:
        return PreviewEligibility(False, "stale_candidate_sha", expected_sha)
    if not isinstance(checks, Sequence) or isinstance(checks, (str, bytes)):
        return PreviewEligibility(False, "invalid_checks", expected_sha)
    for check_name in REQUIRED_CHECKS:
        matched = [
            check for check in checks if isinstance(check, Mapping)
            and check.get("name") == check_name
            and check.get("head_sha") == expected_sha
            and check.get("status") == "completed"
            and check.get("conclusion") == "success"
        ]
        if not matched:
            return PreviewEligibility(False, "missing_exact_green_check:" + check_name, expected_sha)
    if require_console_change:
        if (not isinstance(changed_files, Sequence)
                or isinstance(changed_files, (str, bytes))
                or not changed_files
                or any(not isinstance(path, str) or not path for path in changed_files)):
            return PreviewEligibility(False, "unverified_changed_files", expected_sha)
        if not any(path.startswith("apps/console/") for path in changed_files):
            return PreviewEligibility(False, "preview_not_applicable", expected_sha)
    return PreviewEligibility(True, "eligible", expected_sha)


def browser_dispatch_eligibility(
    *,
    promotion_action: str,
    observed_ref_sha: str | None,
    expected_sha: str,
    candidate: PreviewEligibility,
) -> PreviewEligibility:
    """Do not start browser verification from an unverified/stale promotion."""
    if not candidate.allowed or candidate.candidate_sha != expected_sha or not _sha(expected_sha):
        return PreviewEligibility(False, "candidate_not_eligible", str(expected_sha))
    if promotion_action not in VERIFIED_PROMOTION_ACTIONS:
        return PreviewEligibility(False, "promotion_not_confirmed", expected_sha)
    if observed_ref_sha != expected_sha:
        return PreviewEligibility(False, "preview_ref_sha_mismatch", expected_sha)
    return PreviewEligibility(True, "eligible_browser_dispatch", expected_sha)
