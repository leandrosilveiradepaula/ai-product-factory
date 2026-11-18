"""Static contracts for the owner-requested blocked-work recovery path.

The production migration remains human-gated.  These checks protect the
fail-closed lineage and Console wiring without contacting Supabase.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (ROOT / "supabase/migrations/20261118160000_operator_blocked_work_recovery.sql").read_text(encoding="utf-8")
CONTROL = (ROOT / "apps/console/lib/control-plane.ts").read_text(encoding="utf-8")
PAGE = (ROOT / "apps/console/app/projects/[key]/page.tsx").read_text(encoding="utf-8")


class BlockedWorkRecoveryContract(unittest.TestCase):
    def test_creates_linked_continuation_without_mutating_terminal_change_set(self):
        self.assertIn("factory_blocked_work_recovery_requests", MIGRATION)
        self.assertIn("terminal_change_set_id", MIGRATION)
        self.assertIn("'stages',jsonb_build_array('reconciliation','gap_analysis','planning')", MIGRATION)
        self.assertNotIn("update public.factory_change_sets", MIGRATION.lower())
        self.assertNotIn("update public.factory_repair_jobs", MIGRATION.lower())

    def test_requires_running_cas_and_bounded_unleased_blocked_repair(self):
        for marker in (
            "c.version<>p_expected_version or c.state<>'running'",
            "status='blocked' and cycle<max_cycles",
            "lease_owner is null and lease_expires_at is null",
            "j.change_set_id::text is distinct from r.metadata->>'change_set_id'",
            "unique(project_id,command_id)",
            "unique(repair_job_id)",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, MIGRATION)

    def test_wake_is_durable_and_request_state_tracks_worker_transitions(self):
        self.assertIn("factory_project_execution_commands", MIGRATION)
        self.assertIn("'restart'", MIGRATION)
        self.assertIn("factory_sync_blocked_work_recovery_request", MIGRATION)
        self.assertIn("when 'implementing' then 'recovering'", MIGRATION)
        self.assertIn("when 'completed' then 'completed'", MIGRATION)
        self.assertIn("when 'blocked' then 'blocked'", MIGRATION)

    def test_console_keeps_lifecycle_restart_separate_from_blocked_recovery(self):
        command = CONTROL.split("export async function commandProjectExecution(", 1)[1].split(
            "\n/** Queue a new, auditable", 1
        )[0]
        self.assertIn("factory_control_project_v1", command)
        self.assertNotIn("factory_restart_blocked_work_v1", command)
        self.assertIn("export async function restartBlockedProjectWork", CONTROL)
        self.assertIn("factory_restart_blocked_work_v1", CONTROL)
        self.assertIn("deliverProjectControlWake(commandId)", CONTROL)
        self.assertIn("restartBlockedWork", PAGE)
        self.assertIn('executionControl.state==="running"?restartBlockedWork:controlProject', PAGE)


if __name__ == "__main__":
    unittest.main()
