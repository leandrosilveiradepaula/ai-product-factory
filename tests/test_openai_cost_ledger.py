from __future__ import annotations

import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from ai_product_factory.metered_provider import MeteredPrimaryProvider
from ai_product_factory.model_executor import ModelRequest, ModelResult, ModelRole
from ai_product_factory.openai_costs import estimate_openai_text_cost_usd


class _UsageRow:
    id = "77"


class _Store:
    def __init__(self):
        self.recorded = []
        self.updated = []

    def record_tool_usage(self, **kwargs):
        self.recorded.append(kwargs)
        return _UsageRow()

    def update_tool_usage(self, usage_id, **kwargs):
        self.updated.append((usage_id, kwargs))
        return _UsageRow()


class _Provider:
    def execute(self, request):
        return ModelResult(
            role=ModelRole.PRIMARY,
            output="ok",
            provider_ref="resp_test",
            usage={
                "input_tokens": 1000.0,
                "cached_input_tokens": 100.0,
                "output_tokens": 100.0,
                "total_tokens": 1100.0,
            },
            model="gpt-5.6-luna",
        )


class _FailingProvider:
    def execute(self, request):
        raise RuntimeError("provider failed")


class OpenAICostLedgerTests(unittest.TestCase):
    def test_short_context_cost_handles_cached_input(self):
        cost = estimate_openai_text_cost_usd(
            model="gpt-5.6-luna",
            usage={"input_tokens": 1000, "cached_input_tokens": 100, "output_tokens": 100},
        )
        self.assertEqual(cost, Decimal("0.000302"))

    def test_long_context_uses_long_context_rates(self):
        cost = estimate_openai_text_cost_usd(
            model="gpt-5.6-luna",
            usage={"input_tokens": 300000, "cached_input_tokens": 0, "output_tokens": 1000},
        )
        self.assertEqual(cost, Decimal("0.1218"))

    def test_unknown_model_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no approved pricing"):
            estimate_openai_text_cost_usd(
                model="unknown-model",
                usage={"input_tokens": 1, "output_tokens": 1},
            )

    def test_metered_provider_reserves_then_records_actual(self):
        store = _Store()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            metered = MeteredPrimaryProvider(
                _Provider(),
                store=store,
                reserve_usd=Decimal("0.01"),
            )
            result = metered.execute(
                ModelRequest(task_id="task", objective="x", context="", run_id="run-1")
            )
        self.assertEqual(result.output, "ok")
        self.assertEqual(store.recorded[0]["operation"], "model_call_reserved")
        self.assertEqual(store.recorded[0]["estimated_cost"], 0.01)
        usage_id, update = store.updated[0]
        self.assertEqual(usage_id, "77")
        self.assertEqual(update["operation"], "model_call")
        self.assertEqual(update["estimated_cost"], 0.000302)
        self.assertEqual(update["metadata"]["input_tokens"], 1000)
        self.assertEqual(update["metadata"]["cached_input_tokens"], 100)

    def test_failed_provider_keeps_conservative_reservation(self):
        store = _Store()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            metered = MeteredPrimaryProvider(
                _FailingProvider(),
                store=store,
                reserve_usd=Decimal("0.01"),
            )
            with self.assertRaisesRegex(RuntimeError, "provider failed"):
                metered.execute(
                    ModelRequest(task_id="task", objective="x", context="", run_id="run-1")
                )
        self.assertEqual(len(store.recorded), 1)
        self.assertEqual(len(store.updated), 0)

    def test_paid_request_requires_run_id(self):
        store = _Store()
        metered = MeteredPrimaryProvider(
            _Provider(),
            store=store,
            reserve_usd=Decimal("0.01"),
        )
        with self.assertRaisesRegex(ValueError, "requires run_id"):
            metered.execute(ModelRequest(task_id="task", objective="x", context=""))


if __name__ == "__main__":
    unittest.main()
