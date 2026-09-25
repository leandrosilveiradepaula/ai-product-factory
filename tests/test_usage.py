import unittest
from decimal import Decimal

from ai_product_factory.usage import ModelUsage, summarize_usage, usage_from_openai


class UsageTests(unittest.TestCase):
    def test_summary_keeps_unknown_cost_explicit(self):
        summary = summarize_usage([
            ModelUsage("openai", "a", 10, 5, cost_usd=Decimal("0.01")),
            ModelUsage("openai", "b", 20, 7, cost_usd=None),
        ])
        self.assertEqual(summary.calls, 2)
        self.assertEqual(summary.input_tokens, 30)
        self.assertEqual(summary.output_tokens, 12)
        self.assertEqual(summary.known_cost_usd, Decimal("0.01"))
        self.assertEqual(summary.calls_without_cost, 1)

    def test_openai_usage_mapping(self):
        item = usage_from_openai(
            model="model-x",
            usage={"input_tokens": 12.0, "output_tokens": 3.0},
            auth_kind="chatgpt_access_token",
        )
        self.assertEqual(item.total_tokens, 15)
        self.assertEqual(item.auth_kind, "chatgpt_access_token")
        self.assertIsNone(item.cost_usd)


if __name__ == "__main__":
    unittest.main()
