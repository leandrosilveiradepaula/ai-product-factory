"""Independent GET-only audit of a real, OWNER-authorized native Journey V2.

This deliberately does not reinterpret the legacy JourneyReader's bootstrap run
as a V2 Start. Every positive statement requires immutable Control Plane
lineage, authenticated GitHub source/CI and a verified post-merge browser
snapshot. This report is never a global product-ready certificate.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import quote

from .autonomy_journey import SHA
from .autonomy_journey_reader import SupabaseJourneyReader, _uuid
from .github_loop import CIState
from .github_owner_start import (
    COMMAND, FACTORY_REPO, ISSUE_NUMBER, OWNER_ID, OWNER_LOGIN, request_uuid,
)
from .github_rest import GitHubRestAdapter
from .journey_candidate_provenance import verify_copied_work_unit_waves

KEY = re.compile(r"[a-z0-9][a-z0-9-]{1,119}\Z", re.ASCII)
DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
MAX_UNITS = 30


class EvidenceBlocked(ValueError):
    """Typed, redacted failure; source payloads are never reported."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise EvidenceBlocked(code)


def is_sha(value: object) -> bool:
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def is_digest(value: object) -> bool:
    return isinstance(value, str) and DIGEST.fullmatch(value) is not None


def safe_paths(paths: object) -> bool:
    return (
        isinstance(paths, list) and bool(paths) and len(paths) <= 120
        and len(set(paths)) == len(paths)
        and all(
            isinstance(path, str) and bool(path) and len(path) <= 240
            and not path.startswith("/") and "\\" not in path
            and all(part not in ("", ".", "..") for part in path.split("/"))
            for path in paths
        )
    )


def one(reader: SupabaseJourneyReader, table: str, select: str, filters: str, code: str) -> dict:
    rows = reader._get(table + "?select=" + select + "&" + filters, limit=2)
    require(len(rows) == 1, code)
    return rows[0]


def rows(reader: SupabaseJourneyReader, table: str, select: str, filters: str,
         *, limit: int, code: str) -> list[dict]:
    found = reader._get(table + "?select=" + select + "&" + filters, limit=limit)
    require(0 < len(found) < limit, code)
    return found


