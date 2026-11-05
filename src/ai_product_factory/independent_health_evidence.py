"""Independent, fail-closed health evidence for the AI Product Factory.

Source boundaries: GitHub exact-HEAD and Vercel provider status (NOT a Vercel
API READY claim), live HTTPS Console build identity, authoritative schedule
observations, and privileged read-only Control Plane inventory. A single 200
response or a canceled ignored-build status never grants a PASS.

No production writes, model calls, schedule dispatches or new credentials.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping

from .product_readiness_certification import VerifiedCriterionEvidence

REPO = "leandrosilveiradepaula/ai-product-factory"
CONSOLE_SERVICE = "ai-product-factory-console"
HEALTH_URL = "https://ai-product-factory-console.vercel.app/api/health"
VERCEL_TARGET_PREFIX = (
    "https://vercel.com/leandros-projects-102e32ab/"
    "ai-product-factory-console/"
)
VERCEL_APP_AVATAR = "https://avatars.githubusercontent.com/in/8329"
TRUSTED_WORKFLOW = REPO + "/.github/workflows/autonomous-runner.yml@refs/heads/main"
SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
PREFIX = re.compile(r"[0-9a-f]{12}\Z", re.ASCII)
DEPLOYMENT = re.compile(r"[A-Za-z0-9]{12,48}\Z", re.ASCII)
MAX_PROJECTS = 25


class HealthEvidenceBlocked(RuntimeError):
    """Fixed reason code; never includes remote payload, secrets, or token."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise HealthEvidenceBlocked(code)


def timestamp(value: object) -> datetime:
    require(isinstance(value, str) and bool(value), "health_timestamp_absent")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HealthEvidenceBlocked("health_timestamp_invalid") from exc
    require(result.tzinfo is not None, "health_timestamp_naive")
    return result.astimezone(timezone.utc)


