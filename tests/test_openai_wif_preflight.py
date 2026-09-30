from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ai_product_factory import openai_wif_preflight


class ApiWifPreflightTests(unittest.TestCase):
    def test_missing_configuration_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                openai_wif_preflight.main()

    def test_success_never_prints_token(self):
        env = {
            "OPENAI_IDENTITY_PROVIDER_ID": "idp_test",
            "OPENAI_SERVICE_ACCOUNT_ID": "user-test",
            "OPENAI_WIF_AUDIENCE": "https://api.openai.com/v1",
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://example.invalid/oidc",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "request-token",
            "FACTORY_WIF_EXPECTED_REPOSITORY": "leandrosilveiradepaula/ai-product-factory",
            "FACTORY_WIF_EXPECTED_REF": "refs/heads/main",
            "FACTORY_WIF_EXPECTED_ENVIRONMENT": "openai-api",
        }
        claims = {
            "iss": "https://token.actions.githubusercontent.com",
            "aud": "https://api.openai.com/v1",
            "sub": "repo:example",
            "repository": "leandrosilveiradepaula/ai-product-factory",
            "ref": "refs/heads/main",
            "environment": "openai-api",
            "workflow_ref": "leandrosilveiradepaula/ai-product-factory/.github/workflows/openai-api-wif-preflight.yml@refs/heads/main",
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "ai_product_factory.openai_wif_preflight._request_github_oidc_claims",
            return_value=claims,
        ), patch(
            "ai_product_factory.openai_wif_preflight.GitHubActionsOpenAIWorkloadIdentity.from_env"
        ) as factory, patch("builtins.print") as printer:
            factory.return_value.get_access_token.return_value = "super-secret-short-lived-token"
            self.assertEqual(openai_wif_preflight.main(), 0)
        rendered = "\n".join(" ".join(str(x) for x in call.args) for call in printer.call_args_list)
        self.assertIn("api_wif_preflight=ok", rendered)
        self.assertIn("model_call=not_performed", rendered)
        self.assertIn("github_oidc_claims=", rendered)
        self.assertIn("workflow_ref", rendered)
        self.assertNotIn("super-secret-short-lived-token", rendered)
        self.assertNotIn("request-token", rendered)



    def test_claim_mismatch_fails_before_openai_exchange(self):
        env = {
            "OPENAI_IDENTITY_PROVIDER_ID": "idp_test",
            "OPENAI_SERVICE_ACCOUNT_ID": "user-test",
            "OPENAI_WIF_AUDIENCE": "https://api.openai.com/v1",
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://example.invalid/oidc",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "request-token",
            "FACTORY_WIF_EXPECTED_REPOSITORY": "leandrosilveiradepaula/ai-product-factory",
            "FACTORY_WIF_EXPECTED_REF": "refs/heads/main",
            "FACTORY_WIF_EXPECTED_ENVIRONMENT": "openai-api",
        }
        claims = {
            "iss": "https://token.actions.githubusercontent.com",
            "aud": "https://api.openai.com/v1",
            "repository": "someone/else",
            "ref": "refs/heads/main",
            "environment": "openai-api",
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "ai_product_factory.openai_wif_preflight._request_github_oidc_claims",
            return_value=claims,
        ), patch(
            "ai_product_factory.openai_wif_preflight.GitHubActionsOpenAIWorkloadIdentity.from_env"
        ) as factory:
            with self.assertRaisesRegex(RuntimeError, "repository"):
                openai_wif_preflight.main()
        factory.assert_not_called()

    def test_decode_rejects_non_jwt(self):
        with self.assertRaisesRegex(RuntimeError, "not a JWT"):
            openai_wif_preflight._decode_jwt_claims("not-a-jwt")

if __name__ == "__main__":
    unittest.main()