def _check_owner_intake(*, reader, factory_github, journey: dict,
                        project_key: str, project_id: str) -> dict:
    comment_id = journey.get("auth_event_id")
    require(
        journey.get("request_source") == "github-owner"
        and journey.get("auth_actor_ref") == "github-owner"
        and journey.get("issue_repository") == FACTORY_REPO
        and journey.get("issue_number") == ISSUE_NUMBER
        and isinstance(comment_id, str) and comment_id.isascii()
        and comment_id.isdecimal() and str(int(comment_id)) == comment_id
        and int(comment_id) > 0,
        "owner_intake_identity",
    )
    comment = factory_github._call(
        "GET", f"/repos/{FACTORY_REPO}/issues/comments/{comment_id}"
    )
    user = comment.get("user") if isinstance(comment, dict) else None
    require(
        isinstance(comment, dict) and comment.get("id") == int(comment_id)
        and comment.get("author_association") == "OWNER"
        and comment.get("issue_url") == (
            f"https://api.github.com/repos/{FACTORY_REPO}/issues/{ISSUE_NUMBER}"
        )
        and isinstance(user, dict) and user.get("id") == OWNER_ID
        and user.get("login") == OWNER_LOGIN,
        "owner_comment_not_verified",
    )
    body = comment.get("body")
    require(isinstance(body, str) and len(body.encode("utf-8")) <= 25000,
            "owner_comment_invalid")
    normalized = body.replace("\r\n", "\n")
    header, newline, request = normalized.partition("\n")
    match = COMMAND.fullmatch(header)
    request = request.strip()
    require(
        bool(newline) and match is not None and match.group(1) == project_key
        and 1 <= len(request) <= 6000
        and not any((ord(char) < 32 and char not in "\n\t") or ord(char) == 127
                    for char in normalized),
        "owner_command_invalid",
    )
    digest = hashlib.sha256(request.encode("utf-8")).hexdigest()
    snapshot = journey.get("request_snapshot")
    require(
        journey.get("request_id") == request_uuid(ISSUE_NUMBER, int(comment_id))
        and journey.get("request_digest") == digest
        and isinstance(snapshot, dict)
        and snapshot.get("text") == request
        and snapshot.get("digest") == digest
        and snapshot.get("source") == "github-owner"
        and snapshot.get("authorization_event_id") == comment_id
        and snapshot.get("control_issue_repository") == FACTORY_REPO
        and snapshot.get("control_issue_number") == ISSUE_NUMBER,
        "owner_request_digest_mismatch",
    )
    events = rows(
        reader, "factory_audit_events",
        "id,project_id,task_id,run_id,event_type,actor_type,actor_ref,payload,created_at",
        "project_id=eq." + project_id
        + "&event_type=in.(journey.intake_accepted,journey.source_bound)"
        + "&created_at=gte." + quote(journey["created_at"], safe="")
        + "&order=created_at.asc,id.asc",
        limit=51, code="v2_intake_inventory_unavailable",
    )
    intake = [
        e for e in events if e.get("event_type") == "journey.intake_accepted"
        and isinstance(e.get("payload"), dict)
        and e["payload"].get("journey_id") == journey["id"]
    ]
    bound = [
        e for e in events if e.get("event_type") == "journey.source_bound"
        and isinstance(e.get("payload"), dict)
        and e["payload"].get("journey_id") == journey["id"]
    ]
    require(len(intake) == 1 and len(bound) == 1, "v2_intake_or_binding_duplicate")
    e, b = intake[0], bound[0]
    require(
        e.get("actor_type") == "human" and e.get("actor_ref") == "github-owner"
        and e.get("run_id") is None and e.get("task_id") is None
        and e.get("created_at") == journey["created_at"]
        and e["payload"] == {
            "state": "awaiting_source", "source": "github-owner",
            "journey_id": journey["id"], "request_id": journey["request_id"],
        },
        "v2_intake_receipt_mismatch",
    )
    binding = journey["binding"]
    require(
        b.get("actor_type") == "system" and b.get("actor_ref") == "journey-binder"
        and b.get("project_id") == project_id
        and isinstance(b.get("run_id"), str)
        and b["payload"].get("request_id") == journey["request_id"]
        and b["payload"].get("source_commit") == journey["source_commit"]
        and b["payload"].get("preview_base_ref") == binding["preview_base_ref"]
        and is_digest(b["payload"].get("binding_digest")),
        "v2_source_binding_receipt_mismatch",
    )
    return b


