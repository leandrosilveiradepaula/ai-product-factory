"""Read-only, run-scoped evidence for a genuinely new Factory journey.

This module never starts projects, runs agents, dispatches CI, merges PRs,
updates the Control Plane or calls a paid model. Missing proof is NOT success.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from .github_loop import CIState
from .github_owner_start import FACTORY_REPO, OWNER_ID, OWNER_LOGIN, ISSUE_NUMBER, request_uuid

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
    nonproduction_integrated: bool = False
    nonproduction_merge_sha: str | None = None

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
            "nonproduction_integrated": self.nonproduction_integrated,
            "nonproduction_merge_sha": self.nonproduction_merge_sha,
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
        if row.get("event_type") != name:
            continue
        if row.get("project_id") != audit_project and not (
            # Legacy quality-gate events have project_id=NULL, but are scoped
            # to the exact release run and candidate SHA below.
            row.get("project_id") is None and name == "quality_gate.passed"
            and isinstance(required.get("candidate_commit"), str)
            and SHA.fullmatch(required["candidate_commit"])
        ):
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
        if row.get("event_type") != name:
            continue
        # Legacy release/Preview gate events were intentionally emitted with
        # project_id=NULL. Their immutable run_id + PR + SHA is authoritative,
        # but unrelated NULL-project events never count for other event types.
        if row.get("project_id") != project_id and not (
            row.get("project_id") is None
            and name in ("release.preview_not_required",
                         "release.awaiting_human_merge",
                         "release.human_merge_observed")
        ):
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
    candidate_reconciliations: Sequence[Mapping[str, Any]] = (),
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
    start_kind=start_command.get("command")
    if (start_kind not in ("start","console_continuation","github_owner_continuation","console_greenfield_intake")
        or str((start_command.get("result") or {}).get("run_id")) != root_run_id):
        raise ValueError("evidence is not linked to an explicit operator action")
    if not isinstance(start_command.get("actor_id"), str) or not start_command["actor_id"].strip():
        raise ValueError("explicit operator action has no actor identity")
    if (not isinstance(runs,(list,tuple))
        or any(not isinstance(row,Mapping) or not isinstance(row.get("id"),str)
               or not row["id"].strip() for row in runs)):
        raise ValueError("malformed bounded run lineage")
    run_ids = {str(row.get("id")) for row in runs}
    if root_run_id not in run_ids:
        raise ValueError("Start run is missing from bounded lineage")
    if len(run_ids) != len(runs):
        raise ValueError("duplicate run in bounded lineage")
    blockers: list[str] = []
    primary = [r for r in runs if r.get("id") == root_run_id][0]
    if start_kind == "console_greenfield_intake":
        manifest=project.get("manifest")
        meta=primary.get("metadata")
        draft=start_command.get("request_id")
        operator=start_command.get("actor_id")
        count=start_command.get("attachment_count")
        task_id=start_command.get("bootstrap_task_id")
        born=project.get("created_at")
        uuid_pattern=r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
        if (project.get("project_kind")!="greenfield"
            or not isinstance(manifest,dict)
            or manifest.get("source")!="factory-console"
            or manifest.get("onboarding_mode")!="greenfield"
            or manifest.get("reconcile_first") is True
            or not isinstance(draft,str) or not re.fullmatch(uuid_pattern,draft)
            or not isinstance(operator,str) or not re.fullmatch(uuid_pattern,operator)
            or not isinstance(task_id,str) or not re.fullmatch(uuid_pattern,task_id)
            or type(count) is not int or not 0<=count<=10
            or manifest.get("bootstrap_request_id")!=draft
            or manifest.get("bootstrap_operator_id")!=operator
            or type(manifest.get("bootstrap_attachment_count")) is not int
            or manifest["bootstrap_attachment_count"]!=count
            or not isinstance(born,str)
            or primary.get("task_id")!=task_id
            or not isinstance(meta,dict) or meta.get("source")!="factory-console"):
            raise ValueError("Console greenfield intake provenance is not bound to root run")
        kinds=("project.intake.created","project.attachments.finalized","project.bootstrap.enqueued")
        receipts=[event for event in events if
                  event.get("event_type") in kinds
                  and event.get("project_id")==pid
                  and event.get("created_at")==born]
        if (len(receipts)!=3
            or [e.get("event_type") for e in receipts]!=list(kinds)
            or any(type(e.get("id")) is not int for e in receipts)
            or not (receipts[0]["id"]<receipts[1]["id"]<receipts[2]["id"])
            or any(e.get("actor_ref")!="factory-console" for e in receipts)
            or [e.get("actor_type") for e in receipts]!=["human","human","system"]
            or any(e.get("task_id") is not None for e in receipts)
            or receipts[0].get("run_id") is not None
            or receipts[1].get("run_id") is not None
            or receipts[2].get("run_id")!=root_run_id):
            raise ValueError("Console greenfield intake has no exact paired audit events")
        intake,finalized,bootstrap=receipts
        if (not isinstance(intake.get("payload"),dict)
            or intake["payload"].get("project_key")!=key
            or intake["payload"].get("project_kind")!="greenfield"
            or not isinstance(finalized.get("payload"),dict)
            or finalized["payload"].get("draft_id")!=draft
            or type(finalized["payload"].get("count")) is not int
            or finalized["payload"]["count"]!=count
            or not isinstance(bootstrap.get("payload"),dict)
            or bootstrap["payload"].get("task_id")!=task_id):
            raise ValueError("Console greenfield intake request/attachments are unverified")
    if start_kind == "console_continuation":
        request_id=start_command.get("request_id")
        metadata=primary.get("metadata")
        if (not isinstance(request_id,str)
            or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}",request_id)
            or start_command.get("actor_id")!="factory-console"
            or not isinstance(metadata,dict)
            or metadata.get("source")!="factory-console"
            or metadata.get("continuation_request_id")!=request_id
            or not any(
                event.get("project_id")==pid
                and event.get("run_id")==root_run_id
                and event.get("task_id")==primary.get("task_id")
                and event.get("event_type")=="project.continuation.requested"
                and event.get("actor_type")=="human"
                and event.get("actor_ref")=="factory-console"
                and isinstance(event.get("payload"),dict)
                and event["payload"].get("request_id")==request_id
                for event in events
            )
            or not any(
                event.get("project_id")==pid
                and event.get("run_id")==root_run_id
                and event.get("task_id")==primary.get("task_id")
                and event.get("event_type")=="project.reconciliation.enqueued"
                and event.get("actor_type")=="system"
                and event.get("actor_ref")=="factory-console"
                and isinstance(event.get("payload"),dict)
                and event["payload"].get("request_id")==request_id
                for event in events
            )):
            raise ValueError("operator continuation is not backed by exact human and queue receipts")
    if start_kind == "github_owner_continuation":
        origin=start_command.get("github_origin")
        request_id=start_command.get("request_id")
        metadata=primary.get("metadata")
        gh=metadata.get("continuation_request") if isinstance(metadata,dict) else None
        if (not isinstance(origin,dict)
            or origin.get("repository")!=FACTORY_REPO
            or type(origin.get("actor_id")) is not int or origin["actor_id"]!=OWNER_ID
            or origin.get("actor_login")!=OWNER_LOGIN
            or type(origin.get("issue_number")) is not int
            or origin["issue_number"]!=ISSUE_NUMBER
            or type(origin.get("comment_id")) is not int or origin["comment_id"]<1
            or not isinstance(request_id,str)
            or request_id!=request_uuid(ISSUE_NUMBER,origin["comment_id"])
            or start_command.get("actor_id")!=str(OWNER_ID)
            or not isinstance(metadata,dict)
            or metadata.get("source")!="github-owner"
            or metadata.get("continuation_request_id")!=request_id
            or not isinstance(gh,dict) or gh.get("github")!=origin
            or gh.get("attachment_count")!=0):
            raise ValueError("GitHub owner Start provenance invalid")
        for event_name,actor_type in (
            ("project.continuation.requested","human"),
            ("project.reconciliation.enqueued","system"),
        ):
            if not any(
                ev.get("project_id")==pid
                and ev.get("run_id")==root_run_id
                and ev.get("task_id")==primary.get("task_id")
                and ev.get("event_type")==event_name
                and ev.get("actor_type")==actor_type
                and ev.get("actor_ref")=="github-owner"
                and isinstance(ev.get("payload"),dict)
                and ev["payload"].get("request_id")==request_id
                and ev["payload"].get("github")==origin
                and ev["payload"].get("source")=="github-owner"
                for ev in events
            ):
                raise ValueError("GitHub owner Start lacks exact paired audits")
    if primary.get("status") in ("failed", "blocked", "cancelled"):
        blockers.append("root_run_terminal_without_success")
    if any(r.get("status") in ("failed", "blocked") for r in runs):
        blockers.append("descendant_run_failed_or_blocked")
    if any(s.get("status") in ("blocked",) for s in change_sets):
        blockers.append("change_set_blocked")
    def has_stage(stage: str) -> bool:
        return _event(events, "product.stage.persisted",
                      run_ids=run_ids, payload={"stage":stage}, audit_project=pid)
    # Existing imported projects use reconciliation -> gap_analysis -> planning
    # as their ACTUAL Product Stage contract; greenfield records
    # discovery -> specification -> planning. They must not borrow one
    # another's event names and declare a fictitious successful stage.
    if project.get("project_kind") in ("existing", "platform"):
        discovered = has_stage("reconciliation")
        specified = has_stage("gap_analysis")
    else:
        discovered = has_stage("discovery")
        specified = has_stage("specification")
    planned = has_stage("planning")
    if (not isinstance(change_sets,(list,tuple))
        or any(not isinstance(cs,Mapping) or cs.get("project_id")!=pid
               or not isinstance(cs.get("id"),str) or not cs["id"].strip()
               for cs in change_sets)):
        raise ValueError("Change Set is outside the audited project")
    cs_ids = {str(cs.get("id")) for cs in change_sets}
    if len(cs_ids) != len(change_sets):
        raise ValueError("duplicate Change Set in bounded lineage")
    # Materialization precedes dispatch: pending Work Units intentionally have
    # run_id=NULL in the versioned Change Set schema. A NULL run can never
    # prove routing, implementation or completion. Once work is assigned,
    # its run must be a descendant of the selected human Start.
    def _valid_unit_run(unit: Mapping[str, Any]) -> bool:
        run = unit.get("run_id")
        if run is None:
            return unit.get("status") == "pending" and unit.get("output_commit") is None
        return isinstance(run, str) and run in run_ids

    if (not isinstance(work_units,(list,tuple))
        or any(not isinstance(unit,Mapping)
               or str(unit.get("change_set_id")) not in cs_ids
               or not _valid_unit_run(unit)
               or not isinstance(unit.get("id"),str) or not unit["id"].strip()
               for unit in work_units)):
        raise ValueError("Work Unit is outside the audited Change Set lineage")
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
    if (not isinstance(deployments,(list,tuple))
        or any(not isinstance(row,Mapping) or str(row.get("run_id")) not in run_ids
               for row in deployments)):
        raise ValueError("deployment is outside the audited run lineage")
    if (not isinstance(release_reports,(list,tuple))
        or any(not isinstance(row,Mapping) or row.get("project_id")!=pid
               or str(row.get("run_id")) not in run_ids
               for row in release_reports)):
        raise ValueError("release report is outside the audited project lineage")
    receipt_pairs: dict[str, tuple[int, str]] = {}
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
        pair = (num, str(row["run_id"]))
        if sha in receipt_pairs and receipt_pairs[sha] != pair:
            raise ValueError("conflicting create_pr receipts for same commit")
        receipt_pairs[sha] = pair
    # A later repair may move a PR head ONLY through the existing atomic,
    # audited candidate reconciliation RPC. The original create_pr receipt
    # stays immutable and must match the previous SHA, run and PR number.
    reconciled_receipts: dict[str,tuple[int,str]] = {}
    if not isinstance(candidate_reconciliations,(list,tuple)) or len(candidate_reconciliations)>10:
        raise ValueError("candidate reconciliations are malformed or unbounded")
    for row in candidate_reconciliations:
        if not isinstance(row,dict) or row.get("operation")!="reconcile_pr_candidate" or row.get("run_id") not in run_ids:
            raise ValueError("candidate reconciliation is not scoped to this run")
        meta=row.get("metadata")
        if not isinstance(meta,dict):
            raise ValueError("candidate reconciliation receipt is malformed")
        prev=meta.get("previous_commit")
        curr=meta.get("candidate_commit")
        pr_no=meta.get("pr_number")
        if (not isinstance(prev,str) or not SHA.fullmatch(prev)
            or not isinstance(curr,str) or not SHA.fullmatch(curr)
            or curr not in candidate_shas
            or prev not in receipt_pairs
            or str(pr_no)!=str(receipt_pairs[prev][0])
            or row["run_id"]!=receipt_pairs[prev][1]
            or meta.get("change_set_id") not in cs_ids
            or meta.get("repository")!=repo
            or meta.get("compare_status")!="ahead"
            or not isinstance(meta.get("changed_files"),list)
            or github is None or github.get("candidate_reconciliation_verified") is not True):
            raise ValueError("candidate reconciliation identity or GitHub proof is invalid")
        if curr in reconciled_receipts or curr in receipt_pairs:
            raise ValueError("duplicate or ambiguous candidate reconciliation")
        reconciled_receipts[curr]=receipt_pairs[prev]
    receipt_pairs.update(reconciled_receipts)
    candidate = None
    pr_number = None
    delivery_run_id = None
    if candidate_shas:
        matches = [(sha, num, run_id) for sha, (num, run_id) in receipt_pairs.items()
                   if sha in candidate_shas]
        if len(matches) == 1:
            candidate, pr_number, delivery_run_id = matches[0]
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
    # PR/CI/Preview/release evidence must all belong to the SAME run that
    # created this candidate PR. A different sibling run must never complete it.
    delivery_runs = {delivery_run_id} if delivery_run_id else set()
    def delivery(evidence: str) -> bool:
        return _event(
            events, "delivery.evidence.recorded",
            run_ids=delivery_runs,
            payload={"evidence_type":evidence,"status":"passed",
                     "evidence_ref":candidate},
            audit_project=pid,
        ) or _event(
            events, "delivery.evidence.recorded",
            run_ids=delivery_runs,
            payload={"evidence_type":evidence,"status":"success",
                     "evidence_ref":candidate},
            audit_project=pid,
        )
    reviewed = bool(candidate and delivery("qa") and delivery("security") and
                    _event(events,"quality_gate.passed",run_ids=delivery_runs,
                           payload={"candidate_commit":candidate},audit_project=pid))
    ci = bool(candidate_bound and github_pr.get("ci_state")==CIState.SUCCESS
              and delivery("github_ci"))

    def _verified_provider_preview() -> bool:
        """Link status refs to one deployment, SHA and browser URL.

        The Vercel evidence_ref is a provider deployment identifier, NOT a
        commit SHA. Trusting an arbitrary matching ref would be unsafe; bind
        two distinct delivery receipts to the same candidate-scoped deployment,
        browser event and exact awaiting-release receipt.
        """
        for dep in deployments:
            meta=dep.get("metadata")
            if (dep.get("run_id") not in delivery_runs
                or dep.get("environment")!="preview"
                or dep.get("status")!="success"
                or not isinstance(meta,Mapping)
                or meta.get("candidate_commit")!=candidate
                or meta.get("provider")!="vercel-github"):
                continue
            url=meta.get("preview_url")
            parsed=urlparse(url) if isinstance(url,str) else None
            if (parsed is None or parsed.scheme!="https"
                or not (parsed.hostname or "").endswith(".vercel.app")
                or parsed.username is not None or parsed.password is not None):
                continue
            browser=any(
                event.get("event_type")=="preview.browser_evidence_recorded"
                # Legacy scoped event has project_id=NULL. Its use is
                # safe only after matching run, deployment candidate SHA,
                # preview URL and both immutable delivery receipt refs.
                and event.get("project_id") in (pid,None)
                and event.get("run_id") in delivery_runs
                and isinstance(event.get("payload"),Mapping)
                and event["payload"].get("status")=="success"
                and event["payload"].get("preview_url")==url
                for event in events
            )
            if not browser:
                continue
            for gate in events:
                payload=gate.get("payload")
                if (gate.get("event_type")!="release.awaiting_human_merge"
                    or gate.get("project_id") not in (pid,None)
                    or gate.get("run_id") not in delivery_runs
                    or not isinstance(payload,Mapping)
                    or payload.get("head_sha")!=candidate
                    or str(payload.get("pr"))!=str(pr_number)
                    or payload.get("preview_url")!=url):
                    continue
                ref=payload.get("deployment_ref")
                if not isinstance(ref,str) or not 1<=len(ref)<=200:
                    continue
                if (_event(events,"delivery.evidence.recorded",
                           run_ids=delivery_runs,
                           payload={"evidence_type":"preview","status":"passed",
                                    "evidence_ref":ref},audit_project=pid)
                    and _event(events,"delivery.evidence.recorded",
                               run_ids=delivery_runs,
                               payload={"evidence_type":"browser_evidence","status":"passed",
                                        "evidence_ref":ref},audit_project=pid)):
                    return True
        return False

    preview_done = False
    if candidate_bound and ci and isinstance(preview_required, bool):
        if not preview_required:
            preview_done = _release_event(
                events, "release.preview_not_required", project_id=pid,
                sha=candidate,pr_number=pr_number,run_ids=delivery_runs,
            )
        else:
            # Preserve historical same-repo main release receipts that
            # already used candidate-SHA as both evidence refs and did not
            # persist provider metadata. Never extend that legacy fallback
            # to preview/** integration or modern deployment-linked proofs.
            legacy_main_preview=bool(
                expected_base=="main"
                and delivery("preview") and delivery("browser_evidence")
                and any(row.get("environment")=="preview"
                        and row.get("status")=="success"
                        and row.get("run_id") in delivery_runs
                        and not row.get("metadata")
                        for row in deployments)
                and any(row.get("event_type")=="preview.browser_evidence_recorded"
                        and row.get("project_id")==pid
                        and row.get("run_id") in delivery_runs
                        and isinstance(row.get("payload"),dict)
                        and row["payload"].get("status")=="success"
                        for row in events)
            )
            preview_done = bool(
                _verified_provider_preview() or legacy_main_preview
            )
    if candidate_bound and preview_required is None:
        blockers.append("preview_applicability_not_verified")
    # A terminal run may already be completed AFTER a human release.
    # The immutable audit event is the evidence that the boundary existed;
    # looking only at today's status would erase a legitimate past gate.
    # Both contracts represent a real, explicit human release boundary:
    # legacy exact-PR event, or a newer policy decision AND exact candidate
    # transition to awaiting_release. Never infer a gate from CI alone.
    legacy_gate=_release_event(events,"release.awaiting_human_merge",project_id=pid,
                               sha=candidate,pr_number=pr_number,run_ids=delivery_runs)
    policy_gate=bool(
        _event(events,"release.policy.decided",run_ids=delivery_runs,
               payload={"outcome":"ready_for_human_release"},audit_project=pid)
        and _event(events,"run.status.updated",run_ids=delivery_runs,
                   payload={"status":"awaiting_release","candidate_commit":candidate},
                   audit_project=pid)
        and preview_done and reviewed and ci
    )
    release_gate=bool(candidate_bound and (legacy_gate or policy_gate))
    merge_sha = github_pr.get("merge_commit_sha") if candidate_bound else None
    # Newer release observer events contain candidate_commit+merge_sha but
    # omit the PR number; the console's separately audited human merge DOES
    # carry exact PR/repository/candidate/merge identities. Require both.
    console_merge_witness = bool(
        delivery_run_id and isinstance(merge_sha,str) and SHA.fullmatch(merge_sha)
        and _event(events,"release.human_merge_observed",run_ids=delivery_runs,
                   payload={"candidate_commit":candidate,"merge_sha":merge_sha},
                   audit_project=pid)
        and any(
            row.get("event_type") == "human_release.console_merge_succeeded"
            and row.get("project_id") == pid
            and row.get("run_id") == delivery_run_id
            and isinstance(row.get("payload"),dict)
            and row["payload"].get("repository") == repo
            and str(row["payload"].get("pr_number")) == str(pr_number)
            and row["payload"].get("candidate_commit") == candidate
            and row["payload"].get("merge_sha") == merge_sha
            for row in events
        )
    )
    released = bool(
        # Only a main-target PR can ever provide production release proof.
        expected_base == "main"
        and release_gate and github_pr.get("merged") is True
        and isinstance(merge_sha,str) and SHA.fullmatch(merge_sha)
        and (
            _release_event(events,"release.human_merge_observed",project_id=pid,
                           sha=candidate,pr_number=pr_number,merge_sha=merge_sha,
                           run_ids=delivery_runs)
            or console_merge_witness
        )
        and any(rr.get("candidate_commit")==candidate and rr.get("status")=="released"
                and rr.get("run_id") == delivery_run_id for rr in release_reports)
    )
    # Preview/** integration is not a human PRODUCTION release. Certify the
    # typed nonproduction terminal only with the exact observer receipt,
    # independently browser-verified MERGE SHA and the entire preceding
    # delivery chain. Never advance the production operations stage here.
    nonproduction_events=[
        event for event in events
        if event.get("event_type")=="change_set.nonproduction_merge.observed"
        and event.get("project_id")==pid
        and event.get("run_id")==delivery_run_id
    ]
    nonproduction_integrated=bool(
        project.get("project_kind")=="existing"
        and candidate_bound and isinstance(expected_base,str)
        and expected_base.startswith("preview/")
        and github_pr.get("merged") is True
        and isinstance(merge_sha,str) and SHA.fullmatch(merge_sha)
        and github_pr.get("nonproduction_integration_verified") is True
        and routed and implemented and reviewed and ci and preview_done
        and release_gate and not released
        and any(cs.get("candidate_commit")==candidate
                and cs.get("status")=="completed" for cs in change_sets)
        and any(run.get("id")==delivery_run_id and run.get("status")=="integrated"
                for run in runs)
        and len(nonproduction_events)==1
        and nonproduction_events[0].get("actor_ref")=="nonproduction-release-observer"
        and isinstance(nonproduction_events[0].get("payload"),Mapping)
        and nonproduction_events[0]["payload"].get("candidate_commit")==candidate
        and nonproduction_events[0]["payload"].get("merge_sha")==merge_sha
        and nonproduction_events[0]["payload"].get("base_ref")==expected_base
        and nonproduction_events[0]["payload"].get("repository")==repo
        and str(nonproduction_events[0]["payload"].get("pr_number"))==str(pr_number)
        and nonproduction_events[0]["payload"].get("production_released") is False
        and nonproduction_events[0]["payload"].get("production_release_completed") is False
    )
    if (candidate_bound and isinstance(expected_base,str)
        and expected_base.startswith("preview/")
        and any(rr.get("run_id")==delivery_run_id
                and rr.get("candidate_commit")==candidate
                and rr.get("status")=="released" for rr in release_reports)):
        blockers.append("preview_integration_conflicts_with_production_release_report")
        nonproduction_integrated=False
    if candidate_bound and github_pr.get("merged") is True and not released and not nonproduction_integrated:
        blockers.append("merged_candidate_without_verified_release")
    operations = bool(
        released and delivery("operations")
        and _event(events,"project.state.reconciled_after_release",
                   run_ids=delivery_runs,
                   payload={"merge_sha":merge_sha,"lifecycle_stage":"operations"},
                   audit_project=pid)
    )
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
    # A later event alone never yields a complete/awaiting label while
    # any required earlier stage is still missing.
    status = ("blocked" if blockers else
              "observed_complete" if highest == "operations" else
              "integrated_nonproduction" if nonproduction_integrated
              and highest == "awaiting_release" else
              "awaiting_human_merge" if highest == "awaiting_release"
              and not released else "in_progress")
    return JourneyReport(
        key,root_run_id,status,highest,tuple(stages),
        candidate,pr_number,tuple(dict.fromkeys(blockers)),
        nonproduction_integrated=nonproduction_integrated,
        nonproduction_merge_sha=merge_sha if nonproduction_integrated else None,
    )
