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
        self.assertEqual(SQL.lower().count("create or replace function public.factory_"), len(names) + 1)
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
        self.assertIn("grant execute on function public.factory_assert_routed_run_epoch", SQL.lower())
        self.assertNotIn("disable row level security", SQL.lower())
        self.assertNotIn("service_role_key", SQL.lower())

    def test_claimed_epoch_requires_matching_generation_lease_and_route(self):
        body = SQL.split("create or replace function public.factory_assert_routed_run_epoch(", 1)[1]
        for required in (
            "v_generation is distinct from p_generation",
            "v_state not in ('running','pausing','stopping')",
            "v_run.status is distinct from 'implementing'",
            "v_run.execution_route not in ('direct','codex')",
            "v_run.lease_owner is distinct from p_worker_id",
            "v_run.lease_expires_at<=now()",
            "v_run.metadata->>'execution_generation' is distinct from p_generation::text",
        ):
            with self.subTest(required=required):
                self.assertIn(required, body)

    def test_new_claims_are_fenced_independently_of_owned_run_drain(self):
        self.assertEqual(SQL.count("perform public.factory_assert_project_running("), 5)
        body = SQL.split("create or replace function public.factory_assert_routed_run_epoch(", 1)[1]
        self.assertIn("('running','pausing','stopping')", body)
        self.assertIn("raise exception 'routed run epoch revoked'", body)