def _check_lineage(*, reader, project: dict, journey: dict, bound: dict) -> tuple[dict, dict, dict, list[dict], list[dict]]:
    pid, jid = project["id"], journey["id"]
    binding = journey.get("binding")
    require(
        journey.get("state") == "preview_verified"
        and journey.get("production_release_sha") is None
        and journey.get("binding_version") == 2
        and type(journey.get("execution_generation")) is int
        and journey["execution_generation"] > 0
        and type(journey.get("project_policy_version")) is int
        and journey["project_policy_version"] > 0
        and is_sha(journey.get("source_commit"))
        and is_sha(journey.get("candidate_commit"))
        and is_digest(journey.get("policy_digest"))
        and isinstance(binding, dict),
        "v2_journey_not_preview_verified",
    )
    exact = {
        "journey_id": jid, "project_id": pid,
        "request_id": journey["request_id"],
        "repository": project["repository"],
        "source_repository": project["repository"],
        "source_commit": journey["source_commit"],
        "policy_digest": journey["policy_digest"],
        "policy_version": journey["project_policy_version"],
        "binding_version": 2,
        "execution_generation": journey["execution_generation"],
        "release_base_ref": "main",
    }
    require(
        all(binding.get(key) == value for key, value in exact.items())
        and isinstance(binding.get("integration_branch"), str)
        and binding["integration_branch"] == "factory/journey-" + jid
        and isinstance(binding.get("preview_base_ref"), str)
        and binding["preview_base_ref"].startswith("preview/")
        and binding["preview_base_ref"] != "preview/",
        "v2_immutable_binding_mismatch",
    )
    control = one(
        reader, "factory_project_execution_controls", "project_id,state,generation",
        "project_id=eq." + pid, "v2_control_unavailable",
    )
    require(
        control.get("state") == "running"
        and control.get("generation") == journey["execution_generation"],
        "v2_control_epoch_revoked",
    )
    cs = one(
        reader, "factory_change_sets",
        "id,project_id,root_task_id,release_run_id,journey_id,status,source_commit,"
        "candidate_commit,integration_branch,metadata",
        "journey_id=eq." + jid, "v2_change_set_not_unique",
    )
    epoch = (cs.get("metadata") or {}).get("integration_epoch_receipt")
    require(
        cs.get("project_id") == pid and cs.get("journey_id") == jid
        and cs.get("status") == "completed"
        and cs.get("source_commit") == journey["source_commit"]
        and cs.get("candidate_commit") == journey["candidate_commit"]
        and cs.get("integration_branch") == binding["integration_branch"]
        and isinstance(epoch, dict)
        and epoch.get("generation") == journey["execution_generation"]
        and epoch.get("project_id") == pid
        and epoch.get("candidate_commit") == journey["candidate_commit"],
        "v2_change_set_epoch_mismatch",
    )
    root_id, release_id = _uuid(cs.get("root_task_id")), _uuid(cs.get("release_run_id"))
    root = one(
        reader, "factory_tasks", "id,project_id,parent_task_id,journey_id,status,risk",
        "id=eq." + root_id, "v2_root_task_missing",
    )
    risk = root.get("risk") or {}
    require(
        root.get("project_id") == pid and root.get("journey_id") == jid
        and root.get("status") == "integrated"
        and root.get("parent_task_id") is None
        and isinstance(risk, dict)
        and not any(risk.get(key) is True or risk.get(key) == "true" for key in (
            "destructive_data_change", "expands_sensitive_access",
            "material_requirement_change", "new_paid_service",
        )),
        "v2_root_task_not_terminal",
    )
    source_run = one(
        reader, "factory_runs", "id,project_id,task_id,status",
        "id=eq." + _uuid(bound["run_id"]), "v2_bound_run_missing",
    )
    require(
        source_run.get("project_id") == pid
        and source_run.get("task_id") == root_id,
        "v2_source_run_not_root",
    )
    run = one(
        reader, "factory_runs",
        "id,project_id,task_id,status,candidate_commit,branch_name,metadata",
        "id=eq." + release_id, "v2_release_run_missing",
    )
    require(
        run.get("project_id") == pid
        and run.get("task_id") == root_id
        and run.get("status") == "integrated"
        and run.get("candidate_commit") == journey["candidate_commit"]
        and run.get("branch_name") == binding["integration_branch"]
        and isinstance(run.get("metadata"), dict)
        and run["metadata"].get("change_set_id") == cs["id"],
        "v2_release_run_lineage_mismatch",
    )
    units = rows(
        reader, "factory_change_set_work_units",
        "id,change_set_id,task_id,run_id,status,output_commit,changed_files,created_at",
        "change_set_id=eq." + cs["id"] + "&order=created_at.asc,id.asc",
        limit=MAX_UNITS + 1, code="v2_work_units_missing_or_unbounded",
    )
    require(
        len({u.get("id") for u in units}) == len(units)
        and len({u.get("task_id") for u in units}) == len(units)
        and all(
            u.get("status") in ("completed", "integrated")
            and u.get("change_set_id") == cs["id"]
            and is_sha(u.get("output_commit"))
            and safe_paths(u.get("changed_files"))
            for u in units
        ),
        "v2_work_units_not_completed",
    )
    task_ids = {_uuid(u.get("task_id")) for u in units}
    unit_runs = {_uuid(u.get("run_id")) for u in units}
    tasks = rows(
        reader, "factory_tasks", "id,project_id,parent_task_id,journey_id,status",
        "id=in.(" + ",".join(sorted(task_ids)) + ")",
        limit=MAX_UNITS + 1, code="v2_unit_tasks_unavailable",
    )
    runs = rows(
        reader, "factory_runs", "id,project_id,task_id,status",
        "id=in.(" + ",".join(sorted(unit_runs)) + ")",
        limit=MAX_UNITS + 1, code="v2_unit_runs_unavailable",
    )
    task_by_id = {t["id"]: t for t in tasks}
    run_by_id = {r["id"]: r for r in runs}
    require(
        len(task_by_id) == len(units) and len(run_by_id) == len(units)
        and all(
            (task_by_id[u["task_id"]].get("project_id") == pid
             and task_by_id[u["task_id"]].get("journey_id") == jid
             and task_by_id[u["task_id"]].get("parent_task_id") == root_id
             and task_by_id[u["task_id"]].get("status") == "integrated"
             and run_by_id[u["run_id"]].get("project_id") == pid
             and run_by_id[u["run_id"]].get("task_id") == u["task_id"]
             and run_by_id[u["run_id"]].get("status") == "completed")
            for u in units
        ),
        "v2_cross_journey_work_unit",
    )
    root_runs = rows(
        reader, "factory_runs", "id,project_id,task_id,status",
        "task_id=eq." + root_id,
        limit=31, code="v2_root_run_inventory_unbounded",
    )
    require(
        all(r.get("project_id") == pid and r.get("task_id") == root_id for r in root_runs)
        and release_id in {r["id"] for r in root_runs},
        "v2_root_run_inventory_mismatch",
    )
    root_run_ids = sorted(_uuid(r["id"]) for r in root_runs)
    receipts = rows(
        reader, "factory_tool_usage", "id,run_id,operation,metadata,created_at",
        "run_id=in.(" + ",".join(root_run_ids) + ")&operation=eq.create_pr&order=id.asc",
        limit=18, code="v2_pr_wave_inventory_unavailable",
    )
    require(
        all(r.get("run_id") in root_run_ids for r in receipts)
        and len({r["id"] for r in receipts}) == len(receipts),
        "v2_pr_wave_cross_lineage",
    )
    return cs, run, root, units, receipts


