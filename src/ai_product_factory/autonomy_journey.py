"""Read-only, run-scoped evidence for a genuinely new Factory journey.

This module never starts projects, runs agents, dispatches CI, merges PRs,
updates the Control Plane or calls a paid model. Missing proof is NOT success.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .github_loop import CIState

SHA = re.compile(r"^[0-9a-f]{40}$")
STAGES = (
    "manual_start",
    "discovery",
    "specification",
    "planning",
    "routing",
    "implementation",
    "review",
    "github_ci",
    "preview",
    "awaiting_release",
    "human_release_observed",
    "operations",
)


@dataclass(frozen=True)
class JourneyStage:
    name: str
    status: str
    evidence: str | None = None

    def as_json(self) -> dict:
        return {"name": self.name, "status": self.status, "evidence": self.evidence}


@dataclass(frozen=True)
class JourneyReport:
    project_key: str
    root_run_id: str | None
    status: str
    highest_verified: str | None
    stages: tuple[JourneyStage, ...]
    candidate_sha: str | None
    pr_number: int | None
    blockers: tuple[str, ...] = ()

    def as_json(self) -> dict:
        # Only IDs, states and tightly controlled reasons are exposed.
        # Never serialize manifests, arbitrary audit payloads or credentials.
        return {
            "project_key": self.project_key,
            "root_run_id": self.root_run_id,
            "status": self.status,
            "highest_verified": self.highest_verified,
            "stages": [stage.as_json() for stage in self.stages],
            "candidate_sha": self.candidate_sha,
            "pr_number": self.pr_number,
            "blockers": list(self.blockers),
            "product_ready": False,
            "paid_calls": 0,
            "writes": 0,
        }


def no_start_report(project_key: str) -> JourneyReport:
    return JourneyReport(
        project_key, None, "not_started", None,
        tuple(JourneyStage(name, "not_reached") for name in STAGES),
        None, None, ("explicit_project_start_not_observed",),
    )


def _event(
    events: Sequence[Mapping[str, Any]],
    name: str,
    *,
    run_ids: set[str],
    payload: Mapping[str, Any] | None = None,
    audit_project: str,
) -> bool:
    required = payload or {}
    for row in events:
        if row.get("event_type") != name or row.get("project_id") != audit_project:
            continue
        if row.get("run_id") not in run_ids:
            continue
        data = row.get("payload")
        if not isinstance(data, dict):
            continue
        if all(data.get(key) == value for key, value in required.items()):
            return True
    return False


def _release_event(
    events: Sequence[Mapping[str, Any]], name: str, *,
    project_id: str, sha: str, pr_number: int, merge_sha: str | None = None,
    run_ids: set[str],
) -> bool:
    for row in events:
        if row.get("event_type") != name or row.get("project_id") != project_id:
            continue
        if row.get("run_id") not in run_ids:
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        if payload.get("head_sha") != sha:
            continue
        pr = payload.get("pr_number", payload.get("pr"))
        if str(pr) != str(pr_number):
            continue
        if merge_sha is not None and payload.get("merge_sha") != merge_sha:
            continue
        return True
    return False


def evaluate_journey(
    *,
    project: Mapping[str, Any],
    root_run_id: str,
    start_command: Mapping[str, Any],
    runs: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    change_sets: Sequence[Mapping[str, Any]],
    work_units: Sequence[Mapping[str, Any]],
    create_pr_receipts: Sequence[Mapping[str, Any]],
    deployments: Sequence[Mapping[str, Any]],
    release_reports: Sequence[Mapping[str, Any]],
    github: Mapping[str, Any] | None,
    preview_required: bool | None,
) -> JourneyReport:
    """Correlate actual evidence with a fresh explicit Start, never a project-wide count.

    Callers must fetch only the task/run lineage descended from the Start run
    and project/time-scoped evidence, or reject a partial page. All GitHub
    evidence is optional until a candidate exists; when present it must match
    the exact PR and commit recorded in the Control Plane.
    """
    key = project.get("project_key")
    pid = project.get("id")
    repo = project.get("repository")
    if not all(isinstance(v, str) and v.strip() for v in (key, pid, repo, root_run_id)):
        raise ValueError("invalid project or root run identity")
    if start_command.get("command") != "start" or str((start_command.get("result") or {}).get("run_id")) != root_run_id:
        raise ValueError("evidence is not linked to an explicit Start")
    if not isinstance(start_command.get("actor_id"), str) or not start_command["actor_id"].strip():
        raise ValueError("explicit Start has no operator identity")
    run_ids = {str(row.get("id")) for row in runs}
    if root_run_id not in run_ids:
        raise ValueError("Start run is missing from bounded lineage")
    if len(run_ids) != len(runs):
        raise ValueError("duplicate run in bounded lineage")
    blockers: list[str] = []
    primary = [r for r in runs if r.get("id") == root_run_id][0]
    if primary.get("status") in ("failed", "blocked", "cancelled"):
        blockers.append("root_run_terminal_without_success")
    if any(r.get("status") in ("failed", "blocked") for r in runs):
        blockers.append("descendant_run_failed_or_blocked")
    if any(s.get("status") in ("blocked",) for s in change_sets):
        blockers.append("change_set_blocked")
    def has_stage(stage: str) -> bool:
        return _event(events, "product.stage.persisted",
                      run_ids=run_ids, payload={"stage":stage}, audit_project=pid)
    discovered = has_stage("discovery")
    specified = has_stage("specification")
    planned = has_stage("planning")
    cs_ids = {str(cs.get("id")) for cs in change_sets}
    if len(cs_ids) != len(change_sets):
        raise ValueError("duplicate Change Set in bounded lineage")
    unit_ids = {str(u.get("id")) for u in work_units}
    if len(unit_ids) != len(work_units):
        raise ValueError("duplicate Work Unit in bounded lineage")
    routed = bool(cs_ids and work_units) and any(
        str(row.get("payload", {}).get("change_set_id")) in cs_ids
        and row.get("event_type") == "change_set.materialized"
        and row.get("project_id") == pid
        and row.get("run_id") in run_ids
        for row in events if isinstance(row.get("payload"), dict)
    ) and any(
        str(row.get("payload", {}).get("work_unit_id")) in unit_ids
        and row.get("event_type") == "change_set.work_unit.dispatched"
        and row.get("project_id") == pid
        and row.get("run_id") in run_ids
        for row in events if isinstance(row.get("payload"), dict)
    )
    completed_units = [
        u for u in work_units
        if u.get("status") in ("completed", "integrated")
        and isinstance(u.get("output_commit"), str)
        and SHA.fullmatch(u["output_commit"])
        and str(u.get("run_id")) in run_ids
    ]
    candidate_shas = {str(cs.get("candidate_commit")) for cs in change_sets
                      if isinstance(cs.get("candidate_commit"), str) and SHA.fullmatch(cs["candidate_commit"])}
    receipt_pairs = {}
    for row in create_pr_receipts:
        if row.get("run_id") not in run_ids or row.get("operation") != "create_pr":
            raise ValueError("unscoped create_pr receipt")
        meta = row.get("metadata")
        if not isinstance(meta, dict):
            raise ValueError("malformed create_pr receipt")
        sha = meta.get("head_sha")
        num = meta.get("pr")
        if not isinstance(sha, str) or not SHA.fullmatch(sha) or type(num) is not int or num <= 0:
            raise ValueError("invalid create_pr SHA or PR number")
        if sha in receipt_pairs and receipt_pairs[sha] != num:
            raise ValueError("conflicting create_pr receipts for same commit")
        receipt_pairs[sha] = num
    candidate = None
    pr_number = None
    if candidate_shas:
        matches = [(sha, num) for sha, num in receipt_pairs.items() if sha in candidate_shas]
        if len(matches) == 1:
            candidate, pr_number = matches[0]
        elif matches:
            blockers.append("ambiguous_candidate_sha")
        elif receipt_pairs:
            blockers.append("candidate_receipt_drift")
    # The target PR base is part of the project delivery policy, not always
    # main: imported existing projects must first target their explicit
    # nonproduction candidate branch, without calling that a release.
    expected_base = "main"
    if project.get("project_kind") == "existing":
        manifest = project.get("manifest")
        target = manifest.get("delivery_target") if isinstance(manifest, dict) else None
        if (not isinstance(target, dict) or target.get("mode") != "open_pr_candidate"
            or not isinstance(target.get("branch"), str)
            or not target["branch"].startswith("preview/")):
            expected_base = None
            blockers.append("project_delivery_target_unverified")
        else:
            expected_base = target["branch"]
    # Neither PR nor CI evidence is inferred from a green workflow elsewhere.
    github_pr = github or {}
    candidate_bound = bool(
        candidate and pr_number is not None
        and github_pr.get("repository") == repo
        and github_pr.get("number") == pr_number
        and github_pr.get("head_sha") == candidate
        and github_pr.get("head_repository") == repo
        and expected_base is not None
        and github_pr.get("base_ref") == expected_base
    )
    if candidate and github is not None and not candidate_bound:
        blockers.append("github_pr_sha_or_repository_drift")
    commit_verified = bool(candidate_bound and github_pr.get("work_unit_commit_verified") is True)
    implemented = bool(completed_units and commit_verified)
    def delivery(evidence: str) -> bool:
        return _event(
            events, "delivery.evidence.recorded",
            run_ids=run_ids, payload={"evidence_type":evidence,"status":"passed"},
            audit_project=pid,
        ) or _event(
            events, "delivery.evidence.recorded",
            run_ids=run_ids, payload={"evidence_type":evidence,"status":"success"},
            audit_project=pid,
        )
    reviewed = bool(candidate and delivery("qa") and delivery("security") and
                    _event(events,"quality_gate.passed",run_ids=run_ids,
                           payload={"candidate_commit":candidate},audit_project=pid))
    ci = bool(candidate_bound and github_pr.get("ci_state")==CIState.SUCCESS
              and delivery("github_ci"))
    preview_done = False
    if candidate_bound and ci and isinstance(preview_required, bool):
        if not preview_required:
            preview_done = _release_event(
                events, "release.preview_not_required", project_id=pid,
                sha=candidate,pr_number=pr_number,run_ids=run_ids,
            )
        else:
            preview_done = bool(
                delivery("preview") and delivery("browser_evidence")
                and any(row.get("environment")=="preview" and row.get("status")=="success"
                        and row.get("run_id") in run_ids for row in deployments)
                and any(row.get("event_type")=="preview.browser_evidence_recorded"
                        and row.get("project_id")==pid and row.get("run_id") in run_ids
                        and isinstance(row.get("payload"),dict)
                        and row["payload"].get("status")=="success"
                        for row in events)
            )
    if candidate_bound and preview_required is None:
        blockers.append("preview_applicability_not_verified")
    # A terminal run may already be completed AFTER a human release.
    # The immutable audit event is the evidence that the boundary existed;
    # looking only at today's status would erase a legitimate past gate.
    release_gate = bool(
        candidate_bound
        and _release_event(events,"release.awaiting_human_merge",project_id=pid,
                           sha=candidate,pr_number=pr_number,run_ids=run_ids)
    )
    merge_sha = github_pr.get("merge_commit_sha") if candidate_bound else None
    released = bool(
        release_gate and github_pr.get("merged") is True
        and isinstance(merge_sha,str) and SHA.fullmatch(merge_sha)
        and _release_event(events,"release.human_merge_observed",project_id=pid,
                           sha=candidate,pr_number=pr_number,merge_sha=merge_sha,
                           run_ids=run_ids)
        and any(rr.get("candidate_commit")==candidate and rr.get("status")=="released"
                and rr.get("run_id") in run_ids for rr in release_reports)
    )
    if candidate_bound and github_pr.get("merged") is True and not released:
        blockers.append("merged_candidate_without_verified_release")
    operations = bool(released and delivery("operations"))
    checks = (
        True, discovered, specified, planned, routed, implemented, reviewed,
        ci, preview_done, release_gate, released, operations,
    )
    stages: list[JourneyStage] = []
    reached = True
    highest = None
    for stage, good in zip(STAGES, checks):
        if good and reached:
            stages.append(JourneyStage(stage,"verified","durable_scoped_evidence"))
            highest=stage
        else:
            reached=False
            stages.append(JourneyStage(stage,"not_reached"))
    status = ("blocked" if blockers else
              "observed_complete" if operations else
              "awaiting_human_merge" if release_gate and not released else
              "in_progress")
    return JourneyReport(
        key,root_run_id,status,highest,tuple(stages),
        candidate,pr_number,tuple(dict.fromkeys(blockers)),
    )
