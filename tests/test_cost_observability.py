import unittest
from ai_product_factory.cost_observability import requires_cost_estimate

class Tests(unittest.TestCase):
    def test_paid_families_require_cost(self):
        for family in ("model","openai","llm","paid_provider","OPENAI"):
            self.assertTrue(requires_cost_estimate(family))
    def test_infrastructure_integrations_do_not_require_per_call_cost(self):
        for family in ("github","supabase","vercel",None,""):
            self.assertFalse(requires_cost_estimate(family))

if __name__=="__main__": unittest.main()
