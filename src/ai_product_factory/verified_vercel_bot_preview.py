"""Exact-SHA Vercel Git Preview fallback, requiring two provider-owned witnesses.

Only a successful Vercel commit status for the exact GitHub commit and an
authenticated Vercel GitHub App comment on that same open PR can supply a
Preview hostname. Vercel READY is not browser evidence or product readiness.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_SHA = re.compile(r"[a-f0-9]{40}\Z")
_INSPECTOR = re.compile(
    r"https://vercel\.com/(?P<team>[a-z0-9-]+)/(?P<project>[a-z0-9-]+)/"
    r"(?P<deployment>[A-Za-z0-9]{20,40})\Z"
)
_PREVIEW = re.compile(r"\[Preview\]\((https://[a-z0-9][a-z0-9-]*\.vercel\.app)\)")


class VercelPreviewWitnessBlocked(ValueError):
    """Provider identity or candidate lineage cannot be verified."""


def _require(ok: object, reason: str) -> None:
    if ok is not True:
        raise VercelPreviewWitnessBlocked(reason)


def resolve_verified_vercel_bot_preview(*, repository: str, candidate_sha: str,
                                        pulls: object, statuses: object,
                                        comments: object) -> str | None:
    _require(isinstance(repository, str) and _REPO.fullmatch(repository) is not None
             and isinstance(candidate_sha, str) and _SHA.fullmatch(candidate_sha) is not None,
             "invalid_exact_candidate")
    _require(isinstance(pulls, list) and len(pulls) == 1
             and isinstance(pulls[0], dict),
             "candidate_pr_missing_or_ambiguous")
    pull = pulls[0]
    head = pull.get("head") or {}
    base = pull.get("base") or {}
    number = pull.get("number")
    _require(type(number) is int and number > 0 and pull.get("state") == "open"
             and pull.get("draft") is False and pull.get("merged_at") is None
             and isinstance(head, dict) and head.get("sha") == candidate_sha
             and (head.get("repo") or {}).get("full_name") == repository
             and isinstance(head.get("ref"), str)
             and head["ref"].startswith("factory/change-set-")
             and isinstance(base, dict) and base.get("ref") == "main",
             "candidate_pr_head_or_branch_changed")
    _require(isinstance(statuses, list) and len(statuses) <= 100
             and all(isinstance(x, dict) for x in statuses)
             and isinstance(comments, list) and len(comments) <= 100
             and all(isinstance(x, dict) for x in comments),
             "provider_evidence_unbounded")
    vercel = [s for s in statuses if s.get("context") == "Vercel"]
    if not vercel:
        return None
    # GitHub's combined status API returns newest records first. An older
    # SUCCESS must not override a newer failure/pending state.
    latest = vercel[0]
    if latest.get("state") in ("error", "failure"):
        raise VercelPreviewWitnessBlocked("latest_vercel_status_failed")
    if latest.get("state") != "success":
        return None
    inspector = latest.get("target_url")
    match = _INSPECTOR.fullmatch(inspector) if isinstance(inspector, str) else None
    _require(match is not None, "provider_deployment_target_unverified")
    team, project = match.group("team"), match.group("project")
    found: set[str] = set()
    for comment in comments:
        actor = comment.get("user") or {}
        app = comment.get("performed_via_github_app") or {}
        if (not isinstance(actor, dict) or actor.get("login") != "vercel[bot]"
                or not isinstance(app, dict) or app.get("slug") != "vercel"):
            continue
        body = comment.get("body")
        _require(isinstance(body, str) and len(body) <= 10000,
                 "vercel_bot_comment_invalid")
        for line in body.splitlines():
            if "[Ready](" + inspector + ")" not in line or "![Ready](" not in line:
                continue
            urls = _PREVIEW.findall(line)
            _require(len(urls) == 1, "vercel_bot_preview_link_ambiguous")
            parsed = urlsplit(urls[0])
            host = parsed.hostname or ""
            _require(parsed.scheme == "https" and parsed.netloc == host
                     and parsed.path == "" and not parsed.query and not parsed.fragment
                     and host.startswith(project + "-")
                     and host.endswith("-" + team + ".vercel.app"),
                     "vercel_bot_preview_origin_not_project_owned")
            found.add(urls[0])
    if not found:
        # GitHub commit status may precede the bot's update of its PR comment.
        return None
    _require(len(found) == 1, "vercel_bot_preview_conflicting_witnesses")
    return next(iter(found))
