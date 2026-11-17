"""Independent B4 critical-E2E witness from real Factory Control Plane + GitHub.

The evidence is about the FACTORY'S delivery orchestration of a human-started
greenfield candidate, not a declaration that the greenfield application is
complete. No greenfield database or service is provisioned. No release is
authorized; critical_journeys remains a distinct, stricter criterion.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
    "release_policy_blocked", "awaiting_release", "released", "completed", "merged",
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
    witness_candidate_commit: str = ""
    non_runtime_witness_inherited: bool = False

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
            "snapshot_candidate_commit": self.witness_candidate_commit or self.candidate_commit,
            "exact_candidate_snapshot": not self.non_runtime_witness_inherited,
            "non_runtime_ancestry_independently_verified": self.non_runtime_witness_inherited,
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



def _recorded_at(row: dict) -> float:
    """Only control-plane timestamps qualify for same-wave evidence selection."""
    value = row.get("created_at")
    require(isinstance(value, str) and 12 <= len(value) <= 64,
            "b4_browser_wave_timestamp_missing")
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise B4GreenfieldE2EBlocked("b4_browser_wave_timestamp_invalid") from exc
    require(moment.tzinfo is not None, "b4_browser_wave_timestamp_unzoned")
    return moment.timestamp()


def _non_runtime_file(path: object) -> bool:
    """Fail closed: documentation, test and offline CI proof files only.

    Modifying any application, migration, dependency, deployment configuration
    or unknown executable path requires a NEW independent browser snapshot.
    """
    if not isinstance(path, str) or not re.fullmatch(r"[A-Za-z0-9_.\-/]+", path):
        return False
    if path.startswith("/") or any(segment in (".", "..", "") for segment in path.split("/")):
        return False
    if path == "README.md" or (path.startswith("docs/") and path.endswith(".md")):
        return True
    if path in (".github/workflows/validate.yml", ".github/workflows/validate.yaml"):
        return True
    if path.startswith(("tests/", "supabase/tests/")):
        return True
    if path.startswith("scripts/"):
        name = path.rsplit("/", 1)[-1]
        return name.startswith(("verify_", "check_")) and name.endswith((".sh", ".py"))
    return False


def _verify_non_runtime_ancestor(*, cross_repo_get, target_repo: str,
                                 predecessor: str, current: str) -> None:
    require(_sha(predecessor) and _sha(current) and predecessor != current,
            "b4_browser_witness_ancestor_invalid")
    # The Factory's GITHUB_TOKEN cannot read a private product repository.
    # This path MUST use the explicitly configured cross-repo read credential,
    # not silently fall back to the single-repo GitHub Actions token.
    require(callable(cross_repo_get) and REPO.fullmatch(target_repo) is not None,
            "b4_explicit_cross_repo_reader_required")
    comparison = _gh(cross_repo_get, "/repos/" + target_repo + "/compare/"
                     + predecessor + "..." + current)
    files = comparison.get("files")
    ahead = comparison.get("ahead_by")
    require(comparison.get("status") == "ahead"
            and comparison.get("behind_by") == 0
            and type(ahead) is int and 1 <= ahead <= 25
            and comparison.get("total_commits") == ahead
            and comparison.get("truncated") is not True
            and isinstance(files, list) and 1 <= len(files) <= 50,
            "b4_browser_ancestor_compare_incomplete")
    require(all(isinstance(row, dict)
                and row.get("status") in ("added", "modified", "removed", "renamed")
                and _non_runtime_file(row.get("filename"))
                and (row.get("status") != "renamed"
                     or _non_runtime_file(row.get("previous_filename")))
                for row in files),
            "b4_browser_witness_runtime_changed")


def _select_browser_wave(*, evaluations: list[dict], audit: list[dict],
                         candidate_commit: str) -> tuple[dict, dict | None]:
    successes = [e for e in evaluations
                 if e.get("eval_type") == "browser_e2e" and e.get("status") == "success"]
    # The first release candidate can have a single successful evaluation.
    # Recovery and multiwave journeys retain ALL older successful evaluations:
    # never interpret their count as proof of a forged extra browser run.
    if len(successes) == 1:
        return successes[0], None
    rebind = [a for a in audit
              if a.get("event_type") == "change_set.blocked_release_candidate.reconciled"
              and isinstance(a.get("payload"), dict)
              and a["payload"].get("candidate_commit") == candidate_commit
              and a["payload"].get("new_browser_evidence_required") is True
              and a["payload"].get("old_evidence_preserved") is True
              and a["payload"].get("release_authorized") is False]
    require(len(rebind) == 1, "b4_current_wave_rebind_missing_or_ambiguous")
    cutoff = _recorded_at(rebind[0])
    current = [e for e in successes
               if _recorded_at(e) > cutoff]
    require(len(current) == 1, "b4_current_wave_browser_success_not_unique")
    selected = current[0]
    require(any(a.get("event_type") == "preview.browser_evidence_recorded"
                and isinstance(a.get("payload"), dict)
                and a["payload"].get("status") == "success"
                and a["payload"].get("preview_url") == selected.get("baseline_ref")
                and a["payload"].get("detail") is None
                and _recorded_at(a) >= cutoff
                and abs(_recorded_at(a) - _recorded_at(selected)) < 180
                for a in audit), "b4_current_wave_browser_audit_missing")
    return selected, rebind[0]


def verify_b4_greenfield_e2e(*, repository: str, assessed_commit: str,
                             github_get, control_plane_get,
                             cross_repo_get=None) -> VerifiedGreenfieldE2E:
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
                cross_repo_get=cross_repo_get,
            ))
        except (B4GreenfieldE2EBlocked, KeyError, TypeError, ValueError) as exc:
            reasons.append(type(exc).__name__)
    require(len(valid) == 1, "b4_greenfield_verified_candidate_missing_or_ambiguous")
    return valid[0]


def _verify_project(project: dict, *, repository: str, assessed_commit: str,
                    github_get, cp, cross_repo_get=None) -> VerifiedGreenfieldE2E:
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
                github_get=github_get, cross_repo_get=cross_repo_get,
            ))
        except (B4GreenfieldE2EBlocked, KeyError, ValueError, TypeError):
            continue
    require(len(verified) == 1, "b4_real_change_set_e2e_missing_or_ambiguous")
    return verified[0]


def _verify_changeset(*, project_id: str, target_repo: str, cs: dict,
                      cp, repository: str, assessed_commit: str,
                      github_get, cross_repo_get=None) -> VerifiedGreenfieldE2E:
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
            and run.get("branch_name") == branch
            and run.get("status") in PREVIEW_COMPLETE_STATES
            and isinstance(runmeta, dict)
            and runmeta.get("source") == "change-set"
            and runmeta.get("change_set_id") == csid
            and runmeta.get("execution_generation") == epoch["generation"],
            "b4_run_not_at_verified_preview")
    # The original candidate is immutable. After a human merge the run's
    # current candidate is the real merge SHA, not the original PR HEAD.
    # Retain the original E2E PASS only when a released report proves both.
    merged_sha = None
    if run["status"] == "merged":
        require(cs.get("status") == "completed"
                and _sha(run.get("candidate_commit")),
                "b4_merged_run_missing_release_epoch")
        reports = _rows(cp, "factory_release_reports",
            "id,project_id,run_id,status,candidate_commit,report"
            "&run_id=eq." + quote(rid, safe="")
            + "&order=created_at.desc&limit=3", max_rows=3)
        require(len(reports) == 1, "b4_release_report_missing_or_ambiguous")
        report = reports[0]
        evidence = report.get("report")
        merged_sha = run["candidate_commit"]
        require(report.get("project_id") == project_id
                and report.get("run_id") == rid
                and report.get("candidate_commit") == sha
                and report.get("status") == "released"
                and isinstance(evidence, dict)
                and evidence.get("merge_sha") == merged_sha
                and evidence.get("released_by") == "observed_manual_merge",
                "b4_human_release_report_unverified")
    else:
        require(run.get("candidate_commit") == sha,
                "b4_preview_run_candidate_drift")
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
    audit = _rows(cp, "factory_audit_events",
        "id,event_type,payload,created_at"
        "&run_id=eq." + quote(rid, safe="")
        + "&order=created_at.desc&limit=70", max_rows=70)
    success, current_wave = _select_browser_wave(
        evaluations=evals, audit=audit, candidate_commit=sha,
    )
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
    verified_snapshots = []
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
                and _sha(evidence.get("candidate_commit"))
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
            verified_snapshots.append(snapshot)
    direct = [snap for snap in verified_snapshots
              if snap["evidence"]["candidate_commit"] == sha]
    inherited = False
    witness_candidate = sha
    if direct:
        snapshot = direct[0]
    else:
        # A newer release candidate can change ONLY offline tests/docs/validation
        # while still executing a fresh delivery browser_e2e evaluation.
        # Reuse the first-party browser snapshot only across a signed,
        # strictly verified non-runtime ancestry edge on the SAME Change Set.
        require(current_wave is not None,
                "b4_latest_candidate_independent_visual_witness_missing")
        lineage = current_wave["payload"]
        predecessor = lineage.get("previous_commit")
        require(_sha(predecessor) and predecessor != sha
                and lineage.get("change_set_id") == csid
                and lineage.get("pr_number") == release["pr_number"],
                "b4_browser_witness_rebind_provenance_invalid")
        older = [snap for snap in verified_snapshots
                 if snap["evidence"]["candidate_commit"] == predecessor]
        require(len(older) >= 1,
                "b4_independent_ancestral_visual_witness_missing")
        snapshot = older[0]
        require(any(a.get("event_type") in (
                        "preview.failed_candidate.reconciled",
                        "preview.oidc_origin_mismatch.browser_verified_resume",
                        "preview.external_feedback.browser_verified_resume")
                    and isinstance(a.get("payload"), dict)
                    and a["payload"].get("candidate_commit") == predecessor
                    and a["payload"].get("release_authorized") is False
                    and a["payload"].get("browser_snapshot_id",
                        a["payload"].get("snapshot_id")) == snapshot["id"]
                    and (a["payload"].get("historical_failures_preserved") is True
                         or a["payload"].get("original_browser_failure_preserved") is True)
                    for a in audit),
                "b4_ancestral_witness_recovery_audit_missing")
        _verify_non_runtime_ancestor(cross_repo_get=cross_repo_get,
                                     target_repo=target_repo,
                                     predecessor=predecessor,
                                     current=sha)
        inherited = True
        witness_candidate = predecessor
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
    require(any(a.get("event_type") == "preview.browser_evidence_recorded"
                and isinstance(a.get("payload"), dict)
                and a["payload"].get("status") == "success"
                and a["payload"].get("preview_url") == url
                for a in audit), "b4_real_browser_persistence_audit_missing")
    require(any(a.get("event_type")
                in ("preview.oidc_origin_mismatch.browser_verified_resume",
                    "preview.external_feedback.browser_verified_resume",
                    "preview.failed_candidate.reconciled")
                and isinstance(a.get("payload"), dict)
                and a["payload"].get("candidate_commit") == witness_candidate
                and a["payload"].get("release_authorized") is False
                and (
                    (a.get("event_type") != "preview.failed_candidate.reconciled"
                     and a["payload"].get("original_browser_failure_preserved") is True)
                    or (inherited
                        and a.get("event_type") == "preview.failed_candidate.reconciled"
                        and a["payload"].get("historical_failures_preserved") is True
                        and a["payload"].get("browser_snapshot_id") == snapshot["id"])
                )
                for a in audit), "b4_independent_recovery_audit_missing")
    if merged_sha is not None:
        require(any(a.get("event_type") == "release.human_merge_observed"
                    and isinstance(a.get("payload"), dict)
                    and a["payload"].get("merge_sha") == merged_sha
                    for a in audit), "b4_human_merge_audit_missing")
    return VerifiedGreenfieldE2E(
        repository=repository, assessed_commit=assessed_commit,
        project_id=project_id, delivery_run_id=rid, candidate_commit=sha,
        candidate_repository=target_repo, original_pr=release["pr_number"],
        browser_run_id=witness_run, visual_witness_id=snapshot["id"],
        preview_url=url, source_factory_sha=witness_sha,
        checks=tuple(sorted(REQUIRED_PREVIEW_CHECKS)),
        witness_candidate_commit=witness_candidate,
        non_runtime_witness_inherited=inherited,
    )


def verify_b4_critical_journeys(*, e2e: VerifiedGreenfieldE2E,
                                crm_traceability: VerifiedCriterionEvidence,
                                control_plane_get) -> VerifiedCriterionEvidence:
    """Full-source B4 release proof, deliberately unavailable before a human merge.

    A successful Preview or greenfield domain test NEVER suffices. This checks
    independently observed release, merged run, completed Change Set,
    operations snapshot, the original CRM V2 source verifier, and human audit.
    Product-specific functionality remains governed by its separate DoD.
    """
    require(type(e2e) is VerifiedGreenfieldE2E
            and type(crm_traceability) is VerifiedCriterionEvidence
            and crm_traceability.domain == "observability_operations"
            and crm_traceability.criterion == "traceability"
            and crm_traceability.repository == e2e.repository
            and crm_traceability.assessed_commit == e2e.assessed_commit
            and callable(control_plane_get),
            "b4_existing_and_greenfield_source_not_joined")
    rid = e2e.delivery_run_id
    pid = e2e.project_id
    orig = e2e.candidate_commit
    run = _one(control_plane_get, "factory_runs",
        "id,status,candidate_commit,task_id"
        "&id=eq." + quote(rid, safe="") + "&limit=2")
    merge_sha = run.get("candidate_commit")
    require(run.get("id") == rid and run.get("status") == "merged"
            and _sha(merge_sha) and merge_sha != orig,
            "b4_human_merge_not_observed")
    report = _one(control_plane_get, "factory_release_reports",
        "id,project_id,run_id,status,candidate_commit,report"
        "&run_id=eq." + quote(rid, safe="") + "&limit=2")
    facts = report.get("report")
    require(report.get("project_id") == pid
            and report.get("run_id") == rid
            and report.get("status") == "released"
            and report.get("candidate_commit") == orig
            and isinstance(facts, dict)
            and facts.get("merge_sha") == merge_sha
            and facts.get("released_by") == "observed_manual_merge",
            "b4_released_report_not_verified")
    cs = _one(control_plane_get, "factory_change_sets",
        "id,project_id,release_run_id,status,metadata"
        "&release_run_id=eq." + quote(rid, safe="") + "&limit=2")
    receipt = (cs.get("metadata") or {}).get("release")
    require(cs.get("project_id") == pid and cs.get("status") == "completed"
            and cs.get("release_run_id") == rid
            and isinstance(receipt, dict) and receipt.get("observed") is True
            and receipt.get("merge_sha") == merge_sha
            and receipt.get("run_id") == rid,
            "b4_change_set_not_completed_by_release")
    project = _one(control_plane_get, "factory_projects",
        "id,project_key,project_kind,repository,is_active,manifest"
        "&id=eq." + quote(pid, safe="") + "&limit=2")
    manifest = project.get("manifest")
    release = manifest.get("last_release") if isinstance(manifest, dict) else None
    require(project.get("is_active") is True
            and project.get("project_kind") == "greenfield"
            and project.get("repository") == e2e.candidate_repository
            and isinstance(release, dict)
            and manifest.get("reported_stage") == "operations"
            and release.get("run_id") == rid
            and release.get("merge_sha") == merge_sha
            and release.get("source") == "observed_human_merge",
            "b4_operations_project_observation_missing")
    audit = _rows(control_plane_get, "factory_audit_events",
        "id,event_type,payload"
        "&run_id=eq." + quote(rid, safe="")
        + "&order=created_at.desc&limit=70", max_rows=70)
    require(any(a.get("event_type") == "release.human_merge_observed"
                and isinstance(a.get("payload"), dict)
                and a["payload"].get("merge_sha") == merge_sha
                for a in audit), "b4_release_human_audit_missing")
    operations = _rows(control_plane_get, "factory_project_state_snapshots",
        "id,project_id,run_id,observed_stage,evidence,source_status"
        "&project_id=eq." + quote(pid, safe="")
        + "&run_id=eq." + quote(rid, safe="")
        + "&observed_stage=eq.operations&order=created_at.desc&limit=25", max_rows=25)
    require(any(s.get("project_id") == pid
                and s.get("run_id") == rid
                and s.get("observed_stage") == "operations"
                and isinstance(s.get("evidence"), list)
                and {"type": "human_release", "merge_sha": merge_sha} in s["evidence"]
                and isinstance(s.get("source_status"), dict)
                and s["source_status"].get("release") == "merged"
                for s in operations), "b4_independent_operations_snapshot_missing")
    return VerifiedCriterionEvidence(
        domain="functional_completeness", criterion="critical_journeys",
        repository=e2e.repository, assessed_commit=e2e.assessed_commit,
        verification_state="reviewed",
        source="independent_existing_crm_plus_greenfield_observed_human_release",
        evidence=(
            "https://github.com/" + e2e.repository + "/actions/runs/"
            + str(e2e.browser_run_id) + "#sha=" + e2e.assessed_commit,
            "https://github.com/" + e2e.candidate_repository
            + "/pull/" + str(e2e.original_pr) + "#sha=" + e2e.assessed_commit,
        ),
        retained_receipt={
            "schema": "factory-b4-independent-completed-critical-journeys-v1",
            "assessed_commit": e2e.assessed_commit,
            "greenfield_project_id": pid, "greenfield_run_id": rid,
            "greenfield_candidate_commit": orig, "human_merge_sha": merge_sha,
            "original_crm_traceability_source": crm_traceability.source,
            "critical_e2e_verified": True,
            "human_release_observed": True, "operations_observed": True,
            "model_calls": 0, "writes": 0, "automatic_merge": False,
        },
    )
