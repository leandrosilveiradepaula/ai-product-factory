"""Short-lived GitHub OIDC renewal at the *persistence boundary*.

The certifier verifies exact-SHA evidence before minting a fresh broker token.
Neither the GitHub OIDC request credential nor the broker JWT is logged or saved.
The broker independently validates the signed JWT and its workflow claims.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import MutableMapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

BROKER_URL = (
    "https://fjplmxfcshhbmzgvyqlm.supabase.co/"
    "functions/v1/factory-runtime-control-plane"
)
REPOSITORY = "leandrosilveiradepaula/ai-product-factory"
WORKFLOW_REF = (
    REPOSITORY + "/.github/workflows/autonomous-runner.yml@refs/heads/main"
)
AUDIENCE = "factory-runtime-control-plane"
OIDC_ISSUER = "https://token.actions.githubusercontent.com"
OIDC_REQUEST_HOST = re.compile(r"pipelines[a-z0-9-]*\.actions\.githubusercontent\.com\Z")
JWT_SEGMENT = re.compile(r"[A-Za-z0-9_-]+\Z")


class BrokerOIDCRefreshBlocked(RuntimeError):
    """Bounded failure; never include broker or GitHub token material."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise BrokerOIDCRefreshBlocked(code)


def _claims(token: str) -> dict:
    parts = token.split(".")
    _require(
        len(parts) == 3
        and all(part and JWT_SEGMENT.fullmatch(part) for part in parts),
        "broker_oidc_response_invalid",
    )
    try:
        raw = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
        _require(len(raw) <= 8192, "broker_oidc_claims_too_large")
        value = json.loads(raw)
    except (ValueError, UnicodeError, binascii.Error):
        raise BrokerOIDCRefreshBlocked("broker_oidc_claims_invalid") from None
    _require(isinstance(value, dict), "broker_oidc_claims_invalid")
    return value


def refresh_certification_broker_oidc(
    *,
    environment: MutableMapping[str, str] | None = None,
    opener=None,
    now: int | None = None,
) -> None:
    """Renew only an exact trusted main/validate observer OIDC identity.

    Called *after* the expensive independent certifier revalidation and *before*
    allocating a Control Plane certification. The existing broker still validates
    the JWT's cryptographic signature; locally parsed claims are only an early
    fail-closed guard, not an authentication substitute.
    """
    env = os.environ if environment is None else environment
    required = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_EVENT_NAME": "workflow_run",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": WORKFLOW_REF,
    }
    _require(
        all(env.get(key) == value for key, value in required.items()),
        "broker_oidc_runner_identity_invalid",
    )
    _require(
        env.get("SUPABASE_URL", "").rstrip("/") == BROKER_URL,
        "broker_oidc_target_invalid",
    )
    request_url = env.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    request_token = env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    _require(
        bool(request_url) and bool(request_token),
        "broker_oidc_request_context_missing",
    )
    try:
        parsed = urlsplit(request_url)
        port = parsed.port
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise BrokerOIDCRefreshBlocked("broker_oidc_endpoint_invalid") from None
    audiences = [value for key, value in pairs if key.lower() == "audience"]
    _require(
        parsed.scheme == "https"
        and bool(parsed.hostname and OIDC_REQUEST_HOST.fullmatch(parsed.hostname))
        and port in (None, 443)
        and not parsed.username
        and not parsed.password
        and bool(parsed.path)
        and not parsed.fragment
        # GitHub may supply the job's requested audience in the runtime URL.
        # It is safe to reuse only our exact audience, once; a different or
        # duplicated audience would make the token request ambiguous.
        and (not audiences or audiences == [AUDIENCE]),
        "broker_oidc_endpoint_invalid",
    )
    query_pairs = pairs if audiences else [*pairs, ("audience", AUDIENCE)]
    audience_url = urlunsplit((
        "https",
        parsed.netloc,
        parsed.path,
        urlencode(query_pairs),
        "",
    ))
    request = urllib.request.Request(
        audience_url,
        headers={
            "Authorization": "bearer " + request_token,
            "Accept": "application/json",
        },
        method="GET",
    )
    open_request = urllib.request.urlopen if opener is None else opener
    try:
        with open_request(request, timeout=20) as response:
            body = response.read(16385)
        _require(len(body) <= 16384, "broker_oidc_response_invalid")
        data = json.loads(body)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        raise BrokerOIDCRefreshBlocked("broker_oidc_refresh_unavailable") from None
    _require(isinstance(data, dict), "broker_oidc_response_invalid")
    token = data.get("value")
    _require(isinstance(token, str) and len(token) < 12000, "broker_oidc_response_invalid")
    claims = _claims(token)
    expected = {
        "iss": OIDC_ISSUER,
        "aud": AUDIENCE,
        "repository": REPOSITORY,
        "ref": "refs/heads/main",
        "event_name": "workflow_run",
        "workflow_ref": WORKFLOW_REF,
    }
    _require(
        all(claims.get(key) == value for key, value in expected.items()),
        "broker_oidc_claims_mismatch",
    )
    current = int(time.time()) if now is None else now
    exp = claims.get("exp")
    iat = claims.get("iat")
    _require(
        type(exp) is int and type(iat) is int
        and current - 60 <= iat <= current + 30
        and current + 90 <= exp <= current + 360,
        "broker_oidc_lifetime_invalid",
    )
    # No print, artifact, environment-file write or token-bearing diagnostics.
    # SupabaseServerConfig will construct a fresh bearer header from this value.
    env["SUPABASE_SECRET_KEY"] = token
    env["SUPABASE_SERVICE_ROLE_KEY"] = ""
