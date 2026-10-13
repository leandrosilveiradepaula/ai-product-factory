from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20261013203000_guard_change_set_materialization.sql"


class ChangeSetMaterializationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.sql = MIGRATION.read_text()
        self.materialize, self.dispatch = self.sql.split(
            "create or replace function public.factory_dispatch_next_planned_task", 1
        )

    def test_existing_change_set_is_read_only_for_all_statuses(self):
        self.assertIn("where team_plan_id=v_team.id for update", self.materialize)
        self.assertIn("'already_materialized',true", self.materialize)
        self.assertNotIn("delete from public.factory_change_set_work_units", self.materialize)
        self.assertNotIn("on conflict(team_plan_id) do update", self.materialize)
        self.assertNotIn("on conflict(change_set_id,task_id) do update", self.materialize)

    def test_rejects_stale_or_already_executed_work(self):
        self.assertIn("newer.version>v_team.version", self.materialize)
        self.assertIn("v_task_status<>'queued'", self.materialize)
        self.assertIn("planned task already has execution history", self.materialize)
        self.assertIn("planned task already has work unit history", self.materialize)

    def test_dispatch_restricts_to_latest_ready_plan(self):
        self.assertIn("select id,status into v_team_id,v_team_status", self.dispatch)
        self.assertIn("s.team_plan_id=v_team_id", self.dispatch)
        self.assertIn("t.status='queued'", self.dispatch)
        self.assertIn("s.status in ('planned','building')", self.dispatch)
        self.assertIn("prior_unit.id<>u.id", self.dispatch)

    def test_functions_are_invoker_only_and_private(self):
        self.assertEqual(self.sql.count("security invoker"), 2)
        for function, arg in (
            ("factory_materialize_change_set", "uuid"),
            ("factory_dispatch_next_planned_task", "text"),
        ):
            self.assertIn("revoke all on function public." + function + "(" + arg + ") from public,anon,authenticated", self.sql)
            self.assertIn("grant execute on function public." + function + "(" + arg + ") to service_role", self.sql)


if __name__ == "__main__":
    unittest.main()
