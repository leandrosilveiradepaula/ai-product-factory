"""Fail-closed read-only evidence check for an already-promoted exact Preview ref.

A Git ref pointing at a PR head is NOT evidence of a Vercel deployment.
This guard is used only after the trusted workflow has rechecked the exact
open PR/head, green CI, and existing preview/pr-N ref. It never creates,
deletes, or force-updates refs, calls models, or deploys to Vercel.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from scripts.preview_provider_cooldown import (
    JSONRequest, REPO, SHA, _get_json, _is_confirmed_deployment,
    _parse_timestamp,
)


def inspect_reused_preview(
    *, token: str, repository: str, sha: str,
    now: datetime | None = None, get_json: JSONRequest = _get_json,
) -> dict[str, Any]:
    if not token or not REPO.fullmatch(repository) or not SHA.fullmatch(sha):
        raise RuntimeError("exact Preview reuse requires GITHUB_TOKEN, repository and 40-character SHA")
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("now must have a timezone")
    instant = instant.astimezone(timezone.utc)
    root = f"https://api.github.com/repos/{repository}"
    response = get_json(
        "GET", f"{root}/commits/{sha}/status",
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    statuses = response.get("statuses") if isinstance(response, dict) else None
    if not isinstance(statuses, list) or len(statuses) > 100:
        raise RuntimeError("GitHub commit status inventory missing or incomplete")

    vercel: list[tuple[datetime, dict[str, Any]]] = []
    for item in statuses:
        if not isinstance(item, dict):
            raise RuntimeError("malformed GitHub commit status")
        if item.get("context") != "Vercel":
            continue
        raw = item.get("updated_at") or item.get("created_at")
        if not isinstance(raw, str):
            raise RuntimeError("Vercel status missing timestamp")
        stamp = _parse_timestamp(raw)
        if stamp > instant + timedelta(minutes=5):
            raise RuntimeError("Vercel status timestamp exceeds clock tolerance")
        vercel.append((stamp, item))

    base = {
        "source": "github_vercel_commit_status",
        "candidate_sha": sha,
        "authoritative_quota": False,
    }
    if not vercel:
        return {**base, "allowed": False, "state": "no_vercel_deployment_evidence"}

    latest_stamp = max(event[0] for event in vercel)
    latest = [event[1] for event in vercel if event[0] == latest_stamp]
    evidence = {"observed_at": latest_stamp.isoformat()}
    # If provider statuses conflict at the same instant, do not choose a
    # favorable one merely because it was returned first.
    if len(latest) != 1:
        return {**base, **evidence, "allowed": False, "state": "ambiguous_vercel_status"}

    status = latest[0]
    if status.get("state") == "failure" and "deployment rate limited" in str(
        status.get("description") or ""
    ).casefold():
        return {**base, **evidence, "allowed": False, "state": "provider_rate_limited"}

    if _is_confirmed_deployment(status):
        return {
            **base, **evidence, "allowed": True,
            "state": "confirmed_deployment_on_exact_sha",
            # Still requires Vercel checks, exact URL, and trusted browser
            # evidence in the subsequent workflow step.
        }

    return {**base, **evidence, "allowed": False, "state": "vercel_not_ready"}


def main() -> int:
    result = inspect_reused_preview(
        token=os.environ.get("GITHUB_TOKEN", ""),
        repository=os.environ.get("GITHUB_REPOSITORY", ""),
        sha=os.environ.get("CANDIDATE_SHA", ""),
    )
    print(json.dumps(result, sort_keys=True))
    if not result["allowed"]:
        print(
            "::error::Existing exact Preview ref is not a READY deployment. "
            "Do not redispatch browser checks or claim Preview verified. "
            "A subsequent provider-authorized redeployment at this same SHA "
            "must be observed before reuse can continue.",
            file=sys.stderr,
        )
    return 0 if result["allowed"] else 2


if __name__ == "__main__":
    sys.exit(main())
