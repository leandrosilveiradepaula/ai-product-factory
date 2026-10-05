import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase"/"migrations"/"20261005131000_preserve_pending_human_gate_descendants.sql"


class PreservePendingHumanGateDescendantsMigrationTests(unittest.TestCase):
    def test_pending_human_gate_excludes_child_from_terminal_reconciliation(self):
        text=MIGRATION.read_text()
        self.assertIn("not exists (",text)
        self.assertIn("join public.factory_human_gates gate on gate.run_id=gate_run.id",text)
        self.assertIn("where gate_run.task_id=child.id",text)
        self.assertIn("and gate.status='pending'",text)

    def test_existing_terminal_reconciliation_behavior_is_retained(self):
        text=MIGRATION.read_text()
        self.assertIn("if v_row.old_status='integrated'",text)
        self.assertIn("set status='completed'",text)
        self.assertIn("set status='cancelled'",text)
        self.assertIn("set status='superseded'",text)

    def test_function_remains_private_security_invoker(self):
        text=MIGRATION.read_text()
        self.assertIn("security invoker",text)
        self.assertIn("revoke all on function public.factory_reconcile_terminal_task_descendants() from public,anon,authenticated",text)
        self.assertIn("grant execute on function public.factory_reconcile_terminal_task_descendants() to service_role",text)


if __name__=="__main__":
    unittest.main()
