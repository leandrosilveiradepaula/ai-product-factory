"""Rotate a human-merged existing-project source candidate without replay.

A merged PR is immutable release *observation*, not a Factory-owned run.
This opt-in transition uses the already versioned, epoch-fenced
factory_replace_nonproduction_candidate_v1 RPC. A new docs-only PR is
source governance for FUTURE work, never proof of implementation or release.
"""
from __future__ import annotations

import re
from typing import Any

from .candidate_source_evidence import (
    collect_candidate_source_evidence, source_issue_scope_alignment,
)
from .nonproduction_candidate_repin import (
    ExistingCandidatePolicy, _select_latest_native_ci,
)
from .github_rest import GitHubRestAdapter
from .github_auth import resolve_github_token

_SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
_PREVIEW = re.compile(r"preview/[a-z0-9][a-z0-9/_-]{1,95}\Z", re.ASCII)
_SOURCE_PATH = "docs/codex/CURRENT_TASK.md"
_FACTORY_REPO = "leandrosilveiradepaula/ai-product-factory"
_OWNER_ID = 256917842


def _authorized_request(project: dict, issue_number: int) -> tuple[ExistingCandidatePolicy, dict]:
    if type(issue_number) is not int or issue_number < 1:
        raise PermissionError("invalid authorized issue identity")
    repository = project.get("repository")
    policy = ExistingCandidatePolicy.parse(project.get("manifest"), repository=repository)
    request = project["manifest"].get("continuation_request")
    owner = request.get("github") if isinstance(request, dict) else None
    if (not isinstance(request, dict) or request.get("source") != "github-owner"
        or not isinstance(request.get("id"), str) or not request["id"]
        or not isinstance(request.get("summary"), str)
        or not isinstance(owner, dict)
        or owner.get("repository") != _FACTORY_REPO
        or type(owner.get("issue_number")) is not int or owner["issue_number"] != 1055
        or type(owner.get("actor_id")) is not int or owner["actor_id"] != _OWNER_ID
        or re.search(r"(?<!\d)issue\s+#" + str(issue_number) + r"\b",
                     request["summary"], re.IGNORECASE) is None):
        raise PermissionError("merged candidate rotation lacks exact OWNER issue authority")
    return policy, request


def _old_human_release(github: Any, *, old: Any, main_sha: str) -> str:
    """No dependency on the old branch: GitHub may delete it after merge."""
    pr = github.get_pull_request(old.candidate_pr_number)
    merge_sha = getattr(pr, "merge_commit_sha", None)
    if (getattr(pr, "number", None) != old.candidate_pr_number
        or getattr(pr, "state", None) != "closed"
        or getattr(pr, "merged", None) is not True
        or getattr(pr, "draft", None) is not False
        or getattr(pr, "head_sha", None) != old.sha
        or getattr(pr, "head_ref", None) != old.branch
        or getattr(pr, "head_repository", None) != old.repository
        or getattr(pr, "base_ref", None) != "main"
        or not isinstance(merge_sha, str) or not _SHA.fullmatch(merge_sha)):
        raise PermissionError("pinned old PR is not the exact observed human merge")

    ancestry = github.compare_commits(merge_sha, main_sha)
    if (not isinstance(ancestry, dict)
        or ancestry.get("status") not in {"identical", "ahead"}
        or type(ancestry.get("ahead_by")) is not int
        or not 0 <= ancestry["ahead_by"] <= 10000
        or ancestry.get("behind_by") != 0):
        raise PermissionError("human merge is not in the current production main ancestry")
    return merge_sha


