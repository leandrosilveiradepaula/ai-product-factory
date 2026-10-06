from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase"/"migrations"/"20261006013000_preserve_planning_decision_continuation.sql"


class PreservePlanningDecisionContinuationMigrationTests(unittest.TestCase):
    def test_terminal_reconciliation_skips_active_planning_continuation(self):
        text=MIGRATION.read_text()
        self.assertIn("continuation_run.task_id=child.id",text)
        self.assertIn("continuation_run.status in ('created','queued','running')",text)
        self.assertIn("continuation_run.metadata->>'source'='planning-decision'",text)

    def test_backfill_is_bounded_to_proven_accidental_cancellation(self):
        text=MIGRATION.read_text()
        self.assertIn("t.status='cancelled'",text)
        self.assertIn("r.status='created'",text)
        self.assertIn("r.metadata->>'source'='planning-decision'",text)
        self.assertIn("g.status='approved'",text)
        self.assertIn("e.event_type='task.descendant.reconciled'",text)
        self.assertIn("e.payload->>'reason'='parent_terminal_child_no_longer_actionable'",text)

    def test_backfill_requeues_task_and_audits_recovery(self):
        text=MIGRATION.read_text()
        self.assertIn("set status='queued'",text)
        self.assertIn("'planning_decision.continuation.recovered'",text)
        self.assertIn("'terminal_descendant_reconciliation_cancelled_valid_continuation'",text)

    def test_function_remains_private_security_invoker(self):
        text=MIGRATION.read_text()
        self.assertIn("security invoker",text)
        self.assertIn("revoke all on function public.factory_reconcile_terminal_task_descendants()",text)
        self.assertIn("grant execute on function public.factory_reconcile_terminal_task_descendants() to service_role",text)


if __name__=="__main__":
    unittest.main()
