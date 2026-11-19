"""General IBM Cloud model selection tests. No external API or paid requests."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from decimal import Decimal
from ai_product_factory.model_executor import ModelRequest
from ai_product_factory.private_chat_provider import build_sql_infodive_provider
from ai_product_factory.primary_provider_selection import (
    OPENAI, INFODIVE, selected_primary_provider,
    require_primary_provider_ready, require_agent_provider_policy,
)
from ai_product_factory.private_model_vps_readiness import assess

SHA = "c"*40
ENV = {
    "FACTORY_PRIMARY_MODEL_ENABLED":"true",
    "FACTORY_PRIMARY_MODEL_PROVIDER":"infodive_ibm_cloud",
    "FACTORY_INFODIVE_VPS_WORKER_ENABLED":"true",
    "FACTORY_SQL_INFODIVE_WORKER_SHA":SHA,
    "FACTORY_SQL_INFODIVE_ENABLED":"true",
    "FACTORY_SQL_INFODIVE_PRIVATE_ROUTE_ATTESTED":"true",
    "FACTORY_SQL_INFODIVE_BASE_URL":"http://10.66.66.1",
    "FACTORY_SQL_INFODIVE_MODEL":"SQL-InfoDive",
    "FACTORY_SQL_INFODIVE_HTTP_HOST":"chat.internal",
    "FACTORY_SQL_INFODIVE_ALLOW_PRIVATE_HTTP":"true",
    "FACTORY_SQL_INFODIVE_API_KEY":"fixture-only",
    "FACTORY_SQL_INFODIVE_PRICING_APPROVED":"true",
    "FACTORY_SQL_INFODIVE_INPUT_USD_PER_MILLION":"0",
    "FACTORY_SQL_INFODIVE_OUTPUT_USD_PER_MILLION":"0",
}

class Policy:
    reserve_usd=Decimal("0.50")

class GeneralProviderTests(unittest.TestCase):
    def test_default_stays_openai_and_invalid_choice_denied(self):
        self.assertEqual(selected_primary_provider({}),OPENAI)
        self.assertEqual(selected_primary_provider(ENV),INFODIVE)
        with self.assertRaises(PermissionError):
            selected_primary_provider({**ENV,"FACTORY_PRIMARY_MODEL_PROVIDER":"unknown"})

    def test_ibm_never_uses_github_actions_or_unapproved_vps(self):
        for changes in ({"GITHUB_ACTIONS":"true"},
                        {"FACTORY_INFODIVE_VPS_WORKER_ENABLED":"false"},
                        {"FACTORY_PRIMARY_MODEL_ENABLED":"false"}):
            route=Mock()
            with self.subTest(changes=changes),self.assertRaises(PermissionError):
                require_primary_provider_ready({**ENV,**changes},
                    local_head=lambda:SHA,route_check=route)
            route.assert_not_called()

    def test_shas_prices_and_tokens_must_be_ready_before_route(self):
        for changes in ({"FACTORY_SQL_INFODIVE_WORKER_SHA":"bad"},
                        {"FACTORY_SQL_INFODIVE_PRICING_APPROVED":"false"},
                        {"FACTORY_SQL_INFODIVE_API_KEY":""},
                        {"FACTORY_SQL_INFODIVE_PRIVATE_ROUTE_ATTESTED":"false"}):
            route=Mock()
            with self.subTest(changes=changes),self.assertRaises((RuntimeError,PermissionError)):
                require_primary_provider_ready({**ENV,**changes},
                    local_head=lambda:SHA,route_check=route)
            route.assert_not_called()

    def test_preclaim_network_check_is_private_tcp_no_model(self):
        calls=[]
        result=require_primary_provider_ready(ENV,local_head=lambda:SHA,
                route_check=lambda url,**kw:calls.append((url,kw)))
        self.assertEqual(result,INFODIVE)
        self.assertEqual(calls,[("http://10.66.66.1",{"interface":"wg-ibm","tcp":True})])

    def test_direct_agent_requires_persisted_provider_binding(self):
        for policy in ({},{"provider":INFODIVE},
                       {"provider":INFODIVE,"enabled":"true"},
                       {"provider":OPENAI,"enabled":True}):
            with self.assertRaises(PermissionError):
                require_agent_provider_policy(SimpleNamespace(model_policy=policy),INFODIVE)
        require_agent_provider_policy(
            SimpleNamespace(model_policy={"provider":INFODIVE,"enabled":True}),INFODIVE)
        require_agent_provider_policy(SimpleNamespace(model_policy={}),OPENAI)

    def test_general_code_json_output_schema_is_transmitted(self):
        captured=[]
        def transport(method,url,headers,body,timeout):
            captured.append(json.loads(body))
            return 200,{"choices":[{"message":{"content":'{"files":[]}'}}],
                        "usage":{"prompt_tokens":12,"completion_tokens":8,"total_tokens":20}}
        provider=build_sql_infodive_provider(env=ENV,transport=transport)
        schema={"type":"object","properties":{"files":{"type":"array"}}}
        result=provider.execute(ModelRequest(task_id="general",objective="Implement a website",
                context="normal software repository",output_schema=schema))
        prompt=json.loads(captured[0]["messages"][0]["content"])
        self.assertEqual(prompt["output_schema"],schema)
        self.assertIn("JSON",prompt["output_rule"])
        self.assertEqual(result.output,'{"files":[]}')
        self.assertEqual(result.provider_ref,INFODIVE)
        self.assertNotIn("response_format",captured[0])

    def test_preflight_ready_is_not_run_success(self):
        result=assess(ENV,head=SHA,route=lambda *a,**kw:None,
                capacity=lambda:Policy()).receipt()
        self.assertEqual(result["status"],"preflight_ready")
        self.assertEqual(result["worker"],"configured")
        self.assertFalse(result["model_invoked"])
        self.assertFalse(result["run_claimed"])
        self.assertNotIn("fixture-only",json.dumps(result))

if __name__=="__main__":
    unittest.main()
