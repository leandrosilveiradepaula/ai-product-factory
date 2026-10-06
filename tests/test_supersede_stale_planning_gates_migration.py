from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase"/"migrations"/"20261006012500_supersede_stale_planning_gates.sql"


class SupersedeStalePlanningGatesMigrationTests(unittest.TestCase):
    def test_runtime_supersedes_older_pending_planning_gates(self):
        text=MIGRATION.read_text()
        self.assertIn("factory_supersede_stale_planning_gates",text)
        self.assertIn("and g.gate_type='planning_decision'",text)
        self.assertIn("and g.status='pending'",text)
        self.assertIn("and (p_keep_gate_id is null or g.id<>p_keep_gate_id)",text)
        self.assertIn("perform public.factory_supersede_stale_planning_gates(v_project_id,v_gate_id)",text)

    def test_supersession_closes_gate_run_and_task_with_audit(self):
        text=MIGRATION.read_text()
        self.assertIn("set status='rejected'",text)
        self.assertIn("'resolution','superseded'",text)
        self.assertIn("set status='cancelled'",text)
        self.assertIn("'human_gate.superseded'",text)
        self.assertIn("'superseded_by_gate_id',p_keep_gate_id",text)

    def test_backfill_keeps_latest_planning_gate_even_when_latest_is_resolved(self):
        text=MIGRATION.read_text()
        block=text.split("do $$",1)[1]
        self.assertIn("where t2.project_id=t.project_id",block)
        self.assertIn("and g2.gate_type='planning_decision'",block)
        self.assertNotIn("g2.status='pending'",block)
        self.assertIn("order by g2.requested_at desc,g2.id desc",block)

    def test_helper_is_private_and_security_invoker(self):
        text=MIGRATION.read_text()
        self.assertIn("security invoker",text)
        self.assertIn("revoke all on function public.factory_supersede_stale_planning_gates(uuid,uuid)",text)
        self.assertIn("grant execute on function public.factory_supersede_stale_planning_gates(uuid,uuid)",text)


if __name__=="__main__":
    unittest.main()
