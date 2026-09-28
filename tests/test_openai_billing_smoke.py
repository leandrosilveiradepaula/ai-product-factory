from decimal import Decimal
import unittest

from ai_product_factory.openai_billing_smoke import (
    EXPECTED_OUTPUT,
    MAX_COST_USD,
    MAX_OUTPUT_TOKENS,
    MODEL,
    estimate_cost_usd,
)


class OpenAIBillingSmokeTests(unittest.TestCase):
    def test_smoke_is_bounded_and_uses_low_cost_model(self):
        self.assertEqual(MODEL, "gpt-5.6-luna")
        self.assertEqual(MAX_OUTPUT_TOKENS, 32)
        self.assertEqual(MAX_COST_USD, Decimal("0.01"))
        self.assertEqual(EXPECTED_OUTPUT, "FACTORY_SMOKE_OK")

    def test_cost_estimate_uses_current_standard_luna_rates(self):
        cost = estimate_cost_usd({"input_tokens": 1000, "output_tokens": 100})
        self.assertEqual(cost, Decimal("0.00032"))


if __name__ == "__main__":
    unittest.main()
