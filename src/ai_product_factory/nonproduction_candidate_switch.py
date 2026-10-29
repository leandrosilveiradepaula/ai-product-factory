"""Explicit replacement of a stale existing-project Preview candidate.

This verifier never writes GitHub or Supabase. It attests two complete
candidate identities, current native CI, and an authorized issue request.
An RPC performs a separate epoch-fenced, quiescent, service-role-only CAS.
"""
from __future__ import annotations

import re
from typing import Any

from .nonproduction_candidate_repin import ExistingCandidatePolicy, _select_latest_native_ci

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_PREVIEW = re.compile(r"preview/[a-z0-9][a-z0-9/_-]{1,95}\Z")


def verify_candidate_switch(
    github: Any, *, project: dict, candidate_pr_number: int,
    issue_number: int,
) -> dict:
    """Read-only GitHub preflight; never infer authority from an open PR alone."""
    repository = project.get("repository")
    policy = ExistingCandidatePolicy.parse(project.get("manifest"), repository=repository)
    old = policy.target
    manifest = project["manifest"]
    request = manifest.get("continuation_request")
    if (not isinstance(request, dict) or request.get("source") != "github-owner"
        or not isinstance(request.get("id"), str) or not request["id"]
        or not isinstance(request.get("summary"), str)
        or type(issue_number) is not int or issue_number < 1
        or re.search(r"(?<!\d)issue\s+#" + str(issue_number) + r"\b",
                     request["summary"], re.IGNORECASE) is None):
        raise PermissionError("candidate switch is not bound to an authorized issue request")
    if (getattr(github, "repository", None) != repository
        or type(candidate_pr_number) is not int or candidate_pr_number < 1
        or candidate_pr_number == old.candidate_pr_number):
        raise PermissionError("invalid replacement candidate identity")

    # Verify the OLD candidate remains unchanged; never abandon a moving PR.
    old.verify(github)
    new_pr = github.get_pull_request(candidate_pr_number)
    new_branch = getattr(new_pr, "head_ref", None)
    new_sha = getattr(new_pr, "head_sha", None)
    if (getattr(new_pr, "number", None) != candidate_pr_number
        or getattr(new_pr, "state", None) != "open"
        or getattr(new_pr, "merged", None) is not False
        or getattr(new_pr, "draft", None) is not False
        or getattr(new_pr, "head_repository", None) != repository
        or getattr(new_pr, "base_ref", None) != "main"
        or not isinstance(new_branch, str) or not _PREVIEW.fullmatch(new_branch)
        or new_branch == old.branch
        or not isinstance(new_sha, str) or not _SHA.fullmatch(new_sha)
        or new_sha == old.sha
        or github.get_branch_sha(new_branch) != new_sha):
        raise PermissionError("replacement PR is not an immutable verified Preview candidate")

    # Current main is the only permitted base. No older historical base,
    # diverged source, or unreviewed fast-forward may be silently adopted.
    base_sha = github.get_branch_sha("main")
    if (not isinstance(base_sha, str) or not _SHA.fullmatch(base_sha)
        or getattr(new_pr, "base_sha", None) != base_sha):
        raise PermissionError("candidate main base moved")
    comparison = github.compare_commits(base_sha, new_sha)
    if (comparison.get("status") != "ahead"
        or type(comparison.get("ahead_by")) is not int
        or comparison["ahead_by"] not in range(1, 33)
        or comparison.get("behind_by") != 0):
        raise PermissionError("replacement candidate is not a bounded descendant of main")
    # Ensure real changed source code, not a document-only PR.
    changed = github.get_pull_request_files(candidate_pr_number)
    if (not isinstance(changed, tuple) or not any(
        isinstance(path, str) and path.startswith(("src/", "apps/"))
        for path in changed)):
        raise PermissionError("replacement candidate has no scoped implementation")

    # Verify exact issue reference in PR body as well as request.
    raw = github._call("GET", f"/repos/{repository}/pulls/{candidate_pr_number}")
    pr_body = raw.get("body") if isinstance(raw, dict) else None
    if (not isinstance(pr_body, str) or re.search(
        r"(?<!\d)#" + str(issue_number) + r"\b", pr_body) is None):
        raise PermissionError("candidate PR does not reference authorized issue")

    ci_policy = policy.ci
    inventory = github._call(
        "GET", f"/repos/{repository}/actions/runs",
        query={"head_sha": new_sha, "per_page": "100"},
    )
    ci = _select_latest_native_ci(
        inventory, policy=ci_policy, branch=new_branch, sha=new_sha
    )

    # Final observation immediately before the service-role CAS. Race after
    # this preflight is still guarded by the immutable control epoch at RPC.
    old.verify(github)
    again = github.get_pull_request(candidate_pr_number)
    if (github.get_branch_sha(new_branch) != new_sha
        or github.get_branch_sha("main") != base_sha
        or getattr(again, "head_sha", None) != new_sha
        or getattr(again, "head_ref", None) != new_branch
        or getattr(again, "state", None) != "open"
        or getattr(again, "draft", None) is not False):
        raise PermissionError("replacement candidate moved after exact-SHA CI")

    return {
        "source": "github_actions_exact_sha", "repository": repository,
        "request_id": request["id"], "issue_number": issue_number,
        "old_branch": old.branch, "old_sha": old.sha,
        "old_pr_number": old.candidate_pr_number,
        "new_branch": new_branch, "new_sha": new_sha,
        "new_pr_number": candidate_pr_number,
        "pr_head_sha": new_sha, "branch_head_sha": new_sha,
        "pr_base": "main", "pr_base_sha": base_sha, "pr_state": "open",
        "compare_status": "ahead", "ahead_by": comparison["ahead_by"],
        "behind_by": 0, "ci_conclusion": "success", "ci_sha": new_sha,
        "ci_run_id": ci["id"], "ci_workflow_id": ci["workflow_id"],
        "ci_run_number": ci["run_number"],
        "ci_run_attempt": ci["run_attempt"],
        "ci_workflow_name": ci_policy.workflow_name,
        "ci_workflow_path": ci_policy.workflow_path,
    }
