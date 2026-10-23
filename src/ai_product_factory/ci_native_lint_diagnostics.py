"""Bounded, structured native lint diagnostics from verified GitHub Actions logs.

Never return raw logs, rule messages, headers or redirect locations to a model
or the Control Plane. Job/run/attempt/SHA identity is established by the caller
from the exact native Actions job inventory before this reader is invoked.
"""
from __future__ import annotations

import re
from urllib import error, request
from urllib.parse import urlsplit

_MAX_LOG_BYTES = 1024 * 1024
_MAX_LINES = 20
_MAX_SUMMARY = 1600
_LINT_LINE = re.compile(
    r"\bLINT_CHANGED_ERROR\s+"
    r"(?P<path>(?:src|app|apps|packages|test|tests|scripts|docs)/"
    r"[A-Za-z0-9_.()/\[\]-]+):"
    r"(?P<line>[1-9][0-9]{0,5}):"
    r"(?P<column>[1-9][0-9]{0,5})\s+"
    r"(?P<rule>@?[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)?)"
    r"(?=\s|$)"
)


def summarize_native_lint_errors(log: str) -> str | None:
    """Return only allowlisted path:line:column and rule identifiers."""
    if not isinstance(log, str) or len(log.encode("utf-8")) > _MAX_LOG_BYTES:
        return None
    entries: list[str] = []
    for match in _LINT_LINE.finditer(log):
        path = match.group("path")
        if any(segment in (".", "..") or segment.startswith(".") for segment in path.split("/")):
            continue
        entry = f"{path}:{match.group('line')}:{match.group('column')} {match.group('rule')}"
        if entry not in entries:
            entries.append(entry)
        if len(entries) > _MAX_LINES:
            return None
    if not entries:
        return None
    value = "Verified LINT_CHANGED_ERROR identifiers only: " + "; ".join(entries)
    return value if len(value) <= _MAX_SUMMARY else None


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a GitHub bearer token to a signed log-storage URL.
        return None


def _trusted_log_host(uri: str) -> bool:
    try:
        parsed = urlsplit(uri)
        host = (parsed.hostname or "").lower()
        return bool(
            parsed.scheme == "https"
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
            and (
                host.endswith(".blob.core.windows.net")
                or host.endswith(".githubusercontent.com")
            )
        )
    except ValueError:
        return False


def download_native_job_log(
    *, api_url: str, repository: str, job_id: int, token: str
) -> str:
    """Read one log with a trusted redirect and a hard byte cap.

    The opaque signed URL is never passed to a model, a persistence API or an
    exception. The second HTTPS request intentionally carries no Authorization.
    """
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        or type(job_id) is not int or job_id < 1
        or not token or api_url.rstrip("/") != "https://api.github.com"
    ):
        raise ValueError("invalid native CI log identity")
    url = f"{api_url}/repos/{repository}/actions/jobs/{job_id}/logs"
    req = request.Request(
        url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }, method="GET",
    )
    opener = request.build_opener(_NoRedirect)
    location = None
    try:
        with opener.open(req, timeout=25) as response:
            if response.status != 200:
                raise RuntimeError("native CI log response status is invalid")
            data = response.read(_MAX_LOG_BYTES + 1)
    except error.HTTPError as exc:
        if exc.code not in (302, 303, 307, 308):
            raise RuntimeError("native CI log retrieval failed") from None
        location = exc.headers.get("Location", "")
        if not _trusted_log_host(location):
            raise RuntimeError("native CI log redirect host is not trusted") from None
        # Signed location is sensitive: no GitHub Authorization to this host.
        try:
            with request.urlopen(
                request.Request(location, headers={"Accept": "text/plain"}),
                timeout=25,
            ) as response:
                if response.status != 200:
                    raise RuntimeError("signed native CI log is unavailable")
                data = response.read(_MAX_LOG_BYTES + 1)
        except (error.HTTPError, error.URLError):
            raise RuntimeError("signed native CI log is unavailable") from None
    except error.URLError:
        raise RuntimeError("native CI log retrieval unavailable") from None
    if len(data) > _MAX_LOG_BYTES:
        raise RuntimeError("native CI job log exceeds bounded read limit")
    return data.decode("utf-8", errors="replace")
