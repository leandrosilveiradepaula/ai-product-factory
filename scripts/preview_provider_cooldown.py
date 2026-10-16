"""Fail-closed preflight for a known Vercel deployment rate-limit observation.

Reads open and recently closed GitHub PR head statuses AND recent merge commit statuses; no Vercel API key, billing or mutations.
Absence of a rate-limit signal is NOT evidence that provider quota is available.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib import request, parse

JSONRequest = Callable[[str, str, dict[str, str]], Any]
SHA = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")
MAX_RECENT_PRS = 500
MAX_PR_PAGES = 5
PR_PAGE_SIZE = 100
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


def _is_confirmed_deployment(item: dict[str, Any]) -> bool:
    """Do not confuse Vercel's success for an ignored build with READY.

    A successful commit status only supersedes a quota error when it is
    explicitly a completed deployment and points to a concrete Vercel
    deployment detail, not the team upgrade/cancelled-build page.
    This proves an actual later deployment, not guaranteed future quota.
    """
    if item.get("state") != "success":
        return False
    description = str(item.get("description") or "").strip().casefold()
    if description not in {"deployment has completed", "deployment ready"}:
        return False
    url = item.get("target_url")
    if not isinstance(url, str):
        return False
    parsed = parse.urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    return (
        parsed.scheme == "https" and parsed.hostname == "vercel.com"
        and parsed.username is None and parsed.password is None
        and parsed.port is None and not parsed.query and not parsed.fragment
        and len(parts) == 3
        and all(part not in (".", "..") for part in parts)
    )


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
    # Recently updated PRs are needed because a closed PR may still carry
    # the latest Vercel rate-limit observation. Separately enumerate every
    # open PR: an old open PR can have a recently updated provider status.
    # Use bounded pagination and fail closed on incomplete inventories.
    cutoff = now_utc - WINDOW

    def collect_pulls(state: str) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        previous: datetime | None = None
        for page in range(1, MAX_PR_PAGES + 1):
            pulls = get_json(
                "GET",
                f"{root}/pulls?state={state}&sort=updated&direction=desc"
                f"&per_page={PR_PAGE_SIZE}&page={page}",
                headers,
            )
            if not isinstance(pulls, list) or len(pulls) > PR_PAGE_SIZE:
                raise RuntimeError("recent PR inventory is incomplete or malformed")
            for pull in pulls:
                if not isinstance(pull, dict):
                    raise RuntimeError("invalid PR inventory item")
                pr_state = pull.get("state")
                if pr_state not in ("open", "closed") or (state == "open" and pr_state != "open"):
                    raise RuntimeError("invalid PR state")
                updated_raw = pull.get("updated_at")
                if not isinstance(updated_raw, str):
                    raise RuntimeError("PR inventory has missing update timestamp")
                updated_at = _parse_timestamp(updated_raw)
                if updated_at > now_utc + timedelta(minutes=5):
                    raise RuntimeError("PR inventory timestamp exceeds clock tolerance")
                if previous is not None and updated_at > previous:
                    raise RuntimeError("PR inventory lost descending order")
                previous = updated_at
                if state == "open" or updated_at >= cutoff:
                    selected.append(pull)
            # Sorted 'all' includes closed PRs. Once older than our window,
            # stop and rely on the independent open-only inventory.
            if len(pulls) < PR_PAGE_SIZE or (
                state == "all" and previous is not None and previous < cutoff
            ):
                return selected
        raise RuntimeError("recent PR inventory paginated beyond safe bound")

    # Both queries overlap. Distinguish distinct PRs (even when they share a
    # commit SHA), while counting the same PR just once across both queries.
    candidates_by_number: dict[int, dict[str, Any]] = {}
    for pull in collect_pulls("all") + collect_pulls("open"):
        number = pull.get("number")
        if type(number) is not int or number < 1:
            raise RuntimeError("PR inventory has invalid PR number")
        prior = candidates_by_number.get(number)
        if prior is not None:
            if (prior.get("state") != pull.get("state")
                or prior.get("updated_at") != pull.get("updated_at")
                or (prior.get("head") or {}).get("sha") != (pull.get("head") or {}).get("sha")):
                raise RuntimeError("PR inventory changed across pages/queries")
            continue
        candidates_by_number[number] = pull
        if len(candidates_by_number) > MAX_RECENT_PRS:
            raise RuntimeError("recent PR inventory exceeds safe bound")
    candidates = list(candidates_by_number.values())
    # A GitHub PR head is not necessarily the deployed production commit:
    # squash/merge commits on main carry their own Vercel status. Inspect
    # recent merged PR commits as well, or a fresh production rate limit is
    # invisible to a PR-head-only cooldown scan.
    candidate_shas: list[str] = []
    for pull in candidates:
        sha = (pull.get("head") or {}).get("sha")
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise RuntimeError("invalid open or recent PR candidate SHA")
        candidate_shas.append(sha)
        merged_raw = pull.get("merged_at")
        if merged_raw is None:
            continue
        if not isinstance(merged_raw, str):
            raise RuntimeError("invalid PR merge timestamp")
        merged_at = _parse_timestamp(merged_raw)
        if merged_at > now_utc + timedelta(minutes=5):
            raise RuntimeError("PR merge timestamp exceeds clock tolerance")
        if merged_at < cutoff:
            continue
        merge_sha = pull.get("merge_commit_sha")
        if not isinstance(merge_sha, str) or not SHA.fullmatch(merge_sha):
            raise RuntimeError("invalid merged PR commit SHA")
        candidate_shas.append(merge_sha)

    seen = set()
    rate_limit_events: list[tuple[datetime, str]] = []
    completed_deployments: list[tuple[datetime, str]] = []
    for sha in candidate_shas:
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
        # Read ALL recent commits before making the quota decision. An actual
        # deployment that completed after a rate limit may belong to another
        # PR head or squash merge SHA of the same GitHub repository.
        for recorded, item in vercel:
            description = str(item.get("description") or "").casefold()
            if item.get("state") == "failure" and "deployment rate limited" in description:
                if now_utc < recorded + WINDOW:
                    rate_limit_events.append((recorded, sha))
            elif _is_confirmed_deployment(item):
                completed_deployments.append((recorded, sha))

    if rate_limit_events:
        newest_failure, failed_sha = max(rate_limit_events, key=lambda event: event[0])
        newer_completed = [
            event for event in completed_deployments if event[0] > newest_failure
        ]
        if not newer_completed:
            return {
                "allowed": False, "state": "provider_rate_limited",
                "source": "github_vercel_commit_status",
                "observed_at": newest_failure.isoformat(),
                # Recheck is an upper-bound window, NOT the next mandatory poll.
                "earliest_recheck_at": (newest_failure + WINDOW).isoformat(),
                "sha": failed_sha,
            }
        verified_at, verified_sha = max(newer_completed, key=lambda event: event[0])
        return {
            "allowed": True, "state": "confirmed_deployment_after_rate_limit",
            "source": "github_vercel_commit_status",
            "authoritative_quota": False,
            "observed_at": verified_at.isoformat(),
            "verified_deployment_sha": verified_sha,
            "superseded_rate_limit_sha": failed_sha,
            "checked_prs": len(candidates),
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
