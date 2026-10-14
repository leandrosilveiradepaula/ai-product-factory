from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
S=(R/"supabase/migrations/20261014015500_codex_atomic_mode_isolation.sql").read_text()
P=(R/"src/ai_product_factory/runtime_cli.py").read_text()
class Isolation(unittest.TestCase):
 def test_modes_and_claims(self):
  self.assertIn("factory_dispatch_preapproved_planned_task_v2",S)
  self.assertIn("jsonb_build_object('codex_execution_mode',p_codex_mode)",S)
  self.assertGreaterEqual(S.count("metadata->>'codex_execution_mode'='manual'"),2)
  self.assertGreaterEqual(S.count("metadata->>'codex_execution_mode'='automatic'"),3)
  self.assertIn("a.allowed_tools ? 'codex'",S)
 def test_cost_and_exact_run(self):
  self.assertIn('os.getenv("FACTORY_CODEX_COST_APPROVED")=="true"',P)
  self.assertIn("scheduler.schedule_eligible_codex(run_id=decision.run_id",P)
if __name__=="__main__":unittest.main()