def attest_merged_source_rotation(
    github: Any, *, project: dict, candidate_pr_number: int, issue_number: int,
) -> dict:
    """Attest both PRs and exact CI; never write or accept documentation as delivery."""
    policy, request = _authorized_request(project, issue_number)
    old = policy.target
    repo = old.repository
    if (getattr(github, "repository", None) != repo
        or type(candidate_pr_number) is not int or candidate_pr_number < 1
        or candidate_pr_number == old.candidate_pr_number):
        raise PermissionError("invalid candidate or repository identity")

    main_sha = github.get_branch_sha("main")
    if not isinstance(main_sha, str) or not _SHA.fullmatch(main_sha):
        raise PermissionError("current main is not an exact commit")
    old_merge = _old_human_release(github, old=old, main_sha=main_sha)

    pr = github.get_pull_request(candidate_pr_number)
    branch = getattr(pr, "head_ref", None)
    candidate = getattr(pr, "head_sha", None)
    if (getattr(pr, "number", None) != candidate_pr_number
        or getattr(pr, "state", None) != "open"
        or getattr(pr, "merged", None) is not False
        or getattr(pr, "draft", None) is not True
        or getattr(pr, "head_repository", None) != repo
        or getattr(pr, "base_ref", None) != "main"
        or getattr(pr, "base_sha", None) != main_sha
        or not isinstance(branch, str) or not _PREVIEW.fullmatch(branch)
        or branch == old.branch
        or not isinstance(candidate, str) or not _SHA.fullmatch(candidate)
        or candidate == old.sha
        or github.get_branch_sha(branch) != candidate):
        raise PermissionError("new source PR is not an exact nonproduction candidate")

    comparison = github.compare_commits(main_sha, candidate)
    if (not isinstance(comparison, dict) or comparison.get("status") != "ahead"
        or type(comparison.get("ahead_by")) is not int
        or not 1 <= comparison["ahead_by"] <= 8
        or comparison.get("behind_by") != 0):
        raise PermissionError("source PR does not descend from current main")

    # Only a documented source boundary is allowed at rotation time.
    # No production code or tests are attributed to this rotation.
    if github.get_pull_request_files(candidate_pr_number) != (_SOURCE_PATH,):
        raise PermissionError("bootstrap PR must change only CURRENT_TASK governance")

    raw = github._call("GET", f"/repos/{repo}/pulls/{candidate_pr_number}")
    pr_body = raw.get("body") if isinstance(raw, dict) else None
    if (not isinstance(pr_body, str)
        or re.search(r"(?<!\d)#" + str(issue_number) + r"\b", pr_body) is None):
        raise PermissionError("source PR is not linked to the authorized issue")

    task_record = github.get_file_text(_SOURCE_PATH, ref=candidate)
    if (not isinstance(task_record, str) or not task_record.strip()
        or len(task_record.encode("utf-8")) > 65536
        or source_issue_scope_alignment(
            task_record, request["summary"], repository=repo,
        )["status"] != "matched"):
        raise PermissionError("source governance is not aligned to OWNER scope")

    source = collect_candidate_source_evidence(
        task_record, github, sha=candidate,
        continuation_request=request["summary"],
    )
    if (source.get("status") != "bounded_source_inspected"
        or source.get("issue_scope_alignment", {}).get("status") != "matched"
        or source.get("missing_paths") or source.get("omitted_paths")
        or not 2 <= len(source.get("inspected_files", ())) <= 4):
        raise PermissionError("source bootstrap lacks bounded current code evidence")

    inventory = github._call(
        "GET", f"/repos/{repo}/actions/runs",
        query={"head_sha": candidate, "per_page": "100"},
    )
    ci = _select_latest_native_ci(
        inventory, policy=policy.ci, branch=branch, sha=candidate,
    )

    # Reobserve BOTH the terminal human release and the new open PR.
    # CAS fences the durable epoch; this preflight fences live GitHub identity.
    if github.get_branch_sha("main") != main_sha:
        raise PermissionError("main moved during source rotation")
    if _old_human_release(github, old=old, main_sha=main_sha) != old_merge:
        raise PermissionError("human merge identity changed")
    second = github.get_pull_request(candidate_pr_number)
    if (getattr(second, "state", None) != "open"
        or getattr(second, "merged", None) is not False
        or getattr(second, "draft", None) is not True
        or getattr(second, "head_sha", None) != candidate
        or getattr(second, "head_ref", None) != branch
        or getattr(second, "base_sha", None) != main_sha
        or github.get_branch_sha(branch) != candidate):
        raise PermissionError("new source PR moved after native CI")

    return {
        "source": "github_actions_exact_sha", "repository": repo,
        "request_id": request["id"], "issue_number": issue_number,
        "old_branch": old.branch, "old_sha": old.sha,
        "old_pr_number": old.candidate_pr_number,
        "old_merged": True, "old_merge_sha": old_merge,
        "new_branch": branch, "new_sha": candidate,
        "new_pr_number": candidate_pr_number,
        "pr_head_sha": candidate, "branch_head_sha": candidate,
        "pr_base": "main", "pr_base_sha": main_sha, "pr_state": "open",
        "compare_status": "ahead", "ahead_by": comparison["ahead_by"],
        "behind_by": 0, "ci_conclusion": "success", "ci_sha": candidate,
        "ci_run_id": ci["id"], "ci_workflow_id": ci["workflow_id"],
        "ci_run_number": ci["run_number"],
        "ci_run_attempt": ci["run_attempt"],
        "ci_workflow_name": policy.ci.workflow_name,
        "ci_workflow_path": policy.ci.workflow_path,
        "source_only_candidate": True,
        "source_scoped_file_count": len(source["inspected_files"]),
    }


