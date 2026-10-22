"""GET-only attestation of a candidate's persisted cross-repository Preview smoke.

A Vercel deployment status or a loosely related Factory CI run alone is never
browser evidence. The newest Control Plane receipt on the exact candidate
must resolve to a successful, uniquely correlated Factory browser job. No
release or product readiness authority is returned by this module.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Callable

FACTORY_REPOSITORY = "leandrosilveiradepaula/ai-product-factory"
_MAX_SNAPSHOTS = 25
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z", re.I)
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_URL = re.compile(r"https://[a-z0-9][a-z0-9.-]{0,230}\.vercel\.app\Z", re.I)


def _instant(value: object) -> datetime:
    if not isinstance(value, str) or len(value) > 50:
        raise ValueError("invalid timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamp not UTC aware")
    return result.astimezone(timezone.utc)


def _blocked(state: str) -> dict:
    return {"state": state, "verified": False, "receipt_id": None,
            "verifier_run_id": None, "verification_scope": None,
            "preview_url": None}


def observe_browser_proof(
    *, project_id: str, repository: str, candidate_sha: str,
    cp_get: Callable[[str], object],
    target_get: Callable[[str], object],
    factory_get: Callable[[str], object] | None,
) -> dict:
    """Verify the latest matching receipt without trusting its assertions.

    A failed/invalid newer exact-SHA receipt may never be overridden by an
    older success. Incomplete inventories and unknown provenance fail closed.
    """
    path = (
        "factory_project_state_snapshots?"
        "select=id,project_id,run_id,observed_stage,created_at,evidence,"
        "source_status,constraints,gaps"
        "&project_id=eq." + project_id
        + "&observed_stage=eq.verification&order=created_at.desc&limit=25"
    )
    try:
        rows = cp_get(path)
        if (not isinstance(rows, list) or len(rows) > _MAX_SNAPSHOTS
                or any(not isinstance(row, dict) or row.get("project_id") != project_id
                       or row.get("observed_stage") != "verification" for row in rows)):
            return _blocked("unverifiable_snapshot_inventory")
        # REST order is descending; independently validate timestamps instead
        # of using server-provided ordering as proof of recency.
        stamped = sorted(((_instant(row.get("created_at")), row) for row in rows),
                         key=lambda pair: pair[0], reverse=True)
        matched = [item for item in stamped
                   if isinstance(item[1].get("evidence"), dict)
                   and item[1]["evidence"].get("candidate_commit") == candidate_sha
                   and item[1]["evidence"].get("target_repository") == repository]
        if not matched:
            return _blocked("no_exact_sha_browser_receipt")
        created_at, row = matched[0]
        now = datetime.now(timezone.utc)
        if created_at > now + timedelta(minutes=2) or now - created_at > timedelta(days=14):
            return _blocked("expired_or_future_browser_receipt")
        if (not isinstance(row.get("id"), str) or not _UUID.fullmatch(row["id"])
                or row.get("run_id") is not None):
            return _blocked("invalid_browser_receipt")
        evidence = row["evidence"]
        preview = evidence.get("preview")
        source = row.get("source_status")
        constraints = row.get("constraints")
        if (not isinstance(preview, dict)
                or preview.get("provider") != "vercel"
                or preview.get("status") != "browser_verified"
                or not isinstance(source, dict)
                or source.get("github_target") != "verified"
                or source.get("vercel_preview") != "resolved"
                or source.get("browser_visual_validation") != "success"
                or row.get("gaps") != []
                or not isinstance(constraints, dict)
                or any(constraints.get(key) is not False for key in (
                    "production_merge_authorized", "product_ready_inferred",
                    "release_candidate_ready_inferred"))):
            return _blocked("invalid_browser_receipt")

        url = preview.get("url")
        request_id = preview.get("browser_request_id")
        run_id = preview.get("browser_verifier_run_id")
        factory_sha = preview.get("verifier_factory_commit")
        if (not isinstance(url, str) or not _URL.fullmatch(url)
                or not isinstance(request_id, str) or not _UUID.fullmatch(request_id)
                or type(run_id) is not int or run_id < 1
                or not isinstance(factory_sha, str) or not _SHA.fullmatch(factory_sha)
                or preview.get("browser_verifier_run_url") !=
                   f"https://github.com/{FACTORY_REPOSITORY}/actions/runs/{run_id}"):
            return _blocked("invalid_browser_receipt")
        if factory_get is None:
            return _blocked("browser_verifier_unavailable")

        # Factory GITHUB_TOKEN is used for this fixed, same-repository path;
        # the target-repo GitHub App/token is never used to query this proof.
        prefix = f"/repos/{FACTORY_REPOSITORY}/actions/runs/{run_id}"
        run = factory_get(prefix)
        if (not isinstance(run, dict) or run.get("id") != run_id
                or run.get("repository", {}).get("full_name") != FACTORY_REPOSITORY
                or run.get("path") != ".github/workflows/console-browser-evidence.yml"
                or run.get("event") != "workflow_dispatch"
                or run.get("run_attempt") != 1
                or run.get("head_branch") != "main"
                or run.get("head_sha") != factory_sha
                or run.get("display_title") != "Console evidence " + request_id
                or run.get("status") != "completed"
                or run.get("conclusion") != "success"
                or run.get("html_url") != preview["browser_verifier_run_url"]):
            return _blocked("browser_verifier_mismatch")
        start, finish = _instant(run.get("created_at")), _instant(run.get("updated_at"))
        if not (start <= finish <= created_at + timedelta(minutes=2)):
            return _blocked("browser_verifier_mismatch")
        jobs = factory_get(prefix + "/jobs?per_page=100")
        if (not isinstance(jobs, dict) or jobs.get("total_count") != 1
                or not isinstance(jobs.get("jobs"), list) or len(jobs["jobs"]) != 1):
            return _blocked("browser_verifier_mismatch")
        job = jobs["jobs"][0]
        if (not isinstance(job, dict)
                or job.get("name") != "browser-evidence"
                or job.get("run_id") != run_id
                or job.get("head_sha") != factory_sha
                or job.get("status") != "completed"
                or job.get("conclusion") != "success"):
            return _blocked("browser_verifier_mismatch")

        status = target_get(
            f"/repos/{repository}/commits/{candidate_sha}/status"
        )
        if (not isinstance(status, dict) or status.get("sha") != candidate_sha
                or not isinstance(status.get("statuses"), list)
                or len(status["statuses"]) > 100):
            return _blocked("vercel_ready_not_current")
        vercel = [s for s in status["statuses"]
                  if isinstance(s, dict) and s.get("context") == "Vercel"]
        if not vercel or vercel[0].get("state") != "success":
            return _blocked("vercel_ready_not_current")
        return {
            "state": "verified", "verified": True, "receipt_id": row["id"],
            "verifier_run_id": run_id,
            "verification_scope": "public_preview_browser_smoke_only",
            "preview_url": url,
        }
    except (ValueError, TypeError, OverflowError, KeyError, AttributeError):
        return _blocked("unverifiable_browser_provenance")
