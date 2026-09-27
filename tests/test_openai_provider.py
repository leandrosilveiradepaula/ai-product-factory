import json
import unittest

from ai_product_factory.model_executor import ModelRequest, ModelRole
from ai_product_factory.models import Complexity
from ai_product_factory.openai_provider import OpenAIModelPolicy, OpenAIResponsesProvider


class FakeTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, headers, body):
        payload = json.loads(body.decode("utf-8"))
        self.calls.append((method, url, headers, payload))
        return 200, {
            "id": "resp_test",
            "output": [{"content": [{"type": "output_text", "text": "result"}]}],
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        }


class OpenAIResponsesProviderTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.provider = OpenAIResponsesProvider(
            api_key="placeholder-key",
            transport=self.transport,
        )
        self.request = ModelRequest(task_id="t1", objective="Implement", context="ctx")

    def test_complexity_selects_expected_models(self):
        expected = {
            Complexity.LOW: "gpt-5.6-luna",
            Complexity.MEDIUM: "gpt-5.6-terra",
            Complexity.HIGH: "gpt-5.6-terra",
            Complexity.VERY_HIGH: "gpt-5.6-sol",
        }
        for complexity, model in expected.items():
            with self.subTest(complexity=complexity):
                self.provider.execute_for_complexity(self.request, complexity)
                self.assertEqual(self.transport.calls[-1][3]["model"], model)

    def test_request_is_non_persistent_and_bounded(self):
        result = self.provider.execute_for_complexity(
            self.request,
            Complexity.MEDIUM,
            reasoning_effort="low",
        )
        payload = self.transport.calls[-1][3]
        self.assertFalse(payload["store"])
        self.assertEqual(payload["reasoning"]["effort"], "low")
        self.assertEqual(payload["max_output_tokens"], 12000)
        self.assertEqual(result.role, ModelRole.PRIMARY)
        self.assertEqual(result.output, "result")
        self.assertEqual(result.usage["total_tokens"], 15.0)

    def test_api_key_is_only_in_authorization_header(self):
        self.provider.execute(self.request)
        _, _, headers, payload = self.transport.calls[-1]
        self.assertEqual(headers["Authorization"], "Bearer placeholder-key")
        self.assertNotIn("placeholder-key", json.dumps(payload))


    def test_workload_identity_exchanges_github_oidc_and_uses_short_lived_token(self):
        calls = []

        def transport(method, url, headers, body):
            calls.append((method, url, headers, body))
            if method == "GET":
                self.assertIn("audience=api%3A%2F%2Fopenai-factory", url)
                return 200, {"value": "github-oidc-token"}
            if url == "https://auth.openai.com/oauth/token":
                payload = json.loads(body.decode("utf-8"))
                self.assertEqual(payload["subject_token"], "github-oidc-token")
                self.assertEqual(payload["identity_provider_id"], "idp_test")
                self.assertEqual(payload["service_account_id"], "svc_test")
                return 200, {"access_token": "short-lived-openai-token", "expires_in": 3600}
            self.assertEqual(headers["Authorization"], "Bearer short-lived-openai-token")
            return 200, {
                "id": "resp_wif",
                "output": [{"content": [{"type": "output_text", "text": "result"}]}],
                "usage": {"total_tokens": 3},
            }

        env = {
            "OPENAI_IDENTITY_PROVIDER_ID": "idp_test",
            "OPENAI_SERVICE_ACCOUNT_ID": "svc_test",
            "OPENAI_WIF_AUDIENCE": "api://openai-factory",
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://example.invalid/oidc?x=1",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "github-request-token",
        }
        from unittest.mock import patch
        with patch.dict("os.environ", env, clear=True):
            provider = OpenAIResponsesProvider(api_key="", transport=transport)
            result = provider.execute(self.request)
            provider.execute(self.request)
        self.assertEqual(result.provider_ref, "resp_wif")
        self.assertEqual(sum(1 for method, url, _, _ in calls if method == "GET"), 1)
        self.assertEqual(sum(1 for _, url, _, _ in calls if url == "https://auth.openai.com/oauth/token"), 1)

    def test_missing_auth_fails_fast(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError):
                OpenAIResponsesProvider(api_key="", transport=self.transport)

    def test_partial_workload_identity_fails_closed_instead_of_falling_back_to_api_key(self):
        from unittest.mock import patch
        env = {
            "OPENAI_API_KEY": "long-lived-key",
            "OPENAI_IDENTITY_PROVIDER_ID": "idp_test",
        }
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaises(ValueError):
                OpenAIResponsesProvider(transport=self.transport)

    def test_missing_output_text_fails_closed(self):
        def bad_transport(method, url, headers, body):
            return 200, {"id": "resp_test", "output": []}
        p = OpenAIResponsesProvider(api_key="placeholder-key", transport=bad_transport)
        with self.assertRaises(RuntimeError):
            p.execute(self.request)

    def test_model_policy_can_be_overridden(self):
        policy = OpenAIModelPolicy(low="model-low")
        p = OpenAIResponsesProvider(
            api_key="placeholder-key",
            transport=self.transport,
            policy=policy,
        )
        p.execute_for_complexity(self.request, Complexity.LOW)
        self.assertEqual(self.transport.calls[-1][3]["model"], "model-low")


if __name__ == "__main__":
    unittest.main()
