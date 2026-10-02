from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from urllib import parse, request

MAX_SNAPSHOT_AGE_SECONDS = 8 * 60 * 60


def _request_json(method: str, url: str, headers: dict[str, str], payload: dict | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers=headers, method=method)
    with request.urlopen(req, timeout=30) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else None


def evaluate_quota(snapshot: dict, *, now: datetime) -> dict:
    observed_raw = str(snapshot.get("observed_at") or "")
    if not observed_raw:
        return {"allowed": False, "state": "blocked_unknown", "reason": "missing observed_at"}
    observed = datetime.fromisoformat(observed_raw.replace("Z", "+00:00"))
    if observed.tzinfo is None:
        return {"allowed": False, "state": "blocked_unknown", "reason": "observed_at has no timezone"}
    age = max(0.0, (now.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds())
    if age > MAX_SNAPSHOT_AGE_SECONDS:
        return {"allowed": False, "state": "blocked_stale", "reason": f"snapshot is stale ({int(age)}s)"}

    quality = str(snapshot.get("quality") or "")
    if quality in {"unknown", "provider_blocked", ""}:
        return {"allowed": False, "state": "blocked_unknown", "reason": f"snapshot quality is {quality or 'missing'}"}

    used = snapshot.get("used_value")
    limit = snapshot.get("limit_value")
    if used is None or limit is None or float(limit) <= 0:
        return {"allowed": False, "state": "blocked_unknown", "reason": "usage or limit is unavailable"}

    percent = (float(used) / float(limit)) * 100.0
    if percent >= 95:
        return {"allowed": False, "state": "blocked", "reason": "Vercel deployment usage is at or above 95%", "percent": percent}
    if percent >= 85:
        return {"allowed": True, "state": "protection", "reason": "only explicit final candidate Preview is allowed", "percent": percent}
    if percent >= 70:
        return {"allowed": True, "state": "attention", "reason": "Vercel deployment usage is elevated", "percent": percent}
    return {"allowed": True, "state": "normal", "reason": "Vercel deployment usage is within normal range", "percent": percent}


def _headers(token: str, *, json_body: bool = False) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def latest_snapshot(*, base_url: str, token: str, request_json=_request_json) -> dict | None:
    query = parse.urlencode({
        "select": "used_value,limit_value,quality,observed_at",
        "provider": "eq.vercel",
        "resource_key": "eq.team",
        "metric_key": "eq.deployments_daily",
        "order": "observed_at.desc",
        "limit": "1",
    })
    rows = request_json("GET", base_url.rstrip("/") + "/rest/v1/factory_resource_limit_snapshots?" + query, _headers(token), None)
    if not isinstance(rows, list) or not rows:
        return None
    return rows[0]


def project_id(*, base_url: str, token: str, project_key: str, request_json=_request_json) -> str:
    query = parse.urlencode({"select": "id", "project_key": f"eq.{project_key}", "limit": "1"})
    rows = request_json("GET", base_url.rstrip("/") + "/rest/v1/factory_projects?" + query, _headers(token), None)
    if not isinstance(rows, list) or not rows or not rows[0].get("id"):
        raise RuntimeError("Factory project was not found for audit evidence")
    return str(rows[0]["id"])


def record_event(*, base_url: str, token: str, project_key: str, event_type: str, payload: dict, request_json=_request_json) -> None:
    pid = project_id(base_url=base_url, token=token, project_key=project_key, request_json=request_json)
    body = {
        "project_id": pid,
        "actor_type": "system",
        "actor_ref": "github-actions/vercel-preview-guard",
        "event_type": event_type,
        "payload": payload,
    }
    request_json(
        "POST",
        base_url.rstrip("/") + "/rest/v1/factory_audit_events",
        {**_headers(token, json_body=True), "Prefer": "return=minimal"},
        body,
    )


def check_quota(*, base_url: str, token: str, project_key: str, candidate_sha: str, pr_number: int, now: datetime | None = None, request_json=_request_json) -> dict:
    snapshot = latest_snapshot(base_url=base_url, token=token, request_json=request_json)
    if snapshot is None:
        decision = {"allowed": False, "state": "blocked_unknown", "reason": "no Vercel deployment snapshot is available"}
    else:
        decision = evaluate_quota(snapshot, now=now or datetime.now(timezone.utc))
    evidence = {
        "candidate_sha": candidate_sha,
        "pr_number": pr_number,
        "state": decision["state"],
        "reason": decision["reason"],
        "percent": decision.get("percent"),
    }
    record_event(
        base_url=base_url,
        token=token,
        project_key=project_key,
        event_type="preview.quota.blocked" if not decision["allowed"] else "preview.quota.checked",
        payload=evidence,
        request_json=request_json,
    )
    return decision


def _env() -> tuple[str, str]:
    base_url = os.environ.get("SUPABASE_URL", "")
    token = os.environ.get("SUPABASE_SECRET_KEY", "")
    if not base_url or not token:
        raise RuntimeError("Control Plane OIDC environment is unavailable")
    return base_url, token


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    quota = sub.add_parser("quota")
    quota.add_argument("--project-key", required=True)
    quota.add_argument("--candidate-sha", required=True)
    quota.add_argument("--pr-number", type=int, required=True)

    record = sub.add_parser("record")
    record.add_argument("--project-key", required=True)
    record.add_argument("--candidate-sha", required=True)
    record.add_argument("--pr-number", type=int, required=True)
    record.add_argument("--action", choices=("reused", "created", "updated"), required=True)

    args = parser.parse_args()
    base_url, token = _env()

    if args.command == "quota":
        decision = check_quota(
            base_url=base_url,
            token=token,
            project_key=args.project_key,
            candidate_sha=args.candidate_sha,
            pr_number=args.pr_number,
        )
        print(json.dumps(decision, sort_keys=True))
        return 0 if decision["allowed"] else 2

    record_event(
        base_url=base_url,
        token=token,
        project_key=args.project_key,
        event_type="preview.ref." + args.action,
        payload={"candidate_sha": args.candidate_sha, "pr_number": args.pr_number, "action": args.action},
    )
    print(json.dumps({"recorded": True, "action": args.action}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
