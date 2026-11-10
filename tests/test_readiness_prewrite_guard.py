import unittest
from ai_product_factory.readiness_prewrite_guard import require_monotonic_before_write,ReadinessPrewriteRegression
from ai_product_factory.product_readiness import REQUIRED_COVERAGE_BY_DOMAIN
REPO="leandrosilveiradepaula/ai-product-factory"
SHA="a"*40
def report(status="missing"):
 return {"criteria":{d:{k:{"status":status} for k in keys} for d,keys in REQUIRED_COVERAGE_BY_DOMAIN.items()}}
def old(r):
 return [{"repository":REPO,"assessed_commit":SHA,"state":"persisted","report":r}]
class GuardTests(unittest.TestCase):
 def test_no_history(self):
  require_monotonic_before_write(repository=REPO,assessed_commit=SHA,new_report=report(),get=lambda p:[])
 def test_preserves_passed(self):
  r=report()
  r["criteria"]["documentation"]["operations"]["status"]="passed"
  require_monotonic_before_write(repository=REPO,assessed_commit=SHA,new_report=r,get=lambda p:old(r))
 def test_blocks_loss_even_if_total_increases(self):
  earlier=report()
  earlier["criteria"]["documentation"]["operations"]["status"]="passed"
  later=report()
  for k in ("responsive","surface_inventory"):
   later["criteria"]["product_experience"][k]["status"]="passed"
  with self.assertRaises(ReadinessPrewriteRegression):
   require_monotonic_before_write(repository=REPO,assessed_commit=SHA,new_report=later,get=lambda p:old(earlier))
 def test_invalid_history_fails_closed(self):
  with self.assertRaises(ReadinessPrewriteRegression):
   require_monotonic_before_write(repository=REPO,assessed_commit=SHA,new_report=report(),get=lambda p:{"error":"unavailable"})
if __name__=="__main__":unittest.main()