def public_console_get(url: str) -> tuple[int, Mapping[str, str], bytes]:
    """Canonical unauthenticated endpoint; never forward a GitHub/CP secret."""
    require(url == HEALTH_URL, "health_endpoint_not_allowlisted")
    req = urllib.request.Request(
        HEALTH_URL, headers={"Accept": "application/json"}, method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            require(response.geturl() == HEALTH_URL, "health_endpoint_redirected")
            return response.status, {
                "content-type": response.headers.get("content-type", ""),
            }, response.read(4097)
    except urllib.error.HTTPError as exc:
        # No untrusted HTTP body is surfaced in a diagnostic.
        raise HealthEvidenceBlocked("health_endpoint_http_failed") from exc


def read_rows(cp_get: Callable[[str], object], route: str, limit: int) -> list[dict]:
    found = cp_get(route)
    require(
        isinstance(found, list)
        and 0 < len(found) < limit
        and all(isinstance(row, dict) for row in found),
        "health_control_plane_inventory_unavailable_or_truncated",
    )
    return found


def verify_probes(
    cp_get: Callable[[str], object], *, now: datetime
) -> tuple[str, str]:
    events = read_rows(
        cp_get,
        "factory_audit_events?select=event_type,actor_type,actor_ref,created_at,payload"
        "&event_type=eq.schedule_probe.observed&order=created_at.desc,id.desc&limit=4",
        limit=5,
    )
    require(len(events) >= 2, "health_scheduler_pair_missing")
    dates = []
    for event in events[:2]:
        require(
            event.get("event_type") == "schedule_probe.observed"
            and event.get("actor_type") == "system"
            and event.get("actor_ref") == "schedule-probe",
            "health_scheduler_actor_not_verified",
        )
        details = event.get("payload")
        require(isinstance(details, dict)
                and type(details.get("work_detected")) is bool,
                "health_scheduler_signal_invalid")
        diag = details.get("queue_diagnostics")
        require(isinstance(diag, dict)
                and diag.get("queue_signal_source") == "authoritative_rpc",
                "health_scheduler_rpc_not_authoritative")
        fields = (
            "queued_tasks", "queued_execution_tasks", "eligible_product_tasks",
            "stale_integration_change_sets",
            "queued_execution_without_queued_run",
        )
        require(
            all(type(diag.get(field)) is int and diag[field] >= 0
                for field in fields),
            "health_scheduler_counters_unverified",
        )
        require(
            diag["stale_integration_change_sets"] == 0
            and diag["queued_execution_without_queued_run"] == 0,
            "health_scheduler_inconsistent_lineage",
        )
        if details["work_detected"] is False:
            require(
                diag["queued_tasks"] == 0 and diag["eligible_product_tasks"] == 0
                and diag["queued_execution_tasks"] == 0,
                "health_scheduler_false_idle",
            )
        observed = timestamp(event.get("created_at"))
        require(
            now - timedelta(minutes=50) <= observed <= now + timedelta(seconds=90),
            "health_scheduler_event_stale_or_future",
        )
        dates.append(observed)
    require(
        dates[0] > dates[1] and dates[0] - dates[1] >= timedelta(minutes=10)
        and now - dates[0] <= timedelta(minutes=25),
        "health_scheduler_cadence_invalid",
    )
    return dates[0].isoformat(), dates[1].isoformat()


def verify_control_plane(cp_get: Callable[[str], object]) -> int:
    projects = read_rows(
        cp_get,
        "factory_projects?select=id,project_key,is_active"
        "&is_active=eq.true&limit=25",
        limit=26,
    )
    controls = read_rows(
        cp_get,
        "factory_project_execution_controls?select=project_id,state,generation"
        "&limit=25",
        limit=26,
    )
    ids = [row.get("id") for row in projects]
    require(
        len(ids) == len(set(ids))
        and all(isinstance(pid, str) and len(pid) == 36 for pid in ids)
        and any(row.get("project_key") == "ai-product-factory" for row in projects)
        and all(row.get("is_active") is True for row in projects),
        "health_active_project_identity_invalid",
    )
    by_id = {row.get("project_id"): row for row in controls}
    require(len(by_id) == len(controls), "health_project_controls_duplicated")
    require(
        all(
            pid in by_id
            and by_id[pid].get("state") in ("running", "paused", "stopped")
            and type(by_id[pid].get("generation")) is int
            and by_id[pid]["generation"] >= 0
            for pid in ids
        ),
        "health_project_controls_incomplete",
    )
    factory = next(row for row in projects if row.get("project_key") == "ai-product-factory")
    require(by_id[factory["id"]].get("state") == "running",
            "health_factory_operator_control_not_running")
    return len(ids)


def verify_vercel_provider_status(github_get: Callable[[str], object], *, sha: str) -> str:
    """GitHub-verified Vercel COMPLETED status, not Vercel API READY.

    We require that the live Console itself serves this exact commit prefix;
    a canceled ignored-build status on the current main SHA is not accepted.
    """
    root = "/repos/" + REPO
    combined = github_get(root + "/commits/" + sha + "/status")
    statuses = combined.get("statuses") if isinstance(combined, dict) else None
    require(isinstance(statuses, list) and 0 < len(statuses) <= 100,
            "health_vercel_status_inventory_incomplete")
    provider = [s for s in statuses
                if isinstance(s, dict) and s.get("context") == "Vercel"]
    require(bool(provider), "health_vercel_provider_status_missing")
    status = provider[0]
    target = status.get("target_url")
    require(
        status.get("state") == "success"
        and status.get("description") == "Deployment has completed"
        and isinstance(status.get("avatar_url"), str)
        and status["avatar_url"].startswith(VERCEL_APP_AVATAR)
        and isinstance(target, str)
        and target.startswith(VERCEL_TARGET_PREFIX)
        and DEPLOYMENT.fullmatch(target[len(VERCEL_TARGET_PREFIX):]) is not None,
        "health_vercel_deployment_not_confirmed",
    )
    return target


@dataclass(frozen=True)
class HealthEvidence:
    assessed_commit: str
    deployed_commit: str
    provider_deployment_url: str
    last_probe: str
    previous_probe: str
    active_projects: int
    source: str = "github_vercel_status+live_https+control_plane_rpc"
    production_released: bool = False
    product_ready: bool = False
    writes: int = 0
    paid_calls: int = 0


def verify_operational_health(
    *, repository: str, assessed_commit: str,
    github_get: Callable[[str], object],
    cp_get: Callable[[str], object],
    console_get: Callable[[str], tuple[int, Mapping[str, str], bytes]] = public_console_get,
    now: datetime,
) -> HealthEvidence:
    """Independent bounded read-only proof for observability/health ONLY."""
    require(repository == REPO and isinstance(assessed_commit, str)
            and SHA.fullmatch(assessed_commit) is not None,
            "health_repository_or_sha_invalid")
    require(isinstance(now, datetime) and now.tzinfo is not None,
            "health_clock_invalid")
    now = now.astimezone(timezone.utc)
    root = "/repos/" + REPO
    head = github_get(root + "/git/ref/heads/main")
    require(
        isinstance(head, dict) and isinstance(head.get("object"), dict)
        and head["object"].get("sha") == assessed_commit,
        "health_assessment_sha_stale",
    )
    status_code, headers, raw = console_get(HEALTH_URL)
    require(
        type(status_code) is int and status_code == 200
        and isinstance(headers, Mapping)
        and "application/json" in headers.get("content-type", "").lower(),
        "health_console_http_unverified",
    )
    require(isinstance(raw, bytes) and 0 < len(raw) <= 4096,
            "health_console_body_unbounded")
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise HealthEvidenceBlocked("health_console_json_invalid") from exc
    prefix = body.get("commit") if isinstance(body, dict) else None
    require(
        isinstance(body, dict) and body.get("status") == "ok"
        and body.get("service") == CONSOLE_SERVICE
        and isinstance(prefix, str) and PREFIX.fullmatch(prefix) is not None,
        "health_console_identity_invalid",
    )
    deployed = github_get(root + "/commits/" + prefix)
    deploy_sha = deployed.get("sha") if isinstance(deployed, dict) else None
    require(
        isinstance(deploy_sha, str) and SHA.fullmatch(deploy_sha) is not None
        and deploy_sha.startswith(prefix),
        "health_console_commit_unresolved",
    )
    provider = verify_vercel_provider_status(github_get, sha=deploy_sha)
    compare = github_get(root + "/compare/" + deploy_sha + "..." + assessed_commit)
    files = compare.get("files") if isinstance(compare, dict) else None
    require(
        isinstance(compare, dict)
        and compare.get("status") in ("ahead", "identical")
        and compare.get("behind_by") == 0
        and type(compare.get("total_commits")) is int
        and 0 <= compare["total_commits"] <= 250
        and isinstance(compare.get("merge_base_commit"), dict)
        and compare["merge_base_commit"].get("sha") == deploy_sha
        and isinstance(files, list) and len(files) < 300
        and all(isinstance(x, dict) and isinstance(x.get("filename"), str)
                for x in files)
        and not any(x["filename"].startswith("apps/console/")
                    for x in files),
        "health_console_source_changed_or_unverifiable",
    )
    most_recent, previous = verify_probes(cp_get, now=now)
    project_count = verify_control_plane(cp_get)
    latest = github_get(root + "/git/ref/heads/main")
    require(
        isinstance(latest, dict) and isinstance(latest.get("object"), dict)
        and latest["object"].get("sha") == assessed_commit,
        "health_main_sha_drift_during_probe",
    )
    return HealthEvidence(
        assessed_commit=assessed_commit, deployed_commit=deploy_sha,
        provider_deployment_url=provider,
        last_probe=most_recent, previous_probe=previous,
        active_projects=project_count,
    )


def verify_health_for_certification(
    *, repository: str, assessed_commit: str,
    github_get: Callable[[str], object],
    control_plane_get: Callable[[str], object] | None = None,
    console_get: Callable[[str], tuple[int, Mapping[str, str], bytes]] = public_console_get,
    now: datetime | None = None,
    environment: Mapping[str, str] | None = None,
) -> VerifiedCriterionEvidence:
    """Positive proof is produced ONLY inside the trusted post-CI runner."""
    env = os.environ if environment is None else environment
    require(
        env.get("GITHUB_ACTIONS") == "true"
        and env.get("GITHUB_REPOSITORY") == REPO
        and env.get("GITHUB_WORKFLOW_REF") == TRUSTED_WORKFLOW
        and env.get("GITHUB_EVENT_NAME") == "workflow_run"
        and env.get("GITHUB_REF") == "refs/heads/main",
        "health_trusted_runner_identity_mismatch",
    )
    if control_plane_get is None:
        # The existing OIDC broker supplies scoped GET-only Control Plane API
        # access. The GitHub token remains confined to the GitHub client.
        from .admission_diagnostics import SupabaseAdmissionReader
        control_plane_get = SupabaseAdmissionReader()._get
    evidence = verify_operational_health(
        repository=repository, assessed_commit=assessed_commit,
        github_get=github_get, cp_get=control_plane_get,
        console_get=console_get,
        now=datetime.now(timezone.utc) if now is None else now,
    )
    digest = hashlib.sha256(
        json.dumps(evidence.__dict__, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return VerifiedCriterionEvidence(
        domain="observability_operations", criterion="health",
        repository=repository, assessed_commit=assessed_commit,
        verification_state="observed",
        source="source-verified-factory-health-github-provider-live-cp:" + digest,
        evidence=(
            "https://github.com/" + repository + "/actions/runs/"
            + env.get("GITHUB_RUN_ID", "") + "#sha=" + assessed_commit,
        ),
    )
