from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib import parse, request

if __package__:
    from scripts.collect_vercel_usage import list_team_deployments
    from scripts.vercel_preview_guard import evaluate_quota
else:
    from collect_vercel_usage import list_team_deployments
    from vercel_preview_guard import evaluate_quota

LOCAL_DAILY_LIMIT = 5
JsonRequest = Callable[[str, str, dict[str, str], dict[str, Any] | None], Any]


def _request_json(method: str, url: str, headers: dict[str, str], payload: dict[str, Any] | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers=headers, method=method)
    with request.urlopen(req, timeout=30) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else None


def evaluate_local_budget(successful_runs: int, *, limit: int = LOCAL_DAILY_LIMIT) -> dict[str, Any]:
    state = "local_observation_high" if successful_runs >= limit else "local_observation"
    return {
        "allowed": True,
        "state": state,
        "source": "github_actions",
        "used": successful_runs,
        "limit": limit,
        "authoritative": False,
        "reason": (
            f"local Preview promotion observation is high ({successful_runs}/{limit} in 24h); "
            "provider quota is unavailable, so this count is advisory only"
            if successful_runs >= limit
            else f"local Preview promotion observation ({successful_runs}/{limit} in 24h); provider quota is unavailable"
        ),
    }


def recent_successful_promotions(
    *,
    token: str,
    repository: str,
    current_run_id: str,
    now: datetime,
    request_json: JsonRequest = _request_json,
) -> int:
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required for local Preview promotion observation")
    if "/" not in repository:
        raise RuntimeError("GITHUB_REPOSITORY is invalid")

    cutoff = now.astimezone(timezone.utc) - timedelta(hours=24)
    url = (
        f"https://api.github.com/repos/{repository}/actions/workflows/"
        "promote-preview-candidate.yml/runs?per_page=100"
    )
    payload = request_json(
        "GET",
        url,
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        None,
    )
    rows = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
    count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        run_id = str(row.get("id") or "")
        if not run_id or run_id == str(current_run_id):
            continue
        created_raw = str(row.get("created_at") or "")
        if not created_raw:
            continue
        created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        if created < cutoff:
            continue

        jobs_url = f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/jobs?per_page=100"
        jobs_payload = request_json(
            "GET",
            jobs_url,
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            None,
        )
        jobs = jobs_payload.get("jobs", []) if isinstance(jobs_payload, dict) else []
        promoted = any(
            isinstance(step, dict)
            and step.get("name") == "Create or update one preview ref to the exact candidate"
            and step.get("conclusion") == "success"
            for job in jobs
            if isinstance(job, dict)
            for step in (job.get("steps") or [])
        )
        if promoted:
            count += 1
    return count


def shared_vercel_decision(
    *,
    token: str,
    team_id: str,
    now: datetime,
    request_json: JsonRequest = _request_json,
) -> dict[str, Any]:
    window_start = now.astimezone(timezone.utc) - timedelta(hours=24)
    deployments = list_team_deployments(
        token=token,
        team_id=team_id,
        since_ms=int(window_start.timestamp() * 1000),
        request_json=request_json,
    )
    snapshot = {
        "used_value": len(deployments),
        "limit_value": 100,
        "quality": "derived",
        "observed_at": now.astimezone(timezone.utc).isoformat(),
    }
    decision = evaluate_quota(snapshot, now=now)
    return {
        **decision,
        "source": "vercel_api",
        "used": len(deployments),
        "limit": 100,
    }


def decide(
    *,
    github_token: str,
    repository: str,
    current_run_id: str,
    vercel_token: str = "",
    team_id: str = "",
    now: datetime | None = None,
    request_json: JsonRequest = _request_json,
) -> dict[str, Any]:
    observed_at = now or datetime.now(timezone.utc)

    if vercel_token and team_id:
        try:
            return shared_vercel_decision(
                token=vercel_token,
                team_id=team_id,
                now=observed_at,
                request_json=request_json,
            )
        except Exception as exc:
            fallback_reason = f"Vercel usage read failed; GitHub promotion count is advisory only: {type(exc).__name__}"
    else:
        fallback_reason = "Vercel usage credentials are not configured; GitHub promotion count is advisory only"

    successful_runs = recent_successful_promotions(
        token=github_token,
        repository=repository,
        current_run_id=current_run_id,
        now=observed_at,
        request_json=request_json,
    )
    decision = evaluate_local_budget(successful_runs)
    decision["fallback_reason"] = fallback_reason
    return decision


def main() -> int:
    decision = decide(
        github_token=os.environ.get("GITHUB_TOKEN", ""),
        repository=os.environ.get("GITHUB_REPOSITORY", ""),
        current_run_id=os.environ.get("GITHUB_RUN_ID", ""),
        vercel_token=os.environ.get("VERCEL_TOKEN", ""),
        team_id=os.environ.get("FACTORY_VERCEL_TEAM_ID", ""),
    )
    print(json.dumps(decision, sort_keys=True))
    return 0 if decision["allowed"] else 2


if __name__ == "__main__":
    sys.exit(main())
