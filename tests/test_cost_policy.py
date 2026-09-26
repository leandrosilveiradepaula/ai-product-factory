import unittest
from decimal import Decimal
from ai_product_factory.cost_policy import evaluate_cost_ceiling,require_cost_ceiling
class Tests(unittest.TestCase):
 def test_allows_within_budget(self):self.assertTrue(evaluate_cost_ceiling(budget=Decimal("10"),known_spend=Decimal("3"),reserved_cost=Decimal("2")).allowed)
 def test_blocks_over_budget(self):self.assertFalse(evaluate_cost_ceiling(budget=Decimal("4"),known_spend=Decimal("3"),reserved_cost=Decimal("2")).allowed)
 def test_strict_blocks_unknown_budget(self):
  with self.assertRaises(PermissionError):require_cost_ceiling(budget=None,known_spend=Decimal("0"),reserved_cost=Decimal("1"),strict=True)
 def test_strict_blocks_unknown_reservation(self):self.assertFalse(evaluate_cost_ceiling(budget=Decimal("10"),known_spend=Decimal("0"),reserved_cost=None,strict=True).allowed)
if __name__=="__main__":unittest.main()
