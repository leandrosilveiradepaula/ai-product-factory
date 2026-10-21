"""Evidence-scoped post-release product-readiness follow-up, never a release gate.

A completed delivery is not a global product audit.  This module reads only
the immutable release-report summary and produces a bounded *unverified*
readiness obligation for the next operator-authorized continuation.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from .product_readiness import REQUIRED_DOMAINS

_UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z", re.ASCII)
_SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
_STATES = frozenset({"not_assessed", "not_ready", "candidate_only", "unknown"})
_DOMAINS = tuple(REQUIRED_DOMAINS)
_MAX_REPORT_ROWS = 2


def _unknown(*, reason: str, run_id: str, merge_sha: str) -> dict:
    return {
        "scope": "current_product_after_release",
        "status": "unknown",
        "ready": False,
        "reason_code": reason,
        "next_step": "verify_release_evidence_then_global_audit",
        "release_run_id": run_id,
        "merge_sha": merge_sha,
        "report_verified": False,
        "pending_domains": list(_DOMAINS),
        "candidate_assessed_domains": [],
    }


def summarize_released_product(*, project_id: str, run_id: str,
                               merge_sha: str, report_rows: object) -> dict:
    """A known release can still have an unassessed product. No positive readiness.

    "passed" on the *candidate* is not proof of the current merged HEAD or
    full-product status. Never copy report free text into downstream prompts.
    """
    # This helper is shared by the release reconciler and read-only
    # observability.  Do not echo an unvalidated identifier from a malformed
    # queue/event into a durable follow-up or dashboard report.
    if (not isinstance(project_id,str) or not _UUID.fullmatch(project_id)
            or not isinstance(run_id,str) or not _UUID.fullmatch(run_id)
            or not isinstance(merge_sha,str) or not _SHA.fullmatch(merge_sha)):
        return _unknown(reason="release_identity_unverified",run_id="",merge_sha="")
    if not isinstance(report_rows, list) or len(report_rows) != 1:
        return _unknown(reason="release_report_unavailable_or_ambiguous",
                        run_id=run_id, merge_sha=merge_sha)
    row = report_rows[0]
    if (not isinstance(row, dict) or row.get("project_id") != project_id
            or row.get("run_id") != run_id or row.get("status") != "released"):
        return _unknown(reason="release_report_identity_unverified",
                        run_id=run_id, merge_sha=merge_sha)
    candidate = row.get("candidate_commit")
    report = row.get("report")
    if (not isinstance(candidate, str) or not _SHA.fullmatch(candidate)
            or not isinstance(report, dict) or report.get("merge_sha") != merge_sha
            or not isinstance(merge_sha, str) or not _SHA.fullmatch(merge_sha)):
        return _unknown(reason="release_report_provenance_unverified",
                        run_id=run_id, merge_sha=merge_sha)
    raw = report.get("product_readiness")
    raw = raw if isinstance(raw, dict) else {}
    reported = raw.get("status")
    if reported == "not_assessed" and raw.get("ready") is not True:
        state, reason = "not_assessed", "global_readiness_not_assessed"
    elif reported in ("not_ready", "failed") and raw.get("ready") is not True:
        state, reason = "not_ready", "candidate_readiness_not_ready"
    elif reported == "passed" and raw.get("ready") is True:
        state, reason = "candidate_only", "candidate_assessment_not_current_head"
    else:
        state, reason = "unknown", "global_readiness_evidence_incomplete"
    candidate_domains = []
    domains = raw.get("domains")
    if isinstance(domains, dict):
        candidate_domains = [
            key for key in _DOMAINS if isinstance(domains.get(key),dict)
            and domains[key].get("status") in {"passed", "not_applicable"}
        ]
    return {
        "scope": "current_product_after_release",
        "status": state,
        "ready": False,
        "reason_code": reason,
        "next_step": "global_product_readiness_audit",
        "release_run_id": run_id,
        "merge_sha": merge_sha,
        "report_verified": True,
        "pending_domains": list(_DOMAINS),
        "candidate_assessed_domains": candidate_domains,
    }


def validated_manifest_followup(manifest: object) -> dict | None:
    """Expose only trusted, fixed vocabulary from a persisted handoff."""
    if not isinstance(manifest, dict):
        return None
    last = manifest.get("last_release")
    raw = manifest.get("product_readiness_followup")
    if not isinstance(last, dict) or not isinstance(raw, dict):
        return None
    run = last.get("run_id")
    sha = last.get("merge_sha")
    if (not isinstance(run,str) or not _UUID.fullmatch(run)
            or not isinstance(sha,str) or not _SHA.fullmatch(sha)
            or raw.get("release_run_id") != run or raw.get("merge_sha") != sha
            or raw.get("scope") != "current_product_after_release"
            or raw.get("status") not in _STATES or raw.get("ready") is not False
            or type(raw.get("report_verified")) is not bool
            or raw.get("pending_domains") != list(_DOMAINS)):
        return None
    allowed_reasons = {
        "release_identity_unverified",
        "release_report_unavailable_or_ambiguous", "release_report_identity_unverified",
        "release_report_provenance_unverified", "global_readiness_not_assessed",
        "candidate_readiness_not_ready", "candidate_assessment_not_current_head",
        "global_readiness_evidence_incomplete",
    }
    if (raw.get("reason_code") not in allowed_reasons
            or raw.get("next_step") not in {
                "global_product_readiness_audit",
                "verify_release_evidence_then_global_audit",
            }):
        return None
    candidate = raw.get("candidate_assessed_domains")
    if (not isinstance(candidate,list) or len(candidate) != len(set(candidate))
            or any(domain not in _DOMAINS for domain in candidate)):
        return None
    return {
        "scope": "current_product_after_release",
        "status": raw["status"],
        "ready": False,
        "reason_code": raw["reason_code"],
        "next_step": raw["next_step"],
        "release_run_id": run,
        "merge_sha": sha,
        "report_verified": raw["report_verified"],
        "pending_domains": list(_DOMAINS),
        "candidate_assessed_domains": list(candidate),
    }


def observe_manifest_release(*, get, project_id: str, manifest: object) -> dict | None:
    """Read newest exact release receipt if prior handoff predates this feature.

    Missing connection/row remains unknown, never 'passed'. Never read a
    cross-project report. All PostgREST filters are strict validated UUIDs.
    """
    if not isinstance(manifest, dict):
        return None
    saved = validated_manifest_followup(manifest)
    if saved is not None:
        return saved
    last = manifest.get("last_release")
    if not isinstance(last, dict):
        return None
    run = last.get("run_id")
    sha = last.get("merge_sha")
    if (not isinstance(project_id,str) or not _UUID.fullmatch(project_id)
            or not isinstance(run,str) or not _UUID.fullmatch(run)
            or not isinstance(sha,str) or not _SHA.fullmatch(sha)):
        return None
    try:
        rows = get(
            "factory_release_reports?"
            "select=project_id,run_id,status,candidate_commit,report"
            "&project_id=eq." + quote(project_id, safe="")
            + "&run_id=eq." + quote(run, safe="") + "&limit=2"
        )
    except (RuntimeError, ValueError, OSError, TimeoutError):
        rows = None
    return summarize_released_product(
        project_id=project_id,run_id=run,merge_sha=sha,report_rows=rows
    )
