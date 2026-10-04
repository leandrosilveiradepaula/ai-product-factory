from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib import error, parse, request

from .supabase_server import resolve_supabase_server_config


JsonTransport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, Any]]


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
    allowed_statuses: tuple[int, ...] = (),
) -> tuple[int, Any]:
    status, payload = transport(
        method,
        url,
        headers,
        None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8"),
    )
    if status < 200 or status >= 300:
        if status in allowed_statuses:
            return status, payload
        raise RuntimeError(f"GitHub App runtime request failed with HTTP {status}")
    return status, payload


def _is_runtime_control_plane_broker(url: str) -> bool:
    path = parse.urlparse(url).path.rstrip("/")
    return path.endswith("/functions/v1/factory-runtime-control-plane")


def _token_from_broker_response(
    *,
    status: int,
    token_response: Any,
    expected_installation_id: int | None = None,
    expected_repository_id: int | None = None,
) -> str | None:
    if status == 404:
        return None
    if status == 409:
        code = str((token_response or {}).get("error") or "github_app_not_ready")
        if code == "github_app_not_migrated":
            return None
        raise PermissionError("GitHub App token broker refused this repository: " + code)

    token = str((token_response or {}).get("token") or "")
    if not token:
        raise RuntimeError("GitHub installation token was not issued")

    installation_id = int((token_response or {}).get("installation_id") or 0)
    repository_id = int((token_response or {}).get("repository_id") or 0)
    if installation_id <= 0 or repository_id <= 0:
        raise PermissionError("GitHub App token broker returned incomplete repository binding")
    if expected_installation_id is not None and installation_id != expected_installation_id:
        raise PermissionError("GitHub installation token broker returned a different installation")
    if expected_repository_id is not None and repository_id != expected_repository_id:
        raise PermissionError("GitHub installation token broker returned a different repository")
    if (token_response or {}).get("token_persisted") is not False:
        raise PermissionError("GitHub installation token persistence contract was not proven")
    return token


def resolve_github_app_installation_token(
    repository: str,
    *,
    transport: JsonTransport = _default_transport,
) -> str | None:
    if "/" not in repository or repository.count("/") != 1:
        raise ValueError("repository must be in owner/name form")
    if not _control_plane_available():
        return None

    cfg = resolve_supabase_server_config()

    # GitHub Actions uses the OIDC Control Plane broker as SUPABASE_URL.
    # In that mode, call only the narrowly authorized GitHub App token endpoint.
    # The broker itself performs the privileged project/access lookups and revalidates
    # installation_id, repository_id and exact owner/name binding before returning.
    if _is_runtime_control_plane_broker(cfg.url):
        status, token_response = _request_json(
            "POST",
            cfg.url.rstrip("/") + "/github-app/token",
            {**cfg.headers, "Content-Type": "application/json"},
            {"repository": repository},
            transport=transport,
            allowed_statuses=(404, 409),
        )
        return _token_from_broker_response(status=status, token_response=token_response)

    encoded_repository = parse.quote(repository, safe="")
    _, projects = _request_json(
        "GET",
        f"{cfg.url}/rest/v1/factory_projects?select=id,repository&repository=eq.{encoded_repository}&is_active=eq.true&limit=1",
        cfg.headers,
        None,
        transport=transport,
    )
    if not isinstance(projects, list) or not projects:
        return None

    project_id = str(projects[0].get("id") or "")
    _, access = _request_json(
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

    status, token_response = _request_json(
        "POST",
        cfg.url.rstrip("/") + "/github-app/token",
        {**cfg.headers, "Content-Type": "application/json"},
        {"repository": repository},
        transport=transport,
        allowed_statuses=(409,),
    )
    return _token_from_broker_response(
        status=status,
        token_response=token_response,
        expected_installation_id=installation_id,
        expected_repository_id=repository_id,
    )
