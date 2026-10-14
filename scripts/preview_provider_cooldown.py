"""Fail-closed preflight for a known Vercel deployment rate-limit observation.

Reads only open GitHub PR commit statuses; no Vercel API key, billing or mutations.
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
MAX_OPEN_PRS = 50
WINDOW = timedelta(hours=24)


def _get_json(method: str, url: str, headers: dict[str, str]):
    req = request.Request(url, headers=headers, method=method)
    with request.urlopen(req, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


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
    pulls = get_json("GET", f"{root}/pulls?state=open&per_page=100", headers)
    if not isinstance(pulls, list) or len(pulls) > MAX_OPEN_PRS:
        raise RuntimeError("open PR inventory is incomplete or too large to verify safely")
    seen = set()
    for pull in pulls:
        if not isinstance(pull, dict):
            raise RuntimeError("invalid PR inventory item")
        sha = (pull.get("head") or {}).get("sha")
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise RuntimeError("invalid open PR candidate SHA")
        if sha in seen:
            continue
        seen.add(sha)
        response = get_json("GET", f"{root}/commits/{sha}/status", headers)
        statuses = response.get("statuses") if isinstance(response, dict) else None
        if not isinstance(statuses, list):
            raise RuntimeError("missing GitHub commit statuses")
        for item in statuses:
            if not isinstance(item, dict) or item.get("context") != "Vercel":
                continue
            if item.get("state") != "failure":
                continue
            description = str(item.get("description") or "").casefold()
            if "deployment rate limited" not in description:
                continue
            stamp = item.get("updated_at") or item.get("created_at")
            if not isinstance(stamp, str):
                raise RuntimeError("Vercel rate-limit status has no timestamp")
            recorded = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if recorded.tzinfo is None:
                raise RuntimeError("Vercel rate-limit timestamp lacks timezone")
            recorded = recorded.astimezone(timezone.utc)
            if recorded > now_utc + timedelta(minutes=5):
                raise RuntimeError("Vercel status timestamp exceeds clock tolerance")
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
        "authoritative_quota": False, "checked_prs": len(pulls),
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
