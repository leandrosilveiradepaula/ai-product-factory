import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase/migrations/20261013212000_align_portfolio_with_dispatcher.sql"
PREVIOUS=ROOT/"supabase/migrations/20261013172800_factory_portfolio_planned_task_eligibility.sql"


class PortfolioDispatchTruthTests(unittest.TestCase):
    def setUp(self):
        self.sql=MIGRATION.read_text()
        self.probe=(ROOT/"src/ai_product_factory/schedule_probe.py").read_text()

    def test_historical_migration_preserved_and_new_one_supersedes_bad_predicate(self):
        self.assertIn("has_planned_task_work", PREVIOUS.read_text())
        self.assertNotIn("has_planned_task_work", self.sql)
        self.assertNotIn("pt.external_key like 'plan-%'", self.sql)
        self.assertIn("where has_runnable_work", self.sql)

    def test_portfolio_reuses_exact_dispatcher_claim_guards(self):
        for token in (
            "tp.status='ready'",
            "tp.version=(",
            "cs.status in ('planned','building')",
            "u.status='pending' and u.wave=cs.current_wave",
            "unit_task.status='queued'",
            "prior.status in ('created','queued','implementing','completed')",
            "older.status in ('queued','running','completed','integrated')",
            "older.id<>u.id",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.sql)

    def test_incident_capacity_auth_and_no_unneeded_vercel_work(self):
        for token in (
            "not paused and active_runs<max_active_workers",
            "(not v_has_p0 or incident_rank=0)",
            "dogfood_manual_audit",
            "security invoker",
            "revoke all on function public.factory_portfolio_candidates(integer) from public,anon,authenticated",
            "grant execute on function public.factory_portfolio_candidates(integer) to service_role",
        ):
            self.assertIn(token,self.sql)
        self.assertIn("pending_change_set_work and bool(portfolio_candidates)",self.probe)
        self.assertNotIn("dispatch_work = pending_change_set_work or assigned_execution_work",self.probe)

    def test_migration_never_resurrects_old_work(self):
        for forbidden in (
            "update public.factory_tasks",
            "update public.factory_change_sets",
            "insert into public.factory_runs",
            "delete from public.factory_change_set_work_units",
        ):
            self.assertNotIn(forbidden,self.sql.lower())


if __name__=="__main__":
    unittest.main()
