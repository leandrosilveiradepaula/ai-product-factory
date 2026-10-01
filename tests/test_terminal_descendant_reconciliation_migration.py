import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase"/"migrations"/"20261001165031_factory_reconcile_terminal_task_descendants.sql"


class TerminalDescendantReconciliationMigrationTests(unittest.TestCase):
    def test_function_is_private_security_invoker(self):
        text=MIGRATION.read_text()
        self.assertIn("security invoker",text)
        self.assertIn("revoke all on function public.factory_reconcile_terminal_task_descendants() from public,anon,authenticated",text)
        self.assertIn("grant execute on function public.factory_reconcile_terminal_task_descendants() to service_role",text)

    def test_integrated_children_complete_and_other_nonterminal_children_cancel(self):
        text=MIGRATION.read_text()
        self.assertIn("if v_row.old_status='integrated'",text)
        self.assertIn("set status='completed'",text)
        self.assertIn("set status='cancelled'",text)
        self.assertIn("parent.status in ('completed','cancelled')",text)

    def test_change_sets_become_superseded_without_rewriting_work_units(self):
        text=MIGRATION.read_text()
        self.assertIn("set status='superseded'",text)
        self.assertIn("change_set.superseded_after_terminal_root",text)
        self.assertNotIn("update public.factory_change_set_work_units",text)

    def test_reconciliation_is_audited_and_idempotent_by_terminal_filters(self):
        text=MIGRATION.read_text()
        self.assertIn("task.descendant.reconciled",text)
        self.assertIn("child.status not in ('completed','cancelled')",text)
        self.assertIn("s.status not in ('completed','superseded')",text)


if __name__=="__main__":
    unittest.main()
