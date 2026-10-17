"""Guard routed RPC lifecycle gates without needing paid models or production DB."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "supabase/migrations/20261017224500_guard_routed_claims_manual_control.sql").read_text()

class RoutedControlMigrationTests(unittest.TestCase):
    def test_all_five_rpcs_are_fenced(self):
        names = (
            "factory_claim_next_agent_direct_run",
            "factory_claim_next_agent_codex_run",
            "factory_schedule_eligible_direct_run",
            "factory_schedule_eligible_codex_run",
            "factory_dispatch_preapproved_planned_task_v2",
        )
        self.assertEqual(SQL.lower().count("create or replace function public.factory_"), len(names))
        self.assertEqual(SQL.count("perform public.factory_assert_project_running("), len(names))
        for name in names:
            self.assertIn("FUNCTION public." + name + "(", SQL)
        self.assertIn("BEGIN;", SQL)
        self.assertIn("COMMIT;", SQL)

    def test_preserves_codex_tool_guard_and_mode_isolation(self):
        self.assertIn("codex_execution_mode", SQL)
        self.assertIn("github_write", SQL)
        self.assertIn("factory_run_agent_assignments", SQL)
        self.assertIn("factory_change_set_work_units", SQL)

    def test_no_permissions_or_billing_bypass(self):
        self.assertNotIn("grant execute", SQL.lower())
        self.assertNotIn("disable row level security", SQL.lower())
        self.assertNotIn("service_role_key", SQL.lower())
