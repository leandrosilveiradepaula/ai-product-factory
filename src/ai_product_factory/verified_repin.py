"""Exact-SHA repin authorization assembled only from privileged Control Plane data.

The returned object carries evidence for model context; it does not expand
repository write scopes, replace live GitHub verification or authorize release.
"""
from __future__ import annotations

import re
from typing import Any


_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _positive(value: Any) -> bool:
    return type(value) is int and value > 0


def verified_repin(
    *,
    project_id: str,
    project_key: str,
    repository: str,
    target: object,
    control: object,
    events: object,
) -> dict | None:
    if not isinstance(target, dict) or not isinstance(control, dict):
        return None
    policy = target.get("repin_policy")
    native = policy.get("native_ci") if isinstance(policy, dict) else None
    if not (isinstance(native, dict) and policy.get("enabled") is True
            and native.get("event") == "pull_request"
            and native.get("schema_version") == 1
            and _positive(native.get("workflow_id"))
            and isinstance(native.get("workflow_name"), str)
            and bool(native.get("workflow_name").strip())):
        return None
    sha, branch, pr = (
        target.get("sha"), target.get("branch"), target.get("candidate_pr_number")
    )
    if not (
        isinstance(sha, str) and _SHA.fullmatch(sha)
        and isinstance(branch, str) and branch.startswith("preview/")
        and target.get("repository") == repository
        and target.get("mode") == "open_pr_candidate"
        and target.get("schema_version") == 1
        and _positive(pr)
        and control.get("project_id") == project_id
        and control.get("state") == "running"
        and _positive(control.get("generation"))
        and _positive(control.get("version"))
        and isinstance(events, list)
    ):
        return None
    for event in events:
        if not isinstance(event, dict):
            continue
        kind = event.get("event_type")
        actor = event.get("actor_ref")
        if not (
            event.get("project_id") == project_id
            and event.get("actor_type") == "system"
            and _positive(event.get("id"))
            and (
                (kind == "project.delivery_target.reconciled"
                 and actor == "factory-candidate-reconciler")
                or (kind == "project.delivery_target.replaced"
                    and actor in {"factory-candidate-switch",
                                  "factory-released-source-rotation"})
            )
        ):
            continue
        receipt = event.get("payload")
        if not isinstance(receipt, dict):
            continue
        old_sha = receipt.get("old_sha")
        common = (
            receipt.get("project_key") == project_key
            and receipt.get("repository") == repository
            and receipt.get("new_sha") == sha
            and receipt.get("ci_sha") == sha
            and receipt.get("generation") == control["generation"]
            and receipt.get("version") == control["version"]
            and _positive(receipt.get("ci_run_id"))
            and isinstance(old_sha, str)
            and _SHA.fullmatch(old_sha)
            and old_sha != sha
        )
        if not common:
            continue
        if kind == "project.delivery_target.reconciled":
            valid = (
                receipt.get("status") == "updated"
                and receipt.get("source") == "github_actions_exact_sha"
                and receipt.get("branch") == branch
                and receipt.get("pr_number") == pr
                and receipt.get("compare_status") == "ahead"
                and _positive(receipt.get("ahead_by"))
                and receipt.get("behind_by") == 0
            )
        else:
            valid = (
                receipt.get("status") == "replaced"
                and receipt.get("new_branch") == branch
                and receipt.get("new_pr_number") == pr
                and receipt.get("old_branch") != branch
                and _positive(receipt.get("old_pr_number"))
                and receipt.get("old_pr_number") != pr
                and _positive(receipt.get("issue_number"))
                and isinstance(receipt.get("request_id"), str)
                and bool(receipt.get("request_id").strip())
            )
        if not valid:
            continue
        return {
            "kind": "control_plane_native_ci_repin",
            "source_transition": kind,
            "audit_event_id": event["id"],
            "project_key": project_key,
            "repository": repository,
            "branch": branch,
            "sha": sha,
            "previous_sha": old_sha,
            "candidate_pr_number": pr,
            "ci_sha": sha,
            "ci_run_id": receipt["ci_run_id"],
            "ci_workflow_id": native["workflow_id"],
            "ci_workflow_name": native["workflow_name"],
            "generation": control["generation"],
            "version": control["version"],
        }
    return None
