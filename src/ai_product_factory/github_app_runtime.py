from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable
from urllib import error, parse, request

from .supabase_server import resolve_supabase_server_config


GITHUB_API_VERSION = "2026-03-10"
APP_PERMISSIONS = {
    "actions": "read",
    "checks": "read",
    "contents": "write",
    "issues": "write",
    "pull_requests": "write",
    "statuses": "read",
}

JsonTransport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, Any]]
Signer = Callable[[bytes, str], bytes]


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _default_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, Any]:
    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload: Any = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = None
        return exc.code, payload


def _openssl_sign(payload: bytes, private_key: str) -> bytes:
    key_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            key_path = handle.name
            os.chmod(key_path, 0o600)
            handle.write(private_key)
        completed = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", key_path],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return completed.stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("GitHub App JWT signing failed") from exc
    finally:
        if key_path:
            Path(key_path).unlink(missing_ok=True)


def create_app_jwt(app_id: int, private_key: str, *, now: int | None = None, signer: Signer = _openssl_sign) -> str:
    if app_id <= 0 or not private_key.strip():
        raise ValueError("GitHub App credentials are incomplete")
    issued_at = int(time.time() if now is None else now)
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(
        json.dumps(
            {"iat": issued_at - 60, "exp": issued_at + 9 * 60, "iss": str(app_id)},
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = _b64url(signer(signing_input, private_key))
    return signing_input.decode("ascii") + "." + signature


def _control_plane_available() -> bool:
    return bool(
        os.getenv("SUPABASE_URL", "").strip()
        and (
            os.getenv("SUPABASE_SECRET_KEY", "").strip()
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        )
    )


def _request_json(
    method: str,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any] | None,
    *,
    transport: JsonTransport,
) -> Any:
    status, payload = transport(
        method,
        url,
        headers,
        None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8"),
    )
    if status < 200 or status >= 300:
        raise RuntimeError(f"GitHub App runtime request failed with HTTP {status}")
    return payload


def resolve_github_app_installation_token(
    repository: str,
    *,
    transport: JsonTransport = _default_transport,
    signer: Signer = _openssl_sign,
    now: int | None = None,
) -> str | None:
    if "/" not in repository or repository.count("/") != 1:
        raise ValueError("repository must be in owner/name form")
    if not _control_plane_available():
        return None

    cfg = resolve_supabase_server_config()
    encoded_repository = parse.quote(repository, safe="")
    projects = _request_json(
        "GET",
        f"{cfg.url}/rest/v1/factory_projects?select=id,repository&repository=eq.{encoded_repository}&is_active=eq.true&limit=1",
        cfg.headers,
        None,
        transport=transport,
    )
    if not isinstance(projects, list) or not projects:
        return None

    project_id = str(projects[0].get("id") or "")
    access = _request_json(
        "GET",
        f"{cfg.url}/rest/v1/factory_project_github_access?select=auth_mode,status,installation_id,repository_id&project_id=eq.{parse.quote(project_id, safe='')}&limit=1",
        cfg.headers,
        None,
        transport=transport,
    )
    if not isinstance(access, list) or not access:
        return None

    row = access[0]
    auth_mode = str(row.get("auth_mode") or "")
    if auth_mode != "github_app":
        return None
    if str(row.get("status") or "") != "ready":
        raise PermissionError("GitHub App access is not ready for this repository")

    installation_id = int(row.get("installation_id") or 0)
    repository_id = int(row.get("repository_id") or 0)
    if installation_id <= 0 or repository_id <= 0:
        raise PermissionError("GitHub App verified installation metadata is incomplete")

    app = _request_json(
        "POST",
        f"{cfg.url}/rest/v1/rpc/factory_get_github_app_credentials",
        {**cfg.headers, "Content-Type": "application/json"},
        {},
        transport=transport,
    )
    if not isinstance(app, dict):
        raise RuntimeError("Factory GitHub App is not configured")
    app_id = int(app.get("app_id") or 0)
    private_key = str(app.get("private_key") or "")
    if app_id <= 0 or not private_key:
        raise RuntimeError("Factory GitHub App credentials are incomplete")

    app_jwt = create_app_jwt(app_id, private_key, now=now, signer=signer)
    token_response = _request_json(
        "POST",
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {app_jwt}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        },
        {
            "repository_ids": [repository_id],
            "permissions": APP_PERMISSIONS,
        },
        transport=transport,
    )
    token = str((token_response or {}).get("token") or "")
    if not token:
        raise RuntimeError("GitHub installation token was not issued")
    return token
