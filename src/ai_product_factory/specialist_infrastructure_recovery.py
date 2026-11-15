"""Source-verified one-time continuation of infra-exhausted specialist lanes.

This is NOT a general-purpose retry or a source of product-readiness PASS.
Every external source is read back at its exact SHA before the privileged RPC
is called. The PostgreSQL function independently fences the candidate, epoch,
original three terminal jobs, and single-use recovery marker.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from urllib.parse import quote

from .candidate_pr_receipt import validate_create_pr_candidate

FACTORY_REPOSITORY = "leandrosilveiradepaula/ai-product-factory"
SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z", re.ASCII)
ROLES = frozenset(("qa", "security", "operations"))
REASON = re.compile(r"[a-z][a-z0-9_]{3,63}\Z", re.ASCII)


class SpecialistInfrastructureRecoveryBlocked(RuntimeError):
    """Sanitized, fixed-code source failure; do not print provider responses."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise SpecialistInfrastructureRecoveryBlocked(code)


def one(read, resource: str, select: str, key: str, value: str) -> dict:
    rows = read(f"{resource}?select={select}&{key}=eq.{quote(value,safe='')}&limit=2")
    require(isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict),
            "single_control_plane_source_missing")
    return rows[0]


@dataclass(frozen=True)
class RecoverySources:
    run_id: str
    candidate_sha: str
    factory_sha: str
    execution_generation: int
    repository: str
    project_key: str
    pr_number: int
    ci_run_id: int
    evidence_digest: str

    def receipt(self) -> dict:
        return {
            "schema": "factory-specialist-infrastructure-source-v1",
            "run_id": self.run_id,
            "candidate_sha": self.candidate_sha,
            "factory_sha": self.factory_sha,
            "generation": self.execution_generation,
            "repository": self.repository,
            "project_key": self.project_key,
            "pr_number": self.pr_number,
            "ci_run_id": self.ci_run_id,
            "evidence_digest": self.evidence_digest,
            "writes": 0,
            "paid_calls": 0,
        }


