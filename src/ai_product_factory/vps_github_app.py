"""Short-lived GitHub App installation credentials for native IBM VPS Direct.

The VPS already holds a privileged Supabase Secret Key. Use the EXISTING
service-role-only credential RPC to mint a GitHub installation token in memory,
scoped to the exact active project repository and verified write permissions.
Never store the GitHub App private key, installation token, or a persistent PAT.
The child process passes the token to the Python runtime only over an inherited
anonymous pipe (never stdout, argv, logs, disk, or model prompts).
GitHub Actions OIDC credential acquisition is unchanged.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from typing import Callable
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parents[2]
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_REQUIRED = ("contents_write", "issues_write", "pull_requests_write")
_SCOPED = {"contents": "write", "issues": "write", "pull_requests": "write",
           "actions": "read", "checks": "read", "statuses": "read"}


class VpsGitHubAppUnavailable(PermissionError):
    """All failures are sanitized; credentials and response bodies are hidden."""


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _transport(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, object]:
    if not url.startswith("https://"):
        raise VpsGitHubAppUnavailable("HTTPS required")
    opener = request.build_opener(request.ProxyHandler({}), _NoRedirect)
    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with opener.open(req, timeout=25) as response:
            raw = response.read(200001)
            if len(raw) > 200000:
                raise VpsGitHubAppUnavailable("bounded response exceeded")
            return response.status, json.loads(raw) if raw else None
    except VpsGitHubAppUnavailable:
        raise
    except error.HTTPError:
        raise VpsGitHubAppUnavailable("upstream authorization unavailable") from None
    except Exception:
        raise VpsGitHubAppUnavailable("upstream connection unavailable") from None


def _source_sha():
    try:
        return subprocess.check_output(
            ["/usr/bin/git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True, timeout=8, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        raise VpsGitHubAppUnavailable("source SHA unavailable") from None


def _sign_app_jwt(app_id: int, private_pem: str) -> str:
    # The root-provisioned Ubuntu system Python has python3-cryptography.
    # The Factory .venv need not install an extra unpinned native dependency.
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    def b64(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    now = int(time.time())
    header = b64(b'{"alg":"RS256","typ":"JWT"}')
    claims = b64(json.dumps({
        "iat": now - 60, "exp": now + 480, "iss": str(app_id),
    }, separators=(",", ":")).encode("ascii"))
    content = (header + "." + claims).encode("ascii")
    key = serialization.load_pem_private_key(private_pem.encode("ascii"), password=None)
    signature = key.sign(content, padding.PKCS1v15(), hashes.SHA256())
    return content.decode("ascii") + "." + b64(signature)


def issue_for_repository(
    repository: str, project_key: str,
    *,
    env: dict | None = None,
    transport: Callable = _transport,
    signer: Callable = _sign_app_jwt,
    checkout: Callable = _source_sha,
) -> str:
    env = dict(os.environ if env is None else env)
    if not _REPO.fullmatch(repository) or not _KEY.fullmatch(project_key):
        raise VpsGitHubAppUnavailable("invalid binding")
    if (env.get("GITHUB_ACTIONS", "").strip().lower() == "true"
        or env.get("FACTORY_PRIMARY_MODEL_PROVIDER") != "infodive_ibm_cloud"
        or env.get("FACTORY_PRIMARY_MODEL_ENABLED") != "true"
        or env.get("FACTORY_INFODIVE_VPS_WORKER_ENABLED") != "true"
        or env.get("FACTORY_SQL_INFODIVE_PRIVATE_ROUTE_ATTESTED") != "true"):
        raise VpsGitHubAppUnavailable("native Direct not authorized")
    worker_sha = env.get("FACTORY_SQL_INFODIVE_WORKER_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", worker_sha) or checkout() != worker_sha:
        raise VpsGitHubAppUnavailable("untrusted worker revision")
    service_url = str(env.get("SUPABASE_URL") or "").rstrip("/")
    parsed = parse.urlsplit(service_url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
        or parsed.password or parsed.query or parsed.fragment or parsed.path
        or parsed.port not in (None, 443)):
        raise VpsGitHubAppUnavailable("control plane origin invalid")
    secret = env.get("SUPABASE_SECRET_KEY") or ""
    if not secret.startswith("sb_secret_"):
        raise VpsGitHubAppUnavailable("privileged key unavailable")
    supabase_headers = {"apikey": secret, "Accept": "application/json"}
    def control(path: str, body: bytes | None = None):
        headers = {**supabase_headers}
        if body is not None:
            headers["Content-Type"] = "application/json"
        status, value = transport(
            "POST" if body is not None else "GET",
            service_url + "/rest/v1/" + path, headers, body,
        )
        if status != 200:
            raise VpsGitHubAppUnavailable("control plane refused")
        return value

    project_rows = control(
        "factory_projects?select=id,project_key,repository,is_active"
        "&project_key=eq." + parse.quote(project_key, safe="")
        + "&is_active=eq.true&limit=1",
    )
    if (not isinstance(project_rows, list) or len(project_rows) != 1
        or project_rows[0].get("repository", "").lower() != repository.lower()
        or project_rows[0].get("project_key") != project_key):
        raise VpsGitHubAppUnavailable("project binding unavailable")
    project_id = project_rows[0].get("id")
    if not isinstance(project_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", project_id):
        raise VpsGitHubAppUnavailable("project ID invalid")
    access_rows = control(
        "factory_project_github_access?"
        "select=auth_mode,status,installation_id,repository_id,observed_capabilities"
        "&project_id=eq." + parse.quote(project_id, safe="") + "&limit=1",
    )
    if not isinstance(access_rows, list) or len(access_rows) != 1:
        raise VpsGitHubAppUnavailable("repository access not configured")
    access = access_rows[0]
    rights = access.get("observed_capabilities") or {}
    if (access.get("auth_mode") != "github_app" or access.get("status") != "ready"
        or not isinstance(rights, dict)
        or any(rights.get(key) != "verified" for key in _REQUIRED)):
        raise VpsGitHubAppUnavailable("project access not verified")
    installation_id = access.get("installation_id")
    expected_repo_id = access.get("repository_id")
    if (type(installation_id) is not int or installation_id <= 0
        or type(expected_repo_id) is not int or expected_repo_id <= 0):
        raise VpsGitHubAppUnavailable("installation identity unavailable")

    # The existing RPC is SECURITY INVOKER and service_role-only. Do not
    # retrieve this private key through the model, generated code or browser.
    credential = control("rpc/factory_get_github_app_credentials", b"{}")
    if not isinstance(credential, dict):
        raise VpsGitHubAppUnavailable("GitHub App credential unavailable")
    app_id, pem = credential.get("app_id"), credential.get("private_key")
    if not str(app_id).isdigit() or int(app_id) <= 0 or not isinstance(pem, str):
        raise VpsGitHubAppUnavailable("GitHub App credential invalid")
    try:
        app_jwt = signer(int(app_id), pem)
    except Exception:
        raise VpsGitHubAppUnavailable("GitHub App signing failed") from None
    if not isinstance(app_jwt, str) or not app_jwt:
        raise VpsGitHubAppUnavailable("GitHub App signature missing")
    def github(method: str, path: str, token: str, body: bytes | None = None):
        headers = {"Accept": "application/vnd.github+json",
                   "Authorization": "Bearer " + token,
                   "X-GitHub-Api-Version": "2022-11-28"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        status, value = transport(method, "https://api.github.com" + path, headers, body)
        if not 200 <= status < 300:
            raise VpsGitHubAppUnavailable("GitHub refused installation token")
        return status, value

    request_body = json.dumps({
        "repositories": [repository.split("/")[1]],
        "permissions": dict(_SCOPED),
    }, separators=(",", ":")).encode("utf-8")
    status, issued = github(
        "POST", f"/app/installations/{installation_id}/access_tokens",
        app_jwt, request_body,
    )
    if status != 201 or not isinstance(issued, dict):
        raise VpsGitHubAppUnavailable("GitHub App token mint failed")
    token = issued.get("token")
    if (not isinstance(token, str) or not 24 <= len(token) <= 8192
        or any(ord(c) < 33 or ord(c) > 126 for c in token)):
        raise VpsGitHubAppUnavailable("invalid token response")
    permissions = issued.get("permissions") or {}
    if (not isinstance(permissions, dict)
        or any(permissions.get(key) != value for key, value in _SCOPED.items())):
        raise VpsGitHubAppUnavailable("write scope unverified")
    expiry = issued.get("expires_at")
    try:
        expiration = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        ttl = (expiration - datetime.now(timezone.utc)).total_seconds()
    except Exception:
        raise VpsGitHubAppUnavailable("token expiry invalid") from None
    if not 300 <= ttl <= 3700:
        raise VpsGitHubAppUnavailable("short-lived token not valid")

    # Installation metadata must identify one and ONLY one repository.
    reported = issued.get("repositories")
    if reported is not None:
        if (not isinstance(reported, list) or len(reported) != 1
            or reported[0].get("id") != expected_repo_id
            or str(reported[0].get("full_name", "")).lower() != repository.lower()):
            raise VpsGitHubAppUnavailable("issued repository scope mismatch")
    _, listing = github("GET", "/installation/repositories", token)
    if (not isinstance(listing, dict) or listing.get("total_count") != 1
        or not isinstance(listing.get("repositories"), list)
        or len(listing["repositories"]) != 1
        or listing["repositories"][0].get("id") != expected_repo_id
        or str(listing["repositories"][0].get("full_name", "")).lower() != repository.lower()):
        raise VpsGitHubAppUnavailable("installation scope mismatch")
    _, actual = github("GET", "/repos/" + repository, token)
    if (not isinstance(actual, dict) or actual.get("id") != expected_repo_id
        or str(actual.get("full_name", "")).lower() != repository.lower()):
        raise VpsGitHubAppUnavailable("authenticated repository identity mismatch")
    # GitHub App installation tokens with contents:write can legitimately have
    # permissions.push=false on GET /repos; permissions of the ISSUED token,
    # exclusive installation repo scope and authenticated repo ID were verified.
    # A reversible branch create+delete was independently observed on CRM.
    return token


def mint_vps_github_app_token(repository: str, project_key: str) -> str:
    """Return the verified ephemeral token through an isolated pipe, never env."""
    if not _REPO.fullmatch(repository) or not _KEY.fullmatch(project_key):
        raise VpsGitHubAppUnavailable("invalid repository binding")
    keys = (
        "SUPABASE_URL", "SUPABASE_SECRET_KEY",
        "FACTORY_PRIMARY_MODEL_PROVIDER", "FACTORY_PRIMARY_MODEL_ENABLED",
        "FACTORY_INFODIVE_VPS_WORKER_ENABLED",
        "FACTORY_SQL_INFODIVE_PRIVATE_ROUTE_ATTESTED",
        "FACTORY_SQL_INFODIVE_WORKER_SHA",
    )
    child_env = {key: os.environ.get(key, "") for key in keys}
    child_env["GITHUB_ACTIONS"] = "false"
    child_env["PYTHONPATH"] = str(ROOT / "src")
    child_env["PATH"] = "/usr/bin:/bin"
    child_env["PYTHONDONTWRITEBYTECODE"] = "1"
    read_fd, write_fd = os.pipe()
    process = None
    try:
        child_env["FACTORY_GITHUB_JIT_PIPE_FD"] = str(write_fd)
        process = subprocess.Popen(
            ["/usr/bin/python3", "-m", "ai_product_factory.vps_github_app",
             "--repository", repository, "--project-key", project_key],
            cwd=str(ROOT), env=child_env, pass_fds=(write_fd,),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        os.close(write_fd)
        write_fd = -1
        try:
            code = process.wait(timeout=85)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
            raise VpsGitHubAppUnavailable("GitHub App token timeout") from None
        if code != 0:
            raise VpsGitHubAppUnavailable("GitHub App credential not ready")
        raw = os.read(read_fd, 8193)
        if len(raw) > 8192:
            raise VpsGitHubAppUnavailable("unexpected credential size")
        token = raw.decode("ascii")
        if (not 24 <= len(token) <= 8192
            or any(ord(char) < 33 or ord(char) > 126 for char in token)):
            raise VpsGitHubAppUnavailable("invalid token pipe response")
        return token
    except VpsGitHubAppUnavailable:
        raise
    except Exception:
        raise VpsGitHubAppUnavailable("GitHub App credential unavailable") from None
    finally:
        os.close(read_fd)
        if write_fd >= 0:
            os.close(write_fd)
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--project-key", required=True)
    args = parser.parse_args(argv)
    fd_raw = os.environ.get("FACTORY_GITHUB_JIT_PIPE_FD", "")
    try:
        fd = int(fd_raw)
        if fd < 3 or not stat.S_ISFIFO(os.fstat(fd).st_mode):
            return 3
        token = issue_for_repository(args.repository, args.project_key)
        os.write(fd, token.encode("ascii"))
        return 0
    except Exception:
        # Never write a credential, upstream body or traceback to stdout/stderr.
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
