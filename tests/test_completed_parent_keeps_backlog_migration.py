from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase"/"migrations"/"20261006023500_completed_parent_keeps_backlog.sql"


class CompletedParentKeepsBacklogMigrationTests(unittest.TestCase):
    def test_reconciliation_only_invalidates_children_of_cancelled_parent(self):
        text=MIGRATION.read_text()
        self.assertIn("where parent.status='cancelled'",text)
        self.assertNotIn("where parent.status in ('completed','cancelled')",text)

    def test_change_set_only_supersedes_when_root_cancelled(self):
        text=MIGRATION.read_text()
        self.assertIn("where root.status='cancelled'",text)
        self.assertNotIn("where root.status in ('completed','cancelled')",text)
        self.assertIn("'root_task_cancelled'",text)

    def test_backfill_recovers_only_audited_children_cancelled_under_completed_parent(self):
        text=MIGRATION.read_text()
        self.assertIn("parent.status='completed'",text)
        self.assertIn("e.event_type='task.descendant.reconciled'",text)
        self.assertIn("e.payload->>'reason'='parent_terminal_child_no_longer_actionable'",text)
        self.assertIn("e.payload->>'parent_status'='completed'",text)
        self.assertIn("'task.descendant.recovered_after_completed_parent'",text)

    def test_backfill_restores_superseded_change_set_from_exact_audit(self):
        text=MIGRATION.read_text()
        self.assertIn("s.metadata#>>'{reconciliation,reason}'='root_task_terminal'",text)
        self.assertIn("e.event_type='change_set.superseded_after_terminal_root'",text)
        self.assertIn("'change_set.recovered_after_completed_root'",text)

    def test_function_remains_private(self):
        text=MIGRATION.read_text()
        self.assertIn("security invoker",text)
        self.assertIn("revoke all on function public.factory_reconcile_terminal_task_descendants()",text)
        self.assertIn("grant execute on function public.factory_reconcile_terminal_task_descendants() to service_role",text)


if __name__=="__main__":
    unittest.main()
