"""Deterministic triage for a previously merged code candidate.

A read-only GitHub witness can justify *reviewing* reuse, never source
rebinding, task completion or production release. Only exact-SHA, registered
GitHub Actions workflow evidence can raise CI from unknown to verified.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

_SHA = re.compile(r"[0-9a-f]{40}\Z")


def classify_existing_delivery(
    github: object, *, witness: object, ci_policy: object,
) -> dict:
    if (not isinstance(witness, Mapping)
        or witness.get("status") != "existing_delivery_candidate_unverified"
        or witness.get("source_binding_unchanged") is not True
        or witness.get("ci_verified") is not False
        or witness.get("release_authorized") is not False
        or witness.get("product_ready") is not False
        or getattr(github, "repository", None) != witness.get("repository")
        or not isinstance(witness.get("candidate_sha"), str)
        or not _SHA.fullmatch(witness["candidate_sha"])
        or not isinstance(witness.get("candidate_ref"), str)):
        raise PermissionError("untrusted existing delivery witness")
    result = {
        **dict(witness),
        "status": "awaiting_existing_delivery_reconciliation",
        "decision": "review_existing_candidate_not_reimplement",
        "ci_verified": False,
        "ci_evidence_state": "unverified",
        "source_binding_unchanged": True,
        "release_authorized": False,
        "product_ready": False,
        "next_gate": "independent_candidate_evaluation",
    }
    if not isinstance(ci_policy, Mapping):
        return result
    workflow_id = ci_policy.get("workflow_id")
    workflow_path = ci_policy.get("workflow_path")
    event = ci_policy.get("event")
    if (type(workflow_id) is not int or workflow_id < 1
        or not isinstance(workflow_path, str)
        or not workflow_path.startswith(".github/workflows/")
        or not workflow_path.endswith((".yaml", ".yml"))
        or event not in ("push", "pull_request")):
        return result
    candidate_sha = witness["candidate_sha"]
    if github.get_branch_sha(witness["candidate_ref"]) != candidate_sha:
        raise PermissionError("existing delivery candidate moved during CI witness")
    try:
        inventory = github._call(
            "GET", f"/repos/{github.repository}/actions/runs",
            query={"head_sha": candidate_sha, "per_page": "100"},
        )
        if (not isinstance(inventory, Mapping)
            or not isinstance(inventory.get("workflow_runs"), list)
            or len(inventory["workflow_runs"]) > 100
            or type(inventory.get("total_count")) is not int
            or inventory["total_count"] > 100):
            return result
        eligible = [
            run for run in inventory["workflow_runs"]
            if isinstance(run, Mapping)
            and run.get("head_sha") == candidate_sha
            and run.get("workflow_id") == workflow_id
            and run.get("path") == workflow_path
            and run.get("event") == event
            and run.get("name") == ci_policy.get("workflow_name")
            and type(run.get("id")) is int and run["id"] > 0
            and type(run.get("run_attempt")) is int and run["run_attempt"] >= 1
        ]
        if not eligible:
            return result
        latest = max(eligible, key=lambda r: (r["id"], r["run_attempt"]))
        if latest.get("status") != "completed" or latest.get("conclusion") != "success":
            result["ci_evidence_state"] = "not_successful"
            return result
        jobs = github._call(
            "GET", f"/repos/{github.repository}/actions/runs/{latest['id']}/jobs",
            query={"per_page": "100"},
        )
        if (not isinstance(jobs, Mapping)
            or not isinstance(jobs.get("jobs"), list)
            or type(jobs.get("total_count")) is not int
            or not 1 <= jobs["total_count"] <= 100
            or len(jobs["jobs"]) != jobs["total_count"]
            or any(not isinstance(j, Mapping)
                   or j.get("run_id") != latest["id"]
                   or j.get("status") != "completed"
                   or j.get("conclusion") != "success" for j in jobs["jobs"])):
            return result
        if github.get_branch_sha(witness["candidate_ref"]) != candidate_sha:
            raise PermissionError("existing delivery candidate moved after CI witness")
        result["ci_verified"] = True
        result["ci_evidence_state"] = "exact_sha_native_actions_success"
        result["ci_run_id"] = latest["id"]
        result["ci_run_attempt"] = latest["run_attempt"]
        result["ci_workflow_id"] = workflow_id
    except PermissionError:
        raise
    except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
        return result
    return result
