from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import tempfile
import time
from typing import Any, Callable
from urllib import parse, request


TokenFetcher = Callable[[str], str]


def decode_unverified_claims(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("OIDC token is not a JWT")
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        claims = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError("OIDC token payload cannot be decoded") from exc
    if not isinstance(claims, dict):
        raise ValueError("OIDC token payload must be an object")
    return claims


def validate_github_claims(
    claims: dict[str, Any],
    *,
    audience: str,
    repository: str,
    ref: str,
    environment: str,
    repository_owner_id: str | None = None,
    repository_id: str | None = None,
    now: float | None = None,
) -> None:
    if bool(repository_owner_id) != bool(repository_id):
        raise PermissionError("GitHub OIDC immutable subject configuration is incomplete")
    if repository_owner_id and repository_id:
        try:
            owner, repo_name = repository.split("/", 1)
        except ValueError as exc:
            raise PermissionError("GitHub repository name is invalid") from exc
        if not repository_owner_id.isdigit() or not repository_id.isdigit():
            raise PermissionError("GitHub OIDC immutable subject IDs must be numeric")
        expected_sub = (
            f"repo:{owner}@{repository_owner_id}/{repo_name}@{repository_id}"
            f":environment:{environment}"
        )
    else:
        expected_sub = f"repo:{repository}:environment:{environment}"
    expected = {
        "iss": "https://token.actions.githubusercontent.com",
        "sub": expected_sub,
        "repository": repository,
        "ref": ref,
        "environment": environment,
    }
    for key, value in expected.items():
        if claims.get(key) != value:
            raise PermissionError(f"GitHub OIDC claim mismatch: {key}")

    aud = claims.get("aud")
    if isinstance(aud, str):
        audiences = {aud}
    elif isinstance(aud, list) and all(isinstance(item, str) for item in aud):
        audiences = set(aud)
    else:
        raise PermissionError("GitHub OIDC claim mismatch: aud")
    if audience not in audiences:
        raise PermissionError("GitHub OIDC audience mismatch")

    current = time.time() if now is None else now
    exp = claims.get("exp")
    iat = claims.get("iat")
    if not isinstance(exp, (int, float)) or exp <= current + 30:
        raise PermissionError("GitHub OIDC token is expired or too close to expiry")
    if not isinstance(iat, (int, float)) or iat > current + 30:
        raise PermissionError("GitHub OIDC token has an invalid issued-at time")


def fetch_github_oidc_token(audience: str) -> str:
    request_url = os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL", "").strip()
    request_token = os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "").strip()
    if not request_url or not request_token:
        raise RuntimeError("GitHub Actions OIDC environment is unavailable")

    parts = parse.urlsplit(request_url)
    query = dict(parse.parse_qsl(parts.query, keep_blank_values=True))
    query["audience"] = audience
    url = parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, parse.urlencode(query), parts.fragment)
    )
    req = request.Request(
        url,
        headers={"Authorization": f"bearer {request_token}"},
        method="GET",
    )
    with request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    token = payload.get("value") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError("GitHub Actions OIDC response did not contain a token")
    return token


def write_token_atomically(path: pathlib.Path, token: str) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, temp_name = tempfile.mkstemp(prefix=".identity-token.", dir=path.parent)
    temp_path = pathlib.Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(token)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        os.chmod(path, 0o600)
    finally:
        temp_path.unlink(missing_ok=True)


def refresh_once(
    *,
    token_file: pathlib.Path,
    audience: str,
    repository: str,
    ref: str,
    environment: str,
    repository_owner_id: str | None = None,
    repository_id: str | None = None,
    fetcher: TokenFetcher = fetch_github_oidc_token,
) -> None:
    token = fetcher(audience)
    claims = decode_unverified_claims(token)
    validate_github_claims(
        claims,
        audience=audience,
        repository=repository,
        ref=ref,
        environment=environment,
        repository_owner_id=repository_owner_id,
        repository_id=repository_id,
    )
    write_token_atomically(token_file, token)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-seconds", type=int, default=0)
    args = parser.parse_args(argv)
    if args.refresh_seconds < 0:
        raise ValueError("refresh interval cannot be negative")

    token_file = pathlib.Path(_required_env("OPENAI_IDENTITY_TOKEN_FILE"))
    if not token_file.is_absolute():
        raise RuntimeError("OPENAI_IDENTITY_TOKEN_FILE must be absolute")
    audience = _required_env("OPENAI_WIF_AUDIENCE")
    repository = _required_env("GITHUB_REPOSITORY")
    ref = _required_env("GITHUB_REF")
    repository_owner_id = _required_env("GITHUB_REPOSITORY_OWNER_ID")
    repository_id = _required_env("GITHUB_REPOSITORY_ID")
    environment = _required_env("FACTORY_CODEX_GITHUB_ENVIRONMENT")

    while True:
        refresh_once(
            token_file=token_file,
            audience=audience,
            repository=repository,
            ref=ref,
            environment=environment,
            repository_owner_id=repository_owner_id,
            repository_id=repository_id,
        )
        print("codex_oidc_refresh=ok", flush=True)
        if args.refresh_seconds == 0:
            return 0
        time.sleep(args.refresh_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