def rotate_released_project(
    project: dict, *, candidate_pr_number: int, issue_number: int,
    github_factory=None, rpc=None,
) -> dict:
    """Use existing exclusive-service-role CAS; do NOT mutate old runs or release."""
    from .nonproduction_candidate_repin import _post_rpc
    key = project.get("project_key")
    control = project.get("execution_control")
    if (project.get("project_kind") != "existing" or project.get("is_active") is not True
        or not isinstance(key, str) or not key
        or not isinstance(control, dict) or control.get("state") != "running"
        or type(control.get("generation")) is not int or control["generation"] < 1
        or type(control.get("version")) is not int or control["version"] < 0):
        raise PermissionError("project not eligible for released source rotation")
    repo = project.get("repository")
    github = github_factory(repo) if github_factory else GitHubRestAdapter(
        repository=repo, token=resolve_github_token(repo),
    )
    evidence = attest_merged_source_rotation(
        github, project=project, candidate_pr_number=candidate_pr_number,
        issue_number=issue_number,
    )
    params = {
        "p_project_key": key, "p_expected_old_branch": evidence["old_branch"],
        "p_expected_old_sha": evidence["old_sha"],
        "p_expected_old_pr": evidence["old_pr_number"],
        "p_new_branch": evidence["new_branch"],
        "p_new_sha": evidence["new_sha"],
        "p_new_pr": evidence["new_pr_number"],
        "p_issue_number": issue_number,
        "p_expected_generation": control["generation"],
        "p_expected_version": control["version"],
        "p_evidence": evidence,
        "p_actor_ref": "factory-released-source-rotation",
    }
    receipt = (rpc or _post_rpc)("factory_replace_nonproduction_candidate_v1", params)
    if (not isinstance(receipt, dict) or receipt.get("status") != "replaced"
        or receipt.get("project_key") != key
        or receipt.get("old_sha") != evidence["old_sha"]
        or receipt.get("old_pr_number") != evidence["old_pr_number"]
        or receipt.get("new_sha") != evidence["new_sha"]
        or receipt.get("new_pr_number") != candidate_pr_number
        or receipt.get("generation") != control["generation"] + 1
        or receipt.get("version") != control["version"] + 1):
        raise RuntimeError("released candidate rotation receipt mismatch")
    return {
        "status": "source_candidate_rotated", "project_key": key,
        "old_merged_pr": evidence["old_pr_number"],
        "old_merge_sha": evidence["old_merge_sha"],
        "new_source_pr": candidate_pr_number,
        "new_source_sha": evidence["new_sha"],
        "source_only": True, "factory_run_created": False,
        "generation": receipt["generation"], "version": receipt["version"],
        "audit_event": "project.delivery_target.replaced",
    }


def rotate_released_one(
    project_key: str, *, candidate_pr_number: int, issue_number: int,
) -> dict:
    """Read project + control from server-side credentials, never from browser."""
    from .nonproduction_candidate_repin import _load_projects, _with_control
    rows = _load_projects(project_key=project_key)
    if len(rows) != 1:
        raise PermissionError("existing project not uniquely registered")
    return rotate_released_project(
        _with_control(rows[0]), candidate_pr_number=candidate_pr_number,
        issue_number=issue_number,
    )