def _check_delivery(*, reader, github, factory_github, project: dict,
                    journey: dict, cs: dict, run: dict,
                    units: list[dict], receipts: list[dict]) -> dict:
    pid, sha = project["id"], journey["candidate_commit"]
    integration = (run.get("metadata") or {}).get("nonproduction_integration")
    other = (cs.get("metadata") or {}).get("nonproduction_integration")
    require(
        isinstance(integration, dict) and integration == other
        and integration.get("repository") == project["repository"]
        and integration.get("candidate_commit") == sha
        and integration.get("head_sha") == sha
        and integration.get("head_ref") == cs["integration_branch"]
        and integration.get("base_ref") == journey["binding"]["preview_base_ref"]
        and integration.get("merged") is True
        and integration.get("environment") == "preview"
        and integration.get("production_released") is False
        and integration.get("production_release_completed") is False
        and is_sha(integration.get("merge_sha"))
        and integration.get("merge_sha") != sha
        and str(integration.get("pr_number", "")).isdigit(),
        "v2_preview_merge_receipt_inconsistent",
    )
    pr_number = int(integration["pr_number"])
    require(pr_number > 0, "v2_pr_number_invalid")
    pr = github.get_pull_request(pr_number)
    require(
        pr.number == pr_number and pr.merged is True and pr.state == "closed"
        and pr.head_sha == sha and pr.merge_commit_sha == integration["merge_sha"]
        and pr.head_ref == cs["integration_branch"]
        and pr.base_ref == integration["base_ref"]
        and pr.head_repository == project["repository"]
        and pr.draft is False,
        "v2_github_pr_identity_mismatch",
    )
    require(github.get_ci_state(pr_number) == CIState.SUCCESS, "v2_exact_ci_not_green")
    require(
        verify_copied_work_unit_waves(
            github, final_candidate=sha, units=units,
            receipts=receipts, change_set_id=cs["id"], pr_number=pr_number,
        ),
        "v2_work_unit_bytes_not_verified",
    )
    evals = rows(
        reader, "factory_evaluations",
        "id,run_id,eval_type,status,baseline_ref,result,created_at",
        "run_id=eq." + run["id"]
        + "&eval_type=in.(github_ci,quality_gate,browser_e2e)&order=created_at.asc,id.asc",
        limit=21, code="v2_eval_inventory_unavailable",
    )
    def latest(kind: str) -> dict:
        found = [e for e in evals if e.get("eval_type") == kind]
        require(bool(found) and all(e.get("run_id") == run["id"] for e in found),
                "v2_required_evaluation_missing")
        return found[-1]
    ci, quality, browser = latest("github_ci"), latest("quality_gate"), latest("browser_e2e")
    preview_url = integration.get("preview_url")
    require(
        isinstance(preview_url, str) and preview_url.startswith("https://")
        and ci.get("status") == "success" and ci.get("baseline_ref") == sha
        and quality.get("status") == "success" and quality.get("baseline_ref") == sha
        and isinstance(quality.get("result"), dict)
        and quality["result"].get("passed") is True
        and browser.get("status") == "success"
        and browser.get("baseline_ref") == preview_url,
        "v2_required_ci_quality_browser_missing",
    )
    lanes = rows(
        reader, "factory_specialist_lane_jobs",
        "id,run_id,role,status,required,candidate_commit",
        "run_id=eq." + run["id"] + "&required=eq.true",
        limit=16, code="v2_specialists_unavailable",
    )
    require(
        {"qa", "security", "operations"} <= {row.get("role") for row in lanes}
        and len({row.get("role") for row in lanes}) == len(lanes)
        and all(row.get("status") == "passed" and row.get("required") is True
                and row.get("candidate_commit") == sha for row in lanes),
        "v2_specialist_evidence_invalid",
    )
    deployments = rows(
        reader, "factory_deployments", "id,run_id,environment,status,metadata",
        "run_id=eq." + run["id"] + "&environment=eq.preview",
        limit=11, code="v2_preview_deployment_missing",
    )
    require(
        any(row.get("status") == "success"
            and isinstance(row.get("metadata"), dict)
            and row["metadata"].get("candidate_commit") == sha
            and row["metadata"].get("preview_url") == preview_url
            for row in deployments),
        "v2_preview_deployment_mismatch",
    )
    preview = one(
        reader, "factory_tool_usage", "id,run_id,operation,metadata",
        "run_id=eq." + run["id"]
        + "&operation=eq.verified_preview_awaiting_human_merge",
        "v2_preview_gate_receipt_missing",
    )
    pm = preview.get("metadata")
    require(
        isinstance(pm, dict) and pm.get("pr") == pr_number
        and pm.get("head_sha") == sha and pm.get("preview_url") == preview_url,
        "v2_preview_gate_receipt_mismatch",
    )
    reports = rows(
        reader, "factory_release_reports",
        "id,run_id,status,candidate_commit,report,created_at",
        "run_id=eq." + run["id"] + "&order=created_at.desc,id.desc",
        limit=6, code="v2_release_report_missing",
    )
    latest_report = reports[0]
    report_body = latest_report.get("report")
    require(
        latest_report.get("status") == "blocked"
        and latest_report.get("candidate_commit") == sha
        and isinstance(report_body, dict)
        and report_body.get("release_state") == "nonproduction_integrated"
        and isinstance(report_body.get("blockers"), list)
        and bool(report_body["blockers"]),
        "v2_production_release_not_blocked",
    )
    obs = one(
        reader, "factory_audit_events",
        "id,project_id,task_id,run_id,event_type,actor_type,actor_ref,payload",
        "project_id=eq." + pid + "&run_id=eq." + run["id"]
        + "&event_type=eq.change_set.nonproduction_merge.observed",
        "v2_observed_merge_not_unique",
    )
    require(
        obs.get("task_id") == cs["root_task_id"]
        and obs.get("actor_ref") == "nonproduction-release-observer"
        and obs.get("actor_type") == "system"
        and obs.get("payload") == integration,
        "v2_observed_merge_not_authentic",
    )
    usage = one(
        reader, "factory_tool_usage", "id,run_id,operation,metadata",
        "run_id=eq." + run["id"] + "&operation=eq.nonproduction_merge_observed",
        "v2_merge_usage_not_unique",
    )
    require(usage.get("metadata") == integration, "v2_merge_usage_mismatch")
    require(
        reader._verified_nonproduction_integration(
            github=github, repository=project["repository"],
            project_id=pid, events=[obs], release_run_id=run["id"],
            candidate_sha=sha, pr_number=pr_number,
            head_ref=cs["integration_branch"],
            base_ref=integration["base_ref"], merge_sha=integration["merge_sha"],
        ),
        "v2_postmerge_browser_or_branch_unverified",
    )
    verifier_id = integration.get("verifier_run_id")
    require(str(verifier_id).isdigit() and int(verifier_id) > 0,
            "v2_browser_verifier_identity_invalid")
    vr = factory_github._call(
        "GET", f"/repos/{FACTORY_REPO}/actions/runs/{int(verifier_id)}"
    )
    jobs = factory_github._call(
        "GET", f"/repos/{FACTORY_REPO}/actions/runs/{int(verifier_id)}/jobs",
        query={"per_page": "100"},
    )
    jr = jobs.get("jobs") if isinstance(jobs, dict) else None
    require(
        isinstance(vr, dict) and vr.get("id") == int(verifier_id)
        and vr.get("status") == "completed" and vr.get("conclusion") == "success"
        and isinstance(jr, list) and len(jr) < 100
        and jobs.get("total_count") == len(jr)
        and any(j.get("name") == "browser-evidence"
                and j.get("status") == "completed"
                and j.get("conclusion") == "success" for j in jr),
        "v2_independent_browser_runner_not_green",
    )
    # The PR and the target Preview ref must remain the same after all reads.
    require(github.get_pull_request(pr_number) == pr,
            "v2_pr_changed_during_audit")
    return {"pr_number": pr_number, "merge_sha": integration["merge_sha"],
            "browser_verifier_run_id": int(verifier_id)}


