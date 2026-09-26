import pathlib,unittest
from decimal import Decimal
from ai_product_factory.cost_policy import evaluate_cost_ceiling
from ai_product_factory.models import RiskProfile
from ai_product_factory.release_policy import ReleaseEnvironment,evaluate_release

ROOT=pathlib.Path(__file__).resolve().parents[1]
class SafetyInvariantTests(unittest.TestCase):
 def test_production_is_always_human_gated(self):
  for risk in (RiskProfile(),RiskProfile(destructive_data_change=True),RiskProfile(new_paid_service=True)):
   d=evaluate_release(ReleaseEnvironment.PROD,risk);self.assertTrue(d.human_gate_required);self.assertFalse(d.may_release_autonomously)
 def test_strict_paid_execution_needs_budget_and_reservation(self):
  self.assertFalse(evaluate_cost_ceiling(budget=None,known_spend=Decimal("0"),reserved_cost=Decimal("1"),strict=True).allowed)
  self.assertFalse(evaluate_cost_ceiling(budget=Decimal("10"),known_spend=Decimal("0"),reserved_cost=None,strict=True).allowed)
 def test_direct_job_is_manual_only(self):
  text=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
  direct=text.split("\n  direct:",1)[1]
  self.assertIn("github.event_name == 'workflow_dispatch'",direct)
  self.assertIn("inputs.run_direct == true",direct)
 def test_control_plane_accepts_modern_or_legacy_server_secret(self):
  text=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
  self.assertIn("SUPABASE_SECRET_KEY",text)
  self.assertIn("SUPABASE_SERVICE_ROLE_KEY",text)
  self.assertIn('[ -n "$SUPABASE_SECRET_KEY" ] || [ -n "$SUPABASE_SERVICE_ROLE_KEY" ]',text)
 def test_primary_requires_explicit_enable_flag(self):
  text=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
  self.assertIn('FACTORY_PRIMARY_MODEL_ENABLED',text)
  self.assertIn('FACTORY_PRIMARY_MODEL_ENABLED\" = \"true',text)
if __name__=="__main__":unittest.main()
