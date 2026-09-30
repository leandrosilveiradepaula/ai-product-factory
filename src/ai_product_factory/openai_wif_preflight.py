from __future__ import annotations

import base64
import json
import os
import urllib.parse
import urllib.request

from .openai_provider import GitHubActionsOpenAIWorkloadIdentity


SAFE_CLAIM_KEYS = (
    "iss",
    "aud",
    "sub",
    "repository",
    "repository_owner",
    "ref",
    "environment",
    "workflow",
    "workflow_ref",
    "job_workflow_ref",
    "event_name",
)


def _decode_jwt_claims(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise RuntimeError("GitHub OIDC token is not a JWT")
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("GitHub OIDC token payload is invalid") from exc
    if not isinstance(claims, dict):
        raise RuntimeError("GitHub OIDC token claims are invalid")
    return claims


def _request_github_oidc_claims() -> dict:
    request_url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"].strip()
    request_token = os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"].strip()
    audience = os.environ["OPENAI_WIF_AUDIENCE"].strip()

    parts = urllib.parse.urlsplit(request_url)
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    query["audience"] = audience
    oidc_url = urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment)
    )
    req = urllib.request.Request(
        oidc_url,
        headers={"Authorization": f"bearer {request_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("GitHub OIDC claim inspection failed") from exc
    token = payload.get("value") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError("GitHub OIDC claim inspection returned no token")
    return _decode_jwt_claims(token)


def _validate_github_oidc_claims(claims: dict) -> dict:
    expected = {
        "iss": "https://token.actions.githubusercontent.com",
        "aud": os.environ["OPENAI_WIF_AUDIENCE"].strip(),
        "repository": os.environ["FACTORY_WIF_EXPECTED_REPOSITORY"].strip(),
        "ref": os.environ["FACTORY_WIF_EXPECTED_REF"].strip(),
        "environment": os.environ["FACTORY_WIF_EXPECTED_ENVIRONMENT"].strip(),
    }
    mismatches = []
    for key, value in expected.items():
        observed = claims.get(key)
        if observed != value:
            mismatches.append(f"{key}: expected {value!r}, observed {observed!r}")
    if mismatches:
        raise RuntimeError("GitHub OIDC claim validation failed: " + "; ".join(mismatches))
    return {key: claims.get(key) for key in SAFE_CLAIM_KEYS if key in claims}


def main() -> int:
    required = (
        "OPENAI_IDENTITY_PROVIDER_ID",
        "OPENAI_SERVICE_ACCOUNT_ID",
        "OPENAI_WIF_AUDIENCE",
        "ACTIONS_ID_TOKEN_REQUEST_URL",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
        "FACTORY_WIF_EXPECTED_REPOSITORY",
        "FACTORY_WIF_EXPECTED_REF",
        "FACTORY_WIF_EXPECTED_ENVIRONMENT",
    )
    missing = [name for name in required if not os.getenv(name, "").strip()]
    if missing:
        raise RuntimeError("API WIF preflight configuration is incomplete: " + ", ".join(missing))

    safe_claims = _validate_github_oidc_claims(_request_github_oidc_claims())
    print("github_oidc_claims=" + json.dumps(safe_claims, sort_keys=True))

    identity = GitHubActionsOpenAIWorkloadIdentity.from_env()
    token = identity.get_access_token()
    if not token:
        raise RuntimeError("OpenAI API WIF preflight did not receive an access token")

    print("api_wif_preflight=ok")
    print("auth_mode=workload_identity")
    print("model_call=not_performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
