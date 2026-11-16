"""Independent B4 critical-E2E witness from real Factory Control Plane + GitHub.

The evidence is about the FACTORY'S delivery orchestration of a human-started
greenfield candidate, not a declaration that the greenfield application is
complete. No greenfield database or service is provisioned. No release is
authorized; critical_journeys remains a distinct, stricter criterion.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote
import re

from .product_readiness_certification import VerifiedCriterionEvidence

SHA = re.compile(r"[0-9a-f]{40}\Z")
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
REQUIRED_PREVIEW_CHECKS = frozenset({
    "page_load", "http_status", "body_visible", "expected_text", "console_clean"
})
SPECIALISTS = frozenset({"specialist_security", "specialist_qa", "specialist_operations"})
# This is a deliberately limited evidence contract for a *real* delivered
# greenfield workflow. It must not reinterpret a CI job as an app E2E test.
PREVIEW_COMPLETE_STATES = frozenset({
    "release_policy_blocked", "awaiting_release", "released", "completed",
})
SOURCE_WORKFLOW = ".github/workflows/console-browser-evidence.yml"
ALLOWED_CROSS_REPO_PREFIX = "https://github.com/"


class B4GreenfieldE2EBlocked(RuntimeError):
    """All errors are internal fixed vocabulary; no private project data leaked."""


def require(value: object, reason: str) -> None:
    if value is not True:
        raise B4GreenfieldE2EBlocked(reason)


def _rows(get, table: str, query: str, *, max_rows: int) -> list[dict]:
    rows = get(table + "?select=" + query)
    require(isinstance(rows, list) and len(rows) <= max_rows
            and all(isinstance(row, dict) for row in rows),
            "b4_control_plane_rows_unverifiable")
    return rows


def _one(get, table: str, query: str) -> dict:
    rows = _rows(get, table, query, max_rows=2)
    require(len(rows) == 1, "b4_critical_identity_missing_or_ambiguous")
    return rows[0]


def _identity(value: object) -> bool:
    return isinstance(value, str) and UUID.fullmatch(value) is not None


def _sha(value: object) -> bool:
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def _gh(get, path: str) -> dict:
    value = get(path)
    require(isinstance(value, dict), "b4_github_response_unverifiable")
    return value


@dataclass(frozen=True)
class VerifiedGreenfieldE2E:
    repository: str
    assessed_commit: str
    project_id: str
    delivery_run_id: str
    candidate_commit: str
    candidate_repository: str
    original_pr: int
    browser_run_id: int
    visual_witness_id: str
    preview_url: str
    source_factory_sha: str
    checks: tuple[str, ...]

    def receipt(self) -> dict:
        return {
            "schema": "factory-b4-independent-greenfield-e2e-v1",
            "repository": self.repository,
            "assessed_commit": self.assessed_commit,
            "project_id": self.project_id,
            "delivery_run_id": self.delivery_run_id,
            "candidate_repository": self.candidate_repository,
            "candidate_commit": self.candidate_commit,
            "candidate_pr": self.original_pr,
            "independent_browser_run_id": self.browser_run_id,
            "independent_snapshot_id": self.visual_witness_id,
            "source_factory_commit": self.source_factory_sha,
            "verified_checks": list(self.checks),
            "greenfield_product_ready_inferred": False,
            "critical_journeys_certified": False,
            "production_release_authorized": False,
            "production_merge_observed": False,
            "writes": 0,
            "paid_calls": 0,
        }

    def criterion(self) -> VerifiedCriterionEvidence:
        return VerifiedCriterionEvidence(
            domain="test_strategy",
            criterion="critical_e2e",
            repository=self.repository,
            assessed_commit=self.assessed_commit,
            verification_state="executed",
            source="independent_factory_live_greenfield_to_preview_browser_plus_domain_e2e",
            evidence=(
                "https://github.com/" + self.repository + "/actions/runs/"
                + str(self.browser_run_id) + "#sha=" + self.assessed_commit,
                ALLOWED_CROSS_REPO_PREFIX + self.candidate_repository + "/pull/"
                + str(self.original_pr) + "#sha=" + self.assessed_commit,
            ),
            retained_receipt=self.receipt(),
        )


def _validate_source_run(*, github_get, factory: str, assessed_commit: str,
                         source_commit: str, browser_run_id: int,
                         browser_request_id: str) -> None:
    require(_sha(source_commit) and type(browser_run_id) is int
            and browser_run_id > 0 and _identity(browser_request_id),
            "b4_browser_source_identity_invalid")
    run = _gh(github_get, "/repos/" + factory + "/actions/runs/" + str(browser_run_id))
    require(run.get("id") == browser_run_id
            and run.get("name") == "Console evidence " + browser_request_id
            and run.get("path") == SOURCE_WORKFLOW
            and run.get("event") == "workflow_dispatch"
            and run.get("head_sha") == source_commit
            and run.get("status") == "completed"
            and run.get("conclusion") == "success"
            and (run.get("repository") or {}).get("full_name") == factory,
            "b4_browser_workflow_not_independently_verified")
    jobs = _gh(github_get, "/repos/" + factory + "/actions/runs/"
               + str(browser_run_id) + "/jobs?per_page=100")
    raw = jobs.get("jobs")
    require(type(jobs.get("total_count")) is int
            and jobs["total_count"] == 1
            and isinstance(raw, list) and len(raw) == 1,
            "b4_browser_job_inventory_incomplete")
    job = raw[0]
    require(isinstance(job, dict)
            and job.get("name") == "browser-evidence"
            and job.get("head_sha") == source_commit
            and job.get("status") == "completed"
            and job.get("conclusion") == "success"
            and isinstance(job.get("steps"), list)
            and any(s.get("name") == "Verify exact protected Preview"
                    and s.get("conclusion") == "success"
                    for s in job["steps"] if isinstance(s, dict)),
            "b4_real_browser_step_not_executed")
    # Any main SHA after the witness must descend from the exact signed
    # factory workflow commit. A different root, reset or unrelated branch
    # cannot reuse it.
    if source_commit != assessed_commit:
        comparison = _gh(github_get, "/repos/" + factory + "/compare/"
                         + source_commit + "..." + assessed_commit)
        require(comparison.get("status") == "ahead"
                and comparison.get("behind_by") == 0
                and type(comparison.get("ahead_by")) is int
                and 1 <= comparison["ahead_by"] <= 300,
                "b4_browser_verifier_commit_not_ancestor")


def verify_b4_greenfield_e2e(*, repository: str, assessed_commit: str,
                             github_get, control_plane_get) -> VerifiedGreenfieldE2E:
    """Promote only executed critical_e2e; never infer critical_journeys.

    A positive proof needs a human-decided project, real multi-wave Change Set,
    independent exact-SHA CI/quality/specialists, a recovered browser incident,
    a recorded successful delivery-run browser evaluation, AND an independently
    successful GitHub-owned Playwright workflow on the same candidate/URL.
    All data is independently read, bounded and identity-joined.
    """
    require(isinstance(repository, str) and REPO.fullmatch(repository) is not None
            and _sha(assessed_commit) and callable(github_get)
            and callable(control_plane_get), "b4_source_configuration_invalid")
    projects = _rows(control_plane_get, "factory_projects",
        "id,project_key,project_kind,repository,is_active,manifest"
        "&project_kind=eq.greenfield&is_active=eq.true&limit=15", max_rows=15)
    # The Factory may host many products; a candidate cannot be selected by a
    # hardcoded business name. Only exact operational witnesses qualify.
    reasons = []
    valid = []
    for project in projects:
        try:
            valid.append(_verify_project(
                project, repository=repository, assessed_commit=assessed_commit,
                github_get=github_get, cp=control_plane_get,
            ))
        except (B4GreenfieldE2EBlocked, KeyError, TypeError, ValueError) as exc:
            reasons.append(type(exc).__name__)
    require(len(valid) == 1, "b4_greenfield_verified_candidate_missing_or_ambiguous")
    return valid[0]


def _verify_project(project: dict, *, repository: str, assessed_commit: str,
                    github_get, cp) -> VerifiedGreenfieldE2E:
    pid = project.get("id")
    target = project.get("repository")
    manifest = project.get("manifest")
    require(_identity(pid) and isinstance(target, str)
            and REPO.fullmatch(target) is not None
            and target != repository
            and project.get("project_kind") == "greenfield"
            and project.get("is_active") is True
            and isinstance(manifest, dict)
            and manifest.get("source") == "factory-console",
            "b4_not_human_originated_greenfield")
    decisions = manifest.get("human_decisions")
    require(isinstance(decisions, list) and 1 <= len(decisions) <= 20
            and any(isinstance(d, dict)
                    and _identity(d.get("gate_id"))
                    and isinstance(d.get("resolved_at"), str)
                    and isinstance(d.get("resolved_by"), str)
                    and bool(d["resolved_by"].strip())
                    for d in decisions),
            "b4_human_product_decision_missing")
    preview_policy = manifest.get("preview")
    require(isinstance(preview_policy, dict)
            and preview_policy.get("required") is True
            and preview_policy.get("provider") == "vercel"
            and preview_policy.get("mode") == "github",
            "b4_preview_policy_not_required")

    changes = _rows(cp, "factory_change_sets",
        "id,project_id,root_task_id,release_run_id,status,candidate_commit,"
        "integration_branch,metadata"
        "&project_id=eq." + quote(pid, safe="")
        + "&order=created_at.desc&limit=25", max_rows=25)
    verified = []
    for cs in changes:
        try:
            verified.append(_verify_changeset(
                project_id=pid, target_repo=target, cs=cs, cp=cp,
                repository=repository, assessed_commit=assessed_commit,
                github_get=github_get,
            ))
        except (B4GreenfieldE2EBlocked, KeyError, ValueError, TypeError):
            continue
    require(len(verified) == 1, "b4_real_change_set_e2e_missing_or_ambiguous")
    return verified[0]


def _verify_changeset(*, project_id: str, target_repo: str, cs: dict,
                      cp, repository: str, assessed_commit: str,
                      github_get) -> VerifiedGreenfieldE2E:
    csid = cs.get("id")
    rid = cs.get("release_run_id")
    sha = cs.get("candidate_commit")
    branch = cs.get("integration_branch")
    metadata = cs.get("metadata")
    require(_identity(csid) and _identity(rid)
            and _identity(cs.get("root_task_id")) and _sha(sha)
            and cs.get("project_id") == project_id
            and cs.get("status") in ("ci_pending", "awaiting_release", "completed")
            and isinstance(branch, str) and branch.startswith("factory/change-set-")
            and isinstance(metadata, dict),
            "b4_candidate_lifecycle_invalid")
    release = metadata.get("integration_release_request")
    epoch = metadata.get("integration_epoch_receipt")
    require(isinstance(release, dict) and isinstance(epoch, dict)
            and release.get("candidate_commit") == sha
            and release.get("branch") == branch
            and isinstance(release.get("pr_number"), int)
            and release["pr_number"] > 0
            and release.get("issue_number", 0) > 0
            and epoch.get("candidate_commit") == sha
            and epoch.get("project_id") == project_id
            and type(epoch.get("generation")) is int
            and epoch["generation"] >= 1
            and type(epoch.get("wave")) is int and epoch["wave"] >= 2,
            "b4_multiwave_release_receipt_inconsistent")
    run = _one(cp, "factory_runs",
        "id,task_id,status,branch_name,candidate_commit,metadata"
        "&id=eq." + quote(rid, safe="") + "&limit=2")
    runmeta = run.get("metadata")
    require(run.get("id") == rid
            and run.get("task_id") == cs["root_task_id"]
            and run.get("candidate_commit") == sha
            and run.get("branch_name") == branch
            and run.get("status") in PREVIEW_COMPLETE_STATES
            and isinstance(runmeta, dict)
            and runmeta.get("source") == "change-set"
            and runmeta.get("change_set_id") == csid
            and runmeta.get("execution_generation") == epoch["generation"],
            "b4_run_not_at_verified_preview")
    # These privileged writes were issued by independent existing Factory
    # workers; never accept a raw uploaded manifest in their place.
    evals = _rows(cp, "factory_evaluations",
        "id,eval_type,status,baseline_ref,result,created_at"
        "&run_id=eq." + quote(rid, safe="")
        + "&order=created_at.desc&limit=70", max_rows=70)
    require(len(evals) >= 6, "b4_real_evaluations_incomplete")
    for kind, allowed in (
        ("github_ci", "success"), ("quality_gate", "success"),
        ("specialist_security", "passed"), ("specialist_qa", "passed"),
        ("specialist_operations", "passed"),
    ):
        matches = [e for e in evals
                   if e.get("eval_type") == kind
                   and e.get("status") == allowed
                   and e.get("baseline_ref") == sha]
        require(len(matches) == 1, "b4_exact_sha_quality_lane_missing")
    ci = next(e for e in evals if e.get("eval_type") == "github_ci"
              and e.get("status") == "success" and e.get("baseline_ref") == sha)
    require(isinstance(ci.get("result"), dict)
            and ci["result"].get("head_sha") == sha
            and ci["result"].get("pr") == release["pr_number"]
            and ci["result"].get("ci_state") == "success",
            "b4_ci_attestation_not_bound_to_pr")
    require(any(e.get("eval_type") == "browser_e2e"
                and e.get("status") == "failure" for e in evals),
            "b4_recovery_negative_path_missing")
    browser_success = [e for e in evals if e.get("eval_type") == "browser_e2e"
                       and e.get("status") == "success"]
    require(len(browser_success) == 1, "b4_browser_success_missing_or_ambiguous")
    success = browser_success[0]
    browser = success.get("result")
    require(isinstance(browser, dict)
            and browser.get("detail") is None
            and isinstance(browser.get("checks"), list)
            and set(browser["checks"]) == REQUIRED_PREVIEW_CHECKS
            and len(browser["checks"]) == len(REQUIRED_PREVIEW_CHECKS)
            and isinstance(browser.get("preview_url"), str)
            and browser["preview_url"].startswith("https://")
            and browser.get("preview_url") == success.get("baseline_ref"),
            "b4_browser_e2e_checks_incomplete")
    url = browser["preview_url"]
    require(re.fullmatch(r"https://[a-z0-9][a-z0-9-]*\.vercel\.app", url) is not None,
            "b4_preview_hostname_untrusted")
    snapshots = _rows(cp, "factory_project_state_snapshots",
        "id,project_id,observed_stage,run_id,evidence,source_status,constraints,created_at"
        "&project_id=eq." + quote(project_id, safe="")
        + "&observed_stage=eq.verification&order=created_at.desc&limit=30", max_rows=30)
    candidate = []
    for snapshot in snapshots:
        evidence = snapshot.get("evidence")
        src = snapshot.get("source_status")
        constraints = snapshot.get("constraints")
        if not (isinstance(evidence, dict) and isinstance(src, dict)
                and isinstance(constraints, dict)):
            continue
        preview = evidence.get("preview")
        if (snapshot.get("project_id") == project_id
                and _identity(snapshot.get("id"))
                and snapshot.get("run_id") is None
                and evidence.get("candidate_commit") == sha
                and evidence.get("target_repository") == target_repo
                and isinstance(preview, dict)
                and preview.get("url") == url
                and preview.get("status") == "browser_verified"
                and preview.get("provider") == "vercel"
                and src.get("github_target") == "verified"
                and src.get("vercel_preview") == "resolved"
                and src.get("browser_visual_validation") == "success"
                and constraints.get("product_ready_inferred") is False
                and constraints.get("production_merge_authorized") is False):
            candidate.append(snapshot)
    require(len(candidate) >= 1, "b4_separate_visual_witness_missing")
    snapshot = candidate[0]
    visual = snapshot["evidence"]["preview"]
    witness_sha = visual.get("verifier_factory_commit")
    witness_run = visual.get("browser_verifier_run_id")
    request_id = visual.get("browser_request_id")
    _validate_source_run(
        github_get=github_get, factory=repository,
        assessed_commit=assessed_commit, source_commit=witness_sha,
        browser_run_id=witness_run, browser_request_id=request_id,
    )
    # Failure and recovery remain immutable, and the newer successful
    # delivery-run evaluation is never forged by the one-shot recovery RPC.
    audit = _rows(cp, "factory_audit_events",
        "id,event_type,payload,created_at"
        "&run_id=eq." + quote(rid, safe="")
        + "&order=created_at.desc&limit=70", max_rows=70)
    require(any(a.get("event_type") == "preview.browser_evidence_recorded"
                and isinstance(a.get("payload"), dict)
                and a["payload"].get("status") == "success"
                and a["payload"].get("preview_url") == url
                for a in audit), "b4_real_browser_persistence_audit_missing")
    require(any(a.get("event_type")
                in ("preview.oidc_origin_mismatch.browser_verified_resume",
                    "preview.external_feedback.browser_verified_resume")
                and isinstance(a.get("payload"), dict)
                and a["payload"].get("candidate_commit") == sha
                and a["payload"].get("release_authorized") is False
                and a["payload"].get("original_browser_failure_preserved") is True
                for a in audit), "b4_independent_recovery_audit_missing")
    return VerifiedGreenfieldE2E(
        repository=repository, assessed_commit=assessed_commit,
        project_id=project_id, delivery_run_id=rid, candidate_commit=sha,
        candidate_repository=target_repo, original_pr=release["pr_number"],
        browser_run_id=witness_run, visual_witness_id=snapshot["id"],
        preview_url=url, source_factory_sha=witness_sha,
        checks=tuple(sorted(REQUIRED_PREVIEW_CHECKS)),
    )
