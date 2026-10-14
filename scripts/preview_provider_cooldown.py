"""Fail-closed preflight for a known Vercel deployment rate-limit observation.

Reads open and recently closed GitHub PR commit statuses; no Vercel API key, billing or mutations.
Absence of a rate-limit signal is NOT evidence that provider quota is available.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib import request

JSONRequest = Callable[[str, str, dict[str, str]], Any]
SHA = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")
MAX_RECENT_PRS = 50
WINDOW = timedelta(hours=24)


def _get_json(method: str, url: str, headers: dict[str, str]):
    req = request.Request(url, headers=headers, method=method)
    with request.urlopen(req, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def _parse_timestamp(raw: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("GitHub status timestamp is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError("GitHub status timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


def observe_rate_limit(
    *, token: str, repository: str, now: datetime | None = None, get_json: JSONRequest = _get_json
) -> dict[str, Any]:
    if not token or not REPO.fullmatch(repository):
        raise RuntimeError("GitHub Preview cooldown requires valid repository and GITHUB_TOKEN")
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("now must include timezone")
    now_utc = observed.astimezone(timezone.utc)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    root = f"https://api.github.com/repos/{repository}"
    # Include recently closed PRs: the Vercel rate limit is shared beyond one
    # PR's lifecycle. Most recent PRs first; a truncated recent window fails shut.
    pulls = get_json(
        "GET", f"{root}/pulls?state=all&sort=updated&direction=desc&per_page=100", headers
    )
    if not isinstance(pulls, list) or len(pulls) > 100:
        raise RuntimeError("recent PR inventory is incomplete or malformed")
    cutoff = now_utc - WINDOW
    candidates = []
    for pull in pulls:
        if not isinstance(pull, dict):
            raise RuntimeError("invalid PR inventory item")
        state = pull.get("state")
        if state not in ("open", "closed"):
            raise RuntimeError("invalid PR state")
        updated_raw = pull.get("updated_at")
        if not isinstance(updated_raw, str):
            raise RuntimeError("PR inventory has missing update timestamp")
        updated_at = _parse_timestamp(updated_raw)
        if updated_at > now_utc + timedelta(minutes=5):
            raise RuntimeError("PR inventory timestamp exceeds clock tolerance")
        if state == "open" or updated_at >= cutoff:
            candidates.append(pull)
    if len(pulls) == 100:
        oldest = _parse_timestamp(pulls[-1]["updated_at"])
        if oldest >= cutoff:
            raise RuntimeError("recent PR inventory is paginated and incomplete")
    if len(candidates) > MAX_RECENT_PRS:
        raise RuntimeError("recent PR inventory exceeds safe bound")
    seen = set()
    for pull in candidates:
        sha = (pull.get("head") or {}).get("sha")
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise RuntimeError("invalid open or recent PR candidate SHA")
        if sha in seen:
            continue
        seen.add(sha)
        response = get_json("GET", f"{root}/commits/{sha}/status", headers)
        statuses = response.get("statuses") if isinstance(response, dict) else None
        if not isinstance(statuses, list) or len(statuses) > 100:
            raise RuntimeError("missing or incomplete GitHub commit statuses")
        vercel = []
        for item in statuses:
            if not isinstance(item, dict):
                raise RuntimeError("invalid GitHub commit status")
            if item.get("context") != "Vercel":
                continue
            stamp = item.get("updated_at") or item.get("created_at")
            if not isinstance(stamp, str):
                raise RuntimeError("Vercel status has no timestamp")
            at = _parse_timestamp(stamp)
            if at > now_utc + timedelta(minutes=5):
                raise RuntimeError("Vercel status timestamp exceeds clock tolerance")
            vercel.append((at, item))
        # GitHub statuses contain historical states for a context. A newer
        # success clears a previous failure on that SHA; pending does not.
        vercel.sort(key=lambda value: value[0], reverse=True)
        latest_success = next(
            (stamp for stamp, row in vercel if row.get("state") == "success"), None
        )
        for recorded, item in vercel:
            if item.get("state") != "failure":
                continue
            description = str(item.get("description") or "").casefold()
            if "deployment rate limited" not in description:
                continue
            if latest_success is not None and latest_success > recorded:
                continue
            if now_utc < recorded + WINDOW:
                return {
                    "allowed": False, "state": "provider_rate_limited",
                    "source": "github_vercel_commit_status",
                    "observed_at": recorded.isoformat(),
                    "earliest_recheck_at": (recorded + WINDOW).isoformat(),
                    "sha": sha,
                }
    return {
        "allowed": True, "state": "no_recent_rate_limit_observed",
        "source": "github_vercel_commit_status",
        "authoritative_quota": False, "checked_prs": len(candidates),
    }


def main() -> int:
    result = observe_rate_limit(
        token=os.environ.get("GITHUB_TOKEN", ""),
        repository=os.environ.get("GITHUB_REPOSITORY", ""),
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["allowed"] else 2


if __name__ == "__main__":
    sys.exit(main())
