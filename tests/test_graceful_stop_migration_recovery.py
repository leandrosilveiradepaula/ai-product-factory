"""Fail-closed contract for manual Graceful STOP migration-history recovery.

All checks are local file inspections. No network, database write or model call.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs/GRACEFUL_STOP_MIGRATION_RECONCILIATION.md"
VERIFY = ROOT / "scripts/sql/verify_graceful_stop_production_readonly.sql"
TEMPORARY_WORKFLOW = ROOT / ".github/workflows/graceful-stop-production-migration.yml"
MIGRATION = ROOT / "supabase/migrations/20261017193000_factory_graceful_stop_preserve_queue.sql"


class GracefulStopMigrationRecoveryTests(unittest.TestCase):
    def test_source_migration_retained(self):
        self.assertTrue(MIGRATION.is_file())
        self.assertIn("factory_assert_claimed_run_epoch", MIGRATION.read_text())

    def test_no_reapply_workflow_remains(self):
        self.assertFalse(TEMPORARY_WORKFLOW.exists())

    def test_runbook_uses_official_history_repair_not_schema_reapply(self):
        text = RUNBOOK.read_text()
        self.assertIn("supabase migration repair 20261017193000 --status applied", text)
        self.assertIn("supabase migration list", text)
        self.assertIn("scripts/sql/verify_graceful_stop_production_readonly.sql", text)
        self.assertIn("nao reaplicar", text.lower())
        self.assertNotIn("insert into supabase_migrations", text.lower())

    def test_read_only_preflight_has_safe_scope(self):
        text = VERIFY.read_text().lower()
        self.assertIn("select", text)
        self.assertIn("'pass'", text)
        self.assertIn("'fail'", text)
        for role in ("service_role", "anon", "authenticated"):
            self.assertIn(role, text)
        for fn in (
            "factory_guard_project_execution_dml",
            "factory_control_project_v1",
            "factory_settle_project_control_v1",
            "factory_assert_claimed_run_epoch",
            "factory_claim_next_run",
        ):
            self.assertIn(fn, text)
        for verb in ("insert into ", "update public.", "delete from ", "drop table ", "create or replace ", "alter table ", "grant execute ", "revoke "):
            self.assertNotIn(verb, text)


if __name__ == "__main__":
    unittest.main()
