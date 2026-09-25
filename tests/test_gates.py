import unittest

from ai_product_factory.gates import requires_human_gate
from ai_product_factory.models import RiskProfile


class GateTests(unittest.TestCase):
    def test_low_risk_change_is_autonomous(self):
        required, reasons = requires_human_gate(RiskProfile())
        self.assertFalse(required)
        self.assertEqual(reasons, ())

    def test_production_change_requires_gate(self):
        required, reasons = requires_human_gate(RiskProfile(production_change=True))
        self.assertTrue(required)
        self.assertIn("mudanca em producao", reasons)

    def test_paid_service_requires_gate(self):
        required, reasons = requires_human_gate(RiskProfile(new_paid_service=True))
        self.assertTrue(required)
        self.assertIn("novo servico pago", reasons)


if __name__ == "__main__":
    unittest.main()
