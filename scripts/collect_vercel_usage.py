from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib import parse, request

JsonRequest = Callable[[str, str, dict[str, str], dict[str, Any] | None], Any]


def _request_json(method, url, headers, payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers=headers, method=method)
    with request.urlopen(req, timeout=30) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else None


def list_team_deployments(*, token, team_id, since_ms, request_json=_request_json):
    """Return unique deployments created within a rolling time window."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    until = None
    visited = set()
    deployments = {}
    while True:
        params = {"teamId": team_id, "since": str(since_ms), "limit": "100"}
        if until is not None:
            params["until"] = str(until)
        url = "https://api.vercel.com/v7/deployments?" + parse.urlencode(params)
        page = request_json("GET", url, headers, None)
        rows = page.get("deployments", [])
        if not isinstance(rows, list):
            raise ValueError("Vercel deployments response is malformed")
        for row in rows:
            if not isinstance(row, dict):
                continue
            created = row.get("createdAt", row.get("created"))
            if created is None or int(created) < since_ms:
                continue
            deployment_id = str(row.get("uid") or row.get("id") or "")
            if deployment_id:
                deployments[deployment_id] = row
        next_cursor = (page.get("pagination") or {}).get("next")
        if next_cursor is None or not rows:
            break
        next_cursor = int(next_cursor)
        if next_cursor < since_ms or next_cursor in visited:
            break
        if until is not None and next_cursor >= until:
            raise ValueError("Vercel pagination cursor did not move backwards")
        visited.add(next_cursor)
        until = next_cursor
    return list(deployments.values())


def record_snapshot(*, supabase_url, oidc_token, used, window_started_at, project_counts, request_json=_request_json):
    headers = {
        "Authorization": f"Bearer {oidc_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "p_provider": "vercel",
        "p_resource_key": "team",
        "p_metric_key": "deployments_daily",
        "p_used_value": used,
        "p_limit_value": 100,
        "p_unit": "deployments",
        "p_window_key": "rolling_24h",
        "p_window_started_at": window_started_at,
        "p_resets_at": None,
        "p_quality": "derived",
        "p_source": "vercel-deployments-api",
        "p_metadata": {"project_counts": project_counts},
    }
    url = supabase_url.rstrip("/") + "/rest/v1/rpc/factory_record_resource_limit"
    return request_json("POST", url, headers, payload)


def collect(*, vercel_token, team_id, supabase_url, oidc_token, now=None, request_json=_request_json):
    observed_at = now or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        raise ValueError("now must include a timezone")
    window_start = observed_at.astimezone(timezone.utc) - timedelta(hours=24)
    since_ms = int(window_start.timestamp() * 1000)
    deployments = list_team_deployments(
        token=vercel_token, team_id=team_id, since_ms=since_ms, request_json=request_json
    )
    projects = Counter(str(item.get("projectId") or "unknown") for item in deployments)
    record_snapshot(
        supabase_url=supabase_url,
        oidc_token=oidc_token,
        used=len(deployments),
        window_started_at=window_start.isoformat(timespec="seconds").replace("+00:00", "Z"),
        project_counts=dict(sorted(projects.items())),
        request_json=request_json,
    )
    return {"metric": "deployments_daily", "window": "rolling_24h", "used": len(deployments), "limit": 100}


def main():
    names = ("VERCEL_TOKEN", "FACTORY_VERCEL_TEAM_ID", "SUPABASE_URL", "SUPABASE_SECRET_KEY")
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise SystemExit("Missing required environment variables: " + ", ".join(missing))
    result = collect(
        vercel_token=os.environ["VERCEL_TOKEN"],
        team_id=os.environ["FACTORY_VERCEL_TEAM_ID"],
        supabase_url=os.environ["SUPABASE_URL"],
        oidc_token=os.environ["SUPABASE_SECRET_KEY"],
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