def verify_recovery_sources(*, read, github_get, run_id: str,
                            candidate_sha: str, factory_sha: str) -> RecoverySources:
    """Independently re-read live Control Plane + exact GitHub evidence.

    github_get(repository, path) MUST authenticate the target repository
    separately; never reuse an Actions GITHUB_TOKEN for cross-repo work.
    """
    require(isinstance(run_id, str) and UUID.fullmatch(run_id) is not None
            and isinstance(candidate_sha, str) and SHA.fullmatch(candidate_sha) is not None
            and isinstance(factory_sha, str) and SHA.fullmatch(factory_sha) is not None,
            "recovery_identity_invalid")

    run = one(read, "factory_runs", "id,task_id,status,candidate_commit,branch_name,metadata",
              "id", run_id)
    task = one(read, "factory_tasks", "id,project_id", "id", str(run.get("task_id")))
    project_id = str(task.get("project_id"))
    project = one(read, "factory_projects",
                  "id,project_key,project_kind,repository,is_active", "id", project_id)
    control = one(read, "factory_project_execution_controls",
                  "project_id,state,generation", "project_id", project_id)
    change_set = one(read, "factory_change_sets",
                     "id,project_id,status,candidate_commit,release_run_id,lease_owner,lease_expires_at",
                     "release_run_id", run_id)
    jobs = read("factory_specialist_lane_jobs?select=role,status,required,attempt_count,"
                "candidate_commit,lease_owner,lease_expires_at,completed_at,"
                "evidence,findings&run_id=eq." + quote(run_id, safe="") + "&limit=4")

    generation = control.get("generation")
    metadata = run.get("metadata")
    require(isinstance(metadata, dict) and type(generation) is int and generation > 0
            and project.get("is_active") is True and control.get("state") == "running"
            and metadata.get("execution_generation") == generation
            and metadata.get("source") == "change-set"
            and run.get("status") == "specialist_review_failed"
            and run.get("candidate_commit") == candidate_sha
            and not metadata.get("specialist_infrastructure_recovery_v1")
            and isinstance(metadata.get("specialist_lanes"), dict)
            and metadata["specialist_lanes"].get("required") is True
            and metadata["specialist_lanes"].get("candidate_commit") == candidate_sha
            and change_set.get("project_id") == project_id
            and change_set.get("release_run_id") == run_id
            and change_set.get("status") == "ci_pending"
            and change_set.get("candidate_commit") == candidate_sha
            and change_set.get("lease_owner") is None
            and change_set.get("lease_expires_at") is None,
            "source_run_or_epoch_not_recoverable")
    require(isinstance(jobs, list) and len(jobs) == 3
            and all(isinstance(row, dict) for row in jobs)
            and {row.get("role") for row in jobs} == ROLES
            and all(row.get("candidate_commit") == candidate_sha
                    and row.get("required") is True
                    and row.get("status") == "blocked"
                    and type(row.get("attempt_count")) is int
                    and row["attempt_count"] == 3
                    and row.get("lease_owner") is None
                    and row.get("lease_expires_at") is None
                    and isinstance(row.get("completed_at"), str)
                    and isinstance(row.get("evidence"), dict)
                    and str(row["evidence"].get("_factory_epoch")) == str(generation)
                    and isinstance(row.get("findings"), list)
                    and len(row["findings"]) == 1
                    and isinstance(row["findings"][0], dict)
                    and row["findings"][0].get("code") == "specialist_retry_exhausted"
                    for row in jobs),
            "specialist_jobs_not_only_infrastructure_exhausted")

    repository = project.get("repository")
    branch = run.get("branch_name")
    require(isinstance(repository, str) and re.fullmatch(
                r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is not None
            and repository != FACTORY_REPOSITORY
            and isinstance(project.get("project_key"), str)
            and isinstance(branch, str) and branch not in ("main", "master", "")
            and not branch.startswith("/") and ".." not in branch
            and metadata.get("change_set_id") == change_set.get("id"),
            "target_project_or_change_set_invalid")

    pr_usage = read("factory_tool_usage?select=metadata&run_id=eq." + quote(run_id, safe="")
                    + "&operation=eq.create_pr&order=created_at.desc&limit=1")
    require(isinstance(pr_usage, list) and len(pr_usage) == 1
            and isinstance(pr_usage[0].get("metadata"), dict),
            "original_pr_receipt_missing")
    pr_meta = pr_usage[0]["metadata"]
    pr_number = pr_meta.get("pr")
    original_head = pr_meta.get("head_sha")
    require(type(pr_number) is int and pr_number > 0
            and isinstance(original_head, str) and SHA.fullmatch(original_head) is not None,
            "original_pr_receipt_invalid")
    try:
        validate_create_pr_candidate(read=read, run_id=run_id, pr_number=pr_number,
                                     original_head=original_head,
                                     candidate_commit=candidate_sha,
                                     run_metadata=metadata)
    except (ValueError, TypeError, RuntimeError) as exc:
        raise SpecialistInfrastructureRecoveryBlocked(
            "original_candidate_lineage_not_verified") from exc

    # The Factory repair must already be merged and have passing push CI at
    # the CURRENT default branch, not merely exist on a PR candidate.
    factory_branch = github_get(FACTORY_REPOSITORY,
                                "/repos/" + FACTORY_REPOSITORY + "/branches/main")
    require(isinstance(factory_branch, dict)
            and (factory_branch.get("commit") or {}).get("sha") == factory_sha,
            "factory_fix_not_current_main")
    factory_ci = github_get(
        FACTORY_REPOSITORY, "/repos/" + FACTORY_REPOSITORY +
        "/actions/runs?head_sha=" + factory_sha + "&branch=main&per_page=100"
    )
    require(isinstance(factory_ci, dict)
            and isinstance(factory_ci.get("workflow_runs"), list)
            and any(isinstance(row, dict)
                    and row.get("name") == "validate"
                    and row.get("head_sha") == factory_sha
                    and row.get("event") == "push"
                    and row.get("status") == "completed"
                    and row.get("conclusion") == "success"
                    for row in factory_ci["workflow_runs"]),
            "merged_factory_source_ci_not_verified")

    pr = github_get(repository,
                    "/repos/" + repository + "/pulls/" + str(pr_number))
    require(isinstance(pr, dict)
            and pr.get("number") == pr_number
            and pr.get("state") == "open"
            and pr.get("merged") is False
            and (pr.get("head") or {}).get("sha") == candidate_sha
            and (pr.get("head") or {}).get("ref") == branch
            and ((pr.get("head") or {}).get("repo") or {}).get("full_name") == repository
            and (pr.get("base") or {}).get("ref") == "main"
            and ((pr.get("base") or {}).get("repo") or {}).get("full_name") == repository,
            "candidate_pr_exact_sha_or_branch_changed")

    # Independently fetch the CI run referenced by the prior durable
    # reconcile receipt. A passed standalone test is NOT a browser E2E.
    reconcile = read(
        "factory_tool_usage?select=metadata&run_id=eq." + quote(run_id, safe="")
        + "&operation=eq.reconcile_pr_candidate&order=created_at.desc&limit=1"
    )
    require(isinstance(reconcile, list) and len(reconcile) == 1
            and isinstance(reconcile[0].get("metadata"), dict),
            "candidate_ci_receipt_missing")
    ci_meta = reconcile[0]["metadata"]
    ci_run_id = ci_meta.get("ci_run_id")
    ci_job_id = ci_meta.get("ci_job_id")
    require(type(ci_run_id) is int and ci_run_id > 0
            and type(ci_job_id) is int and ci_job_id > 0
            and ci_meta.get("ci_conclusion") == "success"
            and ci_meta.get("repository") == repository
            and ci_meta.get("pr_number") in (pr_number, str(pr_number))
            and ci_meta.get("ci_sha") == candidate_sha,
            "candidate_ci_receipt_invalid")
    ci = github_get(repository, "/repos/" + repository +
                    "/actions/runs/" + str(ci_run_id))
    job_response = github_get(repository, "/repos/" + repository +
                              "/actions/runs/" + str(ci_run_id) + "/jobs?per_page=100")
    require(isinstance(ci, dict) and ci.get("head_sha") == candidate_sha
            and ci.get("event") == "pull_request"
            and ci.get("status") == "completed"
            and ci.get("conclusion") == "success"
            and isinstance(job_response, dict)
            and isinstance(job_response.get("jobs"), list)
            and any(isinstance(job, dict) and job.get("id") == ci_job_id
                    and job.get("status") == "completed"
                    and job.get("conclusion") == "success"
                    for job in job_response["jobs"]),
            "candidate_ci_exact_sha_not_verified")

    canonical = {
        "schema": "factory-specialist-infrastructure-source-v1",
        "run_id": run_id,
        "project_id": project_id,
        "project_key": project["project_key"],
        "repository": repository,
        "candidate_sha": candidate_sha,
        "factory_sha": factory_sha,
        "execution_generation": generation,
        "change_set_id": change_set["id"],
        "branch": branch,
        "pr_number": pr_number,
        "original_head_sha": original_head,
        "ci_run_id": ci_run_id,
        "ci_job_id": ci_job_id,
        "roles": sorted(ROLES),
        "prior_attempt_count_per_role": 3,
        "release_authorized": False,
    }
    digest = hashlib.sha256(json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()).hexdigest()
    return RecoverySources(
        run_id=run_id, candidate_sha=candidate_sha, factory_sha=factory_sha,
        execution_generation=generation, repository=repository,
        project_key=project["project_key"], pr_number=pr_number,
        ci_run_id=ci_run_id, evidence_digest=digest,
    )
