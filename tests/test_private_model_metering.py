import unittest
from decimal import Decimal

from ai_product_factory.model_executor import ModelRequest
from ai_product_factory.models import ExecutionRoute
from ai_product_factory.private_chat_provider import PrivateModelError
from ai_product_factory.private_model_metering import (
    PrivatePricing, MeteredPrivateProvider, build_guarded_sql_infodive_executor
)

ENV = {
    "FACTORY_SQL_INFODIVE_ENABLED": "true",
    "FACTORY_SQL_INFODIVE_PRIVATE_ROUTE_ATTESTED": "true",
    "FACTORY_SQL_INFODIVE_BASE_URL": "http://10.66.66.1",
    "FACTORY_SQL_INFODIVE_MODEL": "SQL-InfoDive",
    "FACTORY_SQL_INFODIVE_HTTP_HOST": "chat.internal",
    "FACTORY_SQL_INFODIVE_ALLOW_PRIVATE_HTTP": "true",
    "FACTORY_SQL_INFODIVE_API_KEY": "fixture-only",
    "FACTORY_SQL_INFODIVE_PRICING_APPROVED": "true",
    "FACTORY_SQL_INFODIVE_INPUT_USD_PER_MILLION": "0",
    "FACTORY_SQL_INFODIVE_OUTPUT_USD_PER_MILLION": "0",
}

class Receipt:
    id = "fixture-receipt"

class Ledger:
    def __init__(self):
        self.reservations = []
        self.updates = []
    def record_tool_usage(self, **kw):
        self.reservations.append(kw)
        return Receipt()
    def update_tool_usage(self, *args, **kw):
        self.updates.append(kw)

def valid_transport(*args):
    return 200, {
        "choices": [{"message": {"content": "SELECT 1"}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 5,
                  "total_tokens": 25},
    }

class CostTests(unittest.TestCase):
    def test_price_missing_and_unknown_not_assumed_zero(self):
        for env in ({}, {**ENV, "FACTORY_SQL_INFODIVE_PRICING_APPROVED": "false"},
                    {**ENV, "FACTORY_SQL_INFODIVE_INPUT_USD_PER_MILLION": ""}):
            with self.assertRaises(PrivateModelError):
                PrivatePricing.from_env(env)
        self.assertEqual(PrivatePricing.from_env(ENV).cost(2,3), Decimal(0))
        priced = PrivatePricing(Decimal("2.5"), Decimal("10"))
        self.assertEqual(priced.cost(1_000_000, 1_000_000), Decimal("12.5"))

    def test_success_with_isolated_ledger_no_paid_network(self):
        ledger = Ledger()
        executor = build_guarded_sql_infodive_executor(
            env=ENV, transport=valid_transport, ledger=ledger,
            test_reserve=Decimal("0.5"))
        result = executor.execute(ExecutionRoute.DIRECT,
            ModelRequest(task_id="sql", run_id="run-fixture",
                         objective="test", context="fixture"))
        self.assertEqual(result.output, "SELECT 1")
        self.assertEqual(ledger.reservations[0]["tool_family"], "model")
        self.assertEqual(ledger.reservations[0]["estimated_cost"], 0.5)
        self.assertEqual(ledger.updates[0]["operation"], "private_sql_completed")
        self.assertEqual(ledger.updates[0]["estimated_cost"], 0)

    def test_ambiguous_response_keeps_unknown_paid_cost(self):
        ledger = Ledger()
        executor = build_guarded_sql_infodive_executor(
            env=ENV, transport=lambda *args: (200, {"choices": [
                {"message": {"content": "SELECT 1"}}]}),
            ledger=ledger, test_reserve=Decimal("0.5"))
        with self.assertRaises(PrivateModelError):
            executor.execute(ExecutionRoute.DIRECT, ModelRequest(
                task_id="sql", run_id="run-fixture", objective="x", context="y"))
        self.assertEqual(ledger.updates[-1]["operation"], "private_sql_cost_unknown")
        self.assertIsNone(ledger.updates[-1]["estimated_cost"])

    def test_over_reserve_is_not_mislabeled_unknown(self):
        ledger = Ledger()
        pricing = PrivatePricing(Decimal(10000), Decimal(10000))
        class Provider:
            def execute(self, req):
                from ai_product_factory.model_executor import ModelResult,ModelRole
                return ModelResult(ModelRole.PRIMARY,"ok",model="SQL-InfoDive",
                    usage={"input_tokens":100.0,"output_tokens":100.0})
        wrapper = MeteredPrivateProvider(Provider(), pricing, store=ledger,
                                         reserve=Decimal("0.01"))
        with self.assertRaisesRegex(PrivateModelError,"exceeded"):
            wrapper.execute(ModelRequest(task_id="x",run_id="r",objective="x",context="y"))
        self.assertEqual(ledger.updates[-1]["operation"], "private_sql_over_reserve")
        self.assertIsNotNone(ledger.updates[-1]["estimated_cost"])

    def test_no_run_id_never_reserves(self):
        ledger=Ledger()
        executor=build_guarded_sql_infodive_executor(
            env=ENV, transport=valid_transport, ledger=ledger,
            test_reserve=Decimal("0.5"))
        with self.assertRaises(PrivateModelError):
            executor.execute(ExecutionRoute.DIRECT,
                ModelRequest(task_id="x",objective="x",context="y"))
        self.assertFalse(ledger.reservations)

if __name__ == "__main__":
    unittest.main()


class PrivateRouteBeforeCostTests(unittest.TestCase):
    def test_invalid_route_never_writes_paid_ledger(self):
        ledger=Ledger()
        class BadRoute:
            def verify_route(self):
                raise PrivateModelError("private VPS route unavailable")
            def execute(self, req):
                raise AssertionError("must not call model")
        provider=MeteredPrivateProvider(
            BadRoute(), PrivatePricing.from_env(ENV),
            store=ledger, reserve=Decimal("0.5"))
        with self.assertRaisesRegex(PrivateModelError, "route unavailable"):
            provider.execute(ModelRequest(task_id="t", run_id="r", objective="x", context="y"))
        self.assertEqual(ledger.reservations, [])
        self.assertEqual(ledger.updates, [])
