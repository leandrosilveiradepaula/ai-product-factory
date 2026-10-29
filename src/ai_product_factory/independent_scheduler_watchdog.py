"""Independent, opt-in GitHub Actions scheduler watchdog.

Run only on a trusted host whose clock and timer are independent of GitHub
Actions. This module never performs work itself, reads the Control Plane,
uses models or merges. It may request one bounded workflow_dispatch.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

REPOSITORY = "leandrosilveiradepaula/ai-product-factory"
REPOSITORY_ID = 1387883686
WORKFLOW = "autonomous-runner.yml"
WORKFLOW_PATH = ".github/workflows/" + WORKFLOW
BRANCH = "main"
API = "https://api.github.com/repos/" + REPOSITORY
API_VERSION = "2026-03-10"
MAX_RESPONSE = 256 * 1024
MAX_ROWS = 20
MAX_JOBS = 100
MAX_GAP = timedelta(hours=2)
RECENT_WAKE = timedelta(minutes=30)
CLOCK_SKEW = timedelta(minutes=2)


class WatchdogError(RuntimeError):
    """Do not print underlying HTTP error contents or credential details."""


def _utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise WatchdogError("invalid_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WatchdogError("invalid_timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WatchdogError("invalid_timestamp")
    return parsed.astimezone(timezone.utc)


def _rows(payload: object, name: str, count_key: str, rows_key: str, limit: int) -> list[dict]:
    if not isinstance(payload, dict):
        raise WatchdogError("invalid_" + name)
    count, rows = payload.get(count_key), payload.get(rows_key)
    if (type(count) is not int or count < 0 or not isinstance(rows, list)
            or len(rows) != min(count, limit) or len(rows) > limit
            or any(not isinstance(row, dict) for row in rows)):
        raise WatchdogError("incomplete_" + name)
    return rows


class GitHubWatchdogClient:
    def __init__(self, token: str, *, opener=None):
        if not isinstance(token, str) or not token.strip() or token != token.strip():
            raise WatchdogError("github_credential_unavailable")
        self._token = token
        self._open = opener or urllib.request.urlopen

    def _request(self, path: str, *, dispatch: bool = False) -> dict | None:
        if not path.startswith("/") or ".." in path or "//" in path:
            raise WatchdogError("invalid_api_path")
        data = json.dumps({"ref": BRANCH}).encode() if dispatch else None
        request = urllib.request.Request(
            "https://api.github.com" + path,
            method="POST" if dispatch else "GET", data=data,
            headers={
                "Authorization": "Bearer " + self._token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                **({"Content-Type": "application/json"} if dispatch else {}),
            },
        )
        try:
            with self._open(request, timeout=15) as response:
                status = response.status
                raw = response.read(MAX_RESPONSE + 1)
        except Exception as exc:
            raise WatchdogError("github_api_unavailable") from exc
        if len(raw) > MAX_RESPONSE:
            raise WatchdogError("github_api_oversized")
        if dispatch:
            if status != 204:
                raise WatchdogError("github_dispatch_not_accepted")
            return None
        if status != 200:
            raise WatchdogError("github_read_not_successful")
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise WatchdogError("invalid_github_json") from exc
        if not isinstance(result, dict):
            raise WatchdogError("invalid_github_json")
        return result

    def verify_target(self) -> None:
        repo = self._request("/repos/" + REPOSITORY)
        workflow = self._request("/repos/" + REPOSITORY + "/actions/workflows/" + WORKFLOW)
        if (repo is None or type(repo.get("id")) is not int
                or repo["id"] != REPOSITORY_ID or repo.get("full_name") != REPOSITORY
                or repo.get("default_branch") != BRANCH
                or workflow is None or workflow.get("path") != WORKFLOW_PATH
                or workflow.get("state") != "active"
                or type(workflow.get("id")) is not int or workflow["id"] <= 0):
            raise WatchdogError("github_target_identity_mismatch")

    def runs(self, *, event: str) -> list[dict]:
        if event not in {"schedule", "workflow_dispatch"}:
            raise WatchdogError("unsupported_event")
        result = self._request(
            "/repos/" + REPOSITORY + "/actions/workflows/" + WORKFLOW
            + "/runs?event=" + event + "&branch=" + BRANCH + "&per_page=" + str(MAX_ROWS)
        )
        assert result is not None
        rows = _rows(result, "workflow_runs", "total_count", "workflow_runs", MAX_ROWS)
        seen: set[int] = set()
        prev: datetime | None = None
        for row in rows:
            ident = row.get("id")
            created = _utc(row.get("created_at"))
            if (type(ident) is not int or ident < 1 or ident in seen
                    or row.get("event") != event or row.get("path") != WORKFLOW_PATH
                    or row.get("head_branch") != BRANCH
                    or (row.get("repository") or {}).get("full_name") != REPOSITORY
                    or (prev is not None and created > prev)):
                raise WatchdogError("untrusted_workflow_run")
            seen.add(ident)
            prev = created
        return rows

    def probe_succeeded(self, run: dict) -> bool:
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            return False
        result = self._request(
            "/repos/" + REPOSITORY + "/actions/runs/" + str(run["id"])
            + "/jobs?per_page=" + str(MAX_JOBS)
        )
        assert result is not None
        jobs = _rows(result, "workflow_jobs", "total_count", "jobs", MAX_JOBS)
        matched = [job for job in jobs if job.get("name") == "schedule-probe"]
        if len(matched) != 1:
            raise WatchdogError("schedule_probe_job_missing_or_duplicate")
        job = matched[0]
        if (job.get("run_id") != run["id"]
                or job.get("head_sha") != run.get("head_sha")):
            raise WatchdogError("schedule_probe_job_identity_mismatch")
        return job.get("status") == "completed" and job.get("conclusion") == "success"

    def dispatch(self) -> None:
        self._request(
            "/repos/" + REPOSITORY + "/actions/workflows/" + WORKFLOW + "/dispatches",
            dispatch=True,
        )


def decide(client: GitHubWatchdogClient, *, now: datetime) -> str:
    if now.tzinfo is None or now.utcoffset() is None:
        raise WatchdogError("invalid_clock")
    now = now.astimezone(timezone.utc)
    client.verify_target()
    native = client.runs(event="schedule")
    if any(_utc(run["created_at"]) > now + CLOCK_SKEW for run in native):
        raise WatchdogError("future_scheduler_run")
    # A currently starting native workflow can settle itself without a
    # duplicate external dispatch. A hanging run is not a permanent veto.
    if (native and native[0].get("status") in {"queued", "in_progress", "waiting"}
            and now - _utc(native[0]["created_at"]) < RECENT_WAKE):
        return "native_in_progress"
    healthy = (len(native) >= 2
        and native[0].get("status") == "completed"
        and native[1].get("status") == "completed"
        and now - _utc(native[0]["created_at"]) < MAX_GAP
        and timedelta(0) < _utc(native[0]["created_at"]) - _utc(native[1]["created_at"]) < MAX_GAP
        and client.probe_succeeded(native[0]) and client.probe_succeeded(native[1]))
    if healthy:
        return "native_healthy"
    manual = client.runs(event="workflow_dispatch")
    if any(_utc(run["created_at"]) > now + CLOCK_SKEW for run in manual):
        raise WatchdogError("future_dispatch_run")
    if manual and now - _utc(manual[0]["created_at"]) < RECENT_WAKE:
        return "recent_dispatch"
    return "wake_due"


def run(*, token: str, execute: bool, enabled: bool,
        now: datetime | None = None, opener=None) -> dict:
    # This is a *separate* activation boundary from GitHub's schedule.
    # The default is read-only, including if --execute was supplied.
    if execute and not enabled:
        return {"status": "blocked", "reason_code": "explicit_activation_required"}
    if not token:
        return {"status": "blocked", "reason_code": "github_credential_unavailable"}
    client = GitHubWatchdogClient(token, opener=opener)
    decision = decide(client, now=now or datetime.now(timezone.utc))
    if decision != "wake_due":
        return {"status": "skipped", "reason_code": decision}
    if not execute:
        return {"status": "would_dispatch", "reason_code": "native_scheduler_gap"}
    client.dispatch()
    return {"status": "dispatch_accepted", "reason_code": "github_http_204_not_execution_proof"}


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Independent GitHub schedule failover (opt-in)")
    parser.add_argument("--execute", action="store_true", help="Request a bounded GitHub workflow dispatch")
    args = parser.parse_args(argv)
    try:
        output = run(
            token=os.environ.get("FACTORY_EXTERNAL_GITHUB_TOKEN", ""),
            execute=args.execute,
            enabled=os.environ.get("FACTORY_EXTERNAL_SCHEDULER_ENABLED") == "true",
        )
    except Exception as exc:
        # Never include untrusted HTTP/OS exception messages in output.
        output = {"status": "blocked", "reason_code": "verification_or_transport_unavailable",
                  "error_class": type(exc).__name__ if type(exc).__name__ in
                  {"WatchdogError", "HTTPError", "URLError", "TimeoutError"} else "unexpected_error"}
    print(json.dumps({**output, "paid_calls": 0, "production_merge": False}, sort_keys=True))
    return 2 if output["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
