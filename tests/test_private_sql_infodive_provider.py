import json
import unittest
from unittest.mock import patch
from ai_product_factory.private_model_vps_route import PrivateVpsRouteError

from ai_product_factory.model_executor import ModelRequest
from ai_product_factory.private_chat_provider import (
    PrivateChatConfig, PrivateModelError, build_sql_infodive_provider,
    SqlInfodiveProvider,
)

ENV = {
    "FACTORY_SQL_INFODIVE_ENABLED": "true",
    "FACTORY_SQL_INFODIVE_PRIVATE_ROUTE_ATTESTED": "true",
    "FACTORY_SQL_INFODIVE_BASE_URL": "http://10.66.66.1",
    "FACTORY_SQL_INFODIVE_MODEL": "SQL-InfoDive",
    "FACTORY_SQL_INFODIVE_HTTP_HOST": "chat.internal",
    "FACTORY_SQL_INFODIVE_ALLOW_PRIVATE_HTTP": "true",
    "FACTORY_SQL_INFODIVE_API_KEY": "test-sentinel-not-real",
}


class PrivateChatTests(unittest.TestCase):
    def test_fails_closed_by_default(self):
        for env in ({}, {"FACTORY_SQL_INFODIVE_ENABLED": "true"}, {
                **ENV, "FACTORY_SQL_INFODIVE_PRIVATE_ROUTE_ATTESTED": "false"}):
            with self.assertRaises(PrivateModelError):
                build_sql_infodive_provider(env=env)

    def test_private_http_rejects_public_and_bad_urls(self):
        for value in ("http://8.8.8.8", "http://example.org", "file:///tmp",
                      "http://10.66.66.1/more", "http://x:y@10.66.66.1",
                      "http://127.0.0.1", "http://10.66.66.1/#fragment"):
            with self.subTest(value=value):
                with self.assertRaises(PrivateModelError):
                    PrivateChatConfig(base_url=value, model_id="SQL-InfoDive",
                                      allow_private_http=True)
        with self.assertRaises(PrivateModelError):
            PrivateChatConfig(base_url="http://10.66.66.1", model_id="SQL-InfoDive")
        with self.assertRaises(PrivateModelError):
            PrivateChatConfig(base_url="http://10.66.66.1", model_id="SQL-InfoDive",
                              allow_private_http=True, host_header="evil\r\nAuthorization:x")

    def test_exact_api_shape_and_usage_without_network(self):
        calls = []
        def fake(method, url, headers, body, timeout):
            calls.append((method, url, headers, json.loads(body), timeout))
            return 200, {"choices": [{"message": {"content": "SELECT 1"}}],
                         "usage": {"prompt_tokens": 10, "completion_tokens": 3,
                                   "total_tokens": 13}}
        provider = build_sql_infodive_provider(env=ENV, transport=fake)
        result = provider.execute(ModelRequest(task_id="sql", objective="explain", context="schema"))
        method, url, headers, body, timeout = calls[0]
        self.assertEqual(url, "http://10.66.66.1/api/chat/completions")
        self.assertEqual(headers["Host"], "chat.internal")
        self.assertEqual(headers["Authorization"], "Bearer test-sentinel-not-real")
        self.assertNotIn("test-sentinel-not-real", json.dumps(body))
        self.assertEqual((method, timeout), ("POST", 180))
        self.assertEqual(body["temperature"], 0)
        self.assertFalse(body["stream"])
        self.assertEqual(body["max_tokens"], 4096)
        self.assertEqual(result.output, "SELECT 1")
        self.assertEqual(result.usage["total_tokens"], 13)
        self.assertEqual(result.provider_ref, "infodive_ibm_cloud")
        self.assertNotIn("test-sentinel-not-real", repr(provider))
        self.assertNotIn("10.66.66.1", repr(provider))

    def test_output_cap_and_explicit_finish_reason_are_retained(self):
        for reason, tokens, reached, truncated in (
            ("length", 4096, True, True),
            ("max_tokens", 40, False, True),
            ("stop", 4096, True, False),
            (None, 3, False, False),
        ):
            def fake(*args):
                return 200, {"choices": [{"message": {"content": "partial"}, "finish_reason": reason}],
                             "usage": {"prompt_tokens": 10, "completion_tokens": tokens}}
            provider = build_sql_infodive_provider(env=ENV, transport=fake)
            result = provider.execute(ModelRequest(task_id="t", objective="plan", context="fixture"))
            self.assertIs(result.output_limit_reached, reached)
            self.assertIs(result.output_truncated, truncated)

    def test_provider_response_errors_are_sanitized(self):
        for status, response in [
            (401, {"error": {"message": "test-sentinel-not-real"}}),
            (429, {"error": {"message": "test-sentinel-not-real"}}),
            (200, {"choices": [{"message": {"content": "SQL"}}]}),
            (200, {"choices": [{"message": {"content": ""}}],
                   "usage": {"prompt_tokens": 2, "completion_tokens": 1}}),
        ]:
            def fake(*args):
                return status, response
            with self.assertRaises(PrivateModelError) as err:
                build_sql_infodive_provider(env=ENV, transport=fake).execute(
                    ModelRequest(task_id="t", objective="x", context="y"))
            self.assertNotIn("test-sentinel-not-real", str(err.exception))

    def test_transport_failure_is_sanitized(self):
        def fail(*args):
            raise RuntimeError("test-sentinel-not-real")
        with self.assertRaises(PrivateModelError) as err:
            build_sql_infodive_provider(env=ENV, transport=fail).execute(
                ModelRequest(task_id="t", objective="x", context="y"))
        self.assertNotIn("test-sentinel-not-real", str(err.exception))


if __name__ == "__main__":
    unittest.main()


class VpsProviderBoundaryTests(unittest.TestCase):
    def test_real_transport_checks_existing_vps_route_before_reading_bearer(self):
        from ai_product_factory.private_chat_provider import SqlInfodiveProvider
        seen = []
        cfg = PrivateChatConfig(base_url="http://10.66.66.1",
                                model_id="SQL-InfoDive", allow_private_http=True,
                                host_header="chat.internal")
        provider = SqlInfodiveProvider(cfg,credential=lambda:seen.append("credential") or "sentinel")
        with patch("ai_product_factory.private_model_vps_route.verify_existing_vps_route",
                   side_effect=PrivateVpsRouteError("unapproved")):
            with self.assertRaisesRegex(PrivateModelError, "route unavailable"):
                provider.execute(ModelRequest(task_id="t", objective="x", context="y"))
        self.assertEqual(seen, [])
