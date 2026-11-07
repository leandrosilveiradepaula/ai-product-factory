"""Adversarial contract for certifier's short-lived broker identity renewal."""
import base64
import json
import unittest
from urllib.parse import parse_qs, urlsplit

from ai_product_factory.control_plane_oidc_refresh import (
    AUDIENCE, BROKER_URL, OIDC_ISSUER, REPOSITORY, WORKFLOW_REF,
    BrokerOIDCRefreshBlocked, refresh_certification_broker_oidc,
)


def b64(obj):
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


def jwt(claim_overrides=None):
    claims = {
        "iss": OIDC_ISSUER,
        "aud": AUDIENCE,
        "repository": REPOSITORY,
        "ref": "refs/heads/main",
        "event_name": "workflow_run",
        "workflow_ref": WORKFLOW_REF,
        "iat": 100000,
        "exp": 100300,
    }
    claims.update(claim_overrides or {})
    return b64({"alg": "RS256"}) + "." + b64(claims) + "." + b64({"sig": "fixture"})


class Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit=None):
        return json.dumps(self.value).encode()


class RefreshTests(unittest.TestCase):
    def environ(self):
        return {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": REPOSITORY,
            "GITHUB_EVENT_NAME": "workflow_run",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_WORKFLOW_REF": WORKFLOW_REF,
            "SUPABASE_URL": BROKER_URL,
            "SUPABASE_SECRET_KEY": "expired-previous-broker-token",
            "ACTIONS_ID_TOKEN_REQUEST_URL":
                "https://pipelines.actions.githubusercontent.com/abc/idtoken?api-version=2.0",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "request-token-sentinel",
        }

    def test_fresh_token_replaces_expired_identity_only_at_broker_boundary(self):
        env = self.environ()
        observed = []
        expected = jwt()

        def open_request(req, *, timeout):
            observed.append((req, timeout))
            return Response({"value": expected})

        refresh_certification_broker_oidc(
            environment=env, opener=open_request, now=100000,
        )
        self.assertEqual(env["SUPABASE_SECRET_KEY"], expected)
        self.assertEqual(env["SUPABASE_SERVICE_ROLE_KEY"], "")
        self.assertEqual(len(observed), 1)
        request, timeout = observed[0]
        self.assertEqual(timeout, 20)
        self.assertEqual(
            parse_qs(urlsplit(request.full_url).query)["audience"], [AUDIENCE],
        )
        self.assertEqual(
            request.get_header("Authorization"), "bearer request-token-sentinel",
        )

    def test_invalid_runner_or_endpoint_never_requests_token(self):
        cases = [
            ("GITHUB_ACTIONS", "false"),
            ("GITHUB_REPOSITORY", "other/repo"),
            ("GITHUB_REF", "refs/pull/10/merge"),
            ("GITHUB_WORKFLOW_REF", "other.yml@refs/heads/main"),
            ("GITHUB_EVENT_NAME", "pull_request"),
            ("SUPABASE_URL", "https://other.supabase.co"),
            ("ACTIONS_ID_TOKEN_REQUEST_URL", "https://attacker.example/idtoken"),
            ("ACTIONS_ID_TOKEN_REQUEST_URL", "http://pipelines.actions.githubusercontent.com/id"),
            ("ACTIONS_ID_TOKEN_REQUEST_URL", "https://pipelines.actions.githubusercontent.com/id?audience=attacker"),
            ("ACTIONS_ID_TOKEN_REQUEST_TOKEN", ""),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                env = self.environ()
                env[field] = value
                def no_request(*args, **kwargs):
                    self.fail("invalid OIDC context must not call endpoint")
                with self.assertRaises(BrokerOIDCRefreshBlocked):
                    refresh_certification_broker_oidc(
                        environment=env, opener=no_request, now=100000,
                    )
                self.assertEqual(
                    env["SUPABASE_SECRET_KEY"], "expired-previous-broker-token",
                )

    def test_malformed_claims_and_expired_tokens_never_replace_identity(self):
        candidates = [
            {"aud": "other"},
            {"repository": "other/repo"},
            {"workflow_ref": "attacker/another-workflow"},
            {"event_name": "workflow_dispatch"},
            {"exp": 100030},
            {"iat": 99900},
            {"iat": True},
            {"exp": "100300"},
        ]
        for claims in candidates:
            with self.subTest(claims=claims):
                env = self.environ()
                def open_request(*args, **kwargs):
                    return Response({"value": jwt(claims)})
                with self.assertRaises(BrokerOIDCRefreshBlocked) as error:
                    refresh_certification_broker_oidc(
                        environment=env, opener=open_request, now=100000,
                    )
                self.assertNotIn("request-token-sentinel", str(error.exception))
                self.assertNotIn("expired-previous-broker-token", str(error.exception))
                self.assertEqual(
                    env["SUPABASE_SECRET_KEY"], "expired-previous-broker-token",
                )

    def test_invalid_provider_reply_fails_closed_without_secret_leaks(self):
        for body in ({}, {"value": ""}, {"value": "not-a-jwt"}):
            with self.subTest(body=body):
                env = self.environ()
                with self.assertRaises(BrokerOIDCRefreshBlocked):
                    refresh_certification_broker_oidc(
                        environment=env,
                        opener=lambda *args, **kwargs: Response(body),
                        now=100000,
                    )
                self.assertEqual(env["SUPABASE_SECRET_KEY"], "expired-previous-broker-token")


if __name__ == "__main__":
    unittest.main()
