"""Credentialless Vercel Preview backend probe, with no redirect or body capture.

A successful JSON session response is only an environment-readiness signal.
It is NEVER browser evidence and it never authorizes release or production.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
import urllib.error
import urllib.parse
import urllib.request


class PreviewEnvironmentNotReady(RuntimeError):
    pass


def preview_origin(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise PreviewEnvironmentNotReady("invalid_preview_origin")
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError as exc:
        raise PreviewEnvironmentNotReady("invalid_preview_origin") from exc
    hostname = parsed.hostname or ""
    if (parsed.scheme != "https" or not re.fullmatch(
        r"[a-z0-9][a-z0-9-]*[.]vercel[.]app", hostname)
        or parsed.netloc != hostname or parsed.path not in ("", "/")
        or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise PreviewEnvironmentNotReady("untrusted_preview_origin")
    return "https://" + hostname


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Reject a Location before urllib can contact an untrusted destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe_session(url: str) -> dict:
    """Unauthenticated GET /api/session. No redirects, cookies, body or secret.

    A 200/401 JSON response only lifts the temporary environmental wait;
    the exact-SHA browser E2E must still pass in the normal delivery flow.
    """
    origin = preview_origin(url)
    endpoint = origin + "/api/session"
    request = urllib.request.Request(
        endpoint,
        headers={"Accept": "application/json", "User-Agent": "Factory-Preview-Readiness/1"},
        method="GET",
    )
    try:
        try:
            with urllib.request.build_opener(_NoRedirect).open(request, timeout=12) as response:
                status = response.status
                content_type = response.headers.get("Content-Type", "").lower().strip()
                returned_url = response.geturl()
        except urllib.error.HTTPError as exc:
            status = exc.code
            content_type = exc.headers.get("Content-Type", "").lower().strip()
            returned_url = exc.geturl()
            exc.close()
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise PreviewEnvironmentNotReady("preview_session_unreachable") from exc
    if returned_url != endpoint or 300 <= status < 400:
        raise PreviewEnvironmentNotReady("preview_session_redirected")
    if status not in (200, 401) or not re.fullmatch(r"application/json(?:;.*)?", content_type):
        raise PreviewEnvironmentNotReady("preview_backend_still_unverified")
    return {
        "kind": "unauthenticated_json_session_probe",
        "url": endpoint,
        "http_status": str(status),
        "content_type": content_type,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def is_session_backend_503(detail: object) -> bool:
    """Recognize only the recorded browser failure, never general 503/log text."""
    return isinstance(detail, str) and "http_503: fetch /api/session" in detail
