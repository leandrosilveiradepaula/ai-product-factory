import unittest
from pathlib import Path

class PortfolioPlannedTaskEligibilityTests(unittest.TestCase):
    def test_migration_preserves_fail_closed_guards(self):
        root = Path(__file__).resolve().parents[1]
        sql = (root / "supabase/migrations/20261013172800_factory_portfolio_planned_task_eligibility.sql").read_text()
        self.assertIn("pt.status='queued' and pt.external_key like 'plan-%'", sql)
        self.assertIn("(has_runnable_work or has_planned_task_work)", sql)
        self.assertIn("not paused and active_runs<max_active_workers", sql)
        self.assertIn("(not v_has_p0 or incident_rank=0)", sql)
        self.assertIn("security invoker", sql)
        self.assertIn("revoke all on function public.factory_portfolio_candidates(integer) from public,anon,authenticated", sql)
        self.assertIn("grant execute on function public.factory_portfolio_candidates(integer) to service_role", sql)

if __name__ == "__main__":
    unittest.main()