def audit_existing_native_v2(*, reader: SupabaseJourneyReader,
                             project_key: str, journey_id: str,
                             github_factory=GitHubRestAdapter) -> dict:
    """Return positive scope-limited proof or raise EvidenceBlocked.

    Every external lookup is a bounded GET. No PR merge, RPC, SQL write,
    model call, queue claim, real release, production deployment or Start.
    """
    require(isinstance(project_key, str) and KEY.fullmatch(project_key) is not None,
            "invalid_project_key")
    jid = _uuid(journey_id)
    project = one(
        reader, "factory_projects",
        "id,project_key,project_kind,repository,is_active,manifest",
        "project_key=eq." + project_key, "project_unavailable",
    )
    require(
        project.get("project_key") == project_key
        and project.get("project_kind") == "existing"
        and project.get("is_active") is True
        and isinstance(project.get("repository"), str)
        and re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", project["repository"])
        and isinstance(project.get("manifest"), dict)
        and isinstance(project["manifest"].get("preview"), dict)
        and project["manifest"]["preview"].get("required") is True
        and project["manifest"]["preview"].get("provider") == "vercel",
        "project_not_eligible_for_v2_preview_audit",
    )
    pid = _uuid(project.get("id"))
    journey = one(
        reader, "factory_journeys",
        "id,project_id,request_id,request_source,auth_actor_ref,auth_event_id,"
        "request_digest,request_snapshot,issue_repository,issue_number,state,"
        "execution_generation,project_policy_version,policy_digest,binding,"
        "binding_version,source_commit,candidate_commit,production_release_sha,created_at",
        "id=eq." + jid, "journey_v2_unavailable",
    )
    require(journey.get("id") == jid and journey.get("project_id") == pid,
            "cross_project_journey")
    _uuid(journey.get("request_id"))
    factory_github = github_factory(repository=FACTORY_REPO)
    bound = _check_owner_intake(
        reader=reader, factory_github=factory_github,
        journey=journey, project_key=project_key, project_id=pid,
    )
    cs, run, _root, units, receipts = _check_lineage(
        reader=reader, project=project, journey=journey, bound=bound,
    )
    github = github_factory(repository=project["repository"])
    delivery = _check_delivery(
        reader=reader, github=github, factory_github=factory_github,
        project=project, journey=journey, cs=cs, run=run,
        units=units, receipts=receipts,
    )
    return {
        "schema_version": 1, "project_key": project_key,
        "journey_id": jid, "change_set_id": cs["id"],
        "run_id": run["id"], "repository": project["repository"],
        "candidate_commit": journey["candidate_commit"],
        "nonproduction_merge_sha": delivery["merge_sha"],
        "pr_number": delivery["pr_number"],
        "browser_verifier_run_id": delivery["browser_verifier_run_id"],
        "verified_work_units": len(units),
        "status": "integrated_nonproduction",
        "classification": "integrated_nonproduction",
        "requirement_met": True,
        "highest_verified": "awaiting_release",
        "human_release_observed": "not_reached",
        "operations": "not_reached",
        "nonproduction_integrated": True,
        "production_released": False,
        "product_ready": False, "paid_calls": 0, "writes": 0,
    }
