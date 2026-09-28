from decimal import Decimal
import unittest
from ai_product_factory.resource_limits import ResourceLimit,github_actions_usage,summarize_limit,vercel_daily_deployments

class Tests(unittest.TestCase):
 def test_thresholds(self):
  self.assertEqual(ResourceLimit("x","r","m",Decimal(69),Decimal(100)).status,"normal")
  self.assertEqual(ResourceLimit("x","r","m",Decimal(70),Decimal(100)).status,"attention")
  self.assertEqual(ResourceLimit("x","r","m",Decimal(90),Decimal(100)).status,"critical")
  self.assertEqual(ResourceLimit("x","r","m",Decimal(100),Decimal(100)).status,"blocked")
 def test_unknown_never_invents_percent(self):
  item=github_actions_usage(used=None,limit=None)
  self.assertIsNone(item.percent);self.assertEqual(item.status,"unknown");self.assertEqual(item.quality,"unknown")
 def test_vercel_derived_counter(self):
  item=vercel_daily_deployments(count=55)
  self.assertEqual(item.percent,Decimal("55"));self.assertEqual(item.quality,"derived")
  self.assertEqual(summarize_limit(item)["percent"],55.0)

if __name__=="__main__":unittest.main()
