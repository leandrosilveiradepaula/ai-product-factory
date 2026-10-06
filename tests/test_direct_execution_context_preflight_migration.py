from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase"/"migrations"/"20261006020000_direct_execution_context_preflight.sql"


class DirectExecutionContextPreflightMigrationTests(unittest.TestCase):
    def test_block_rpc_closes_run_task_unit_and_change_set(self):
        text=MIGRATION.read_text()
        self.assertIn("factory_block_change_set_work_unit",text)
        self.assertIn("set status='blocked'",text)
        self.assertIn("'change_set.work_unit.blocked'",text)
        self.assertIn("'blocker_type',v_blocker_type",text)
        self.assertIn("lease_owner=null",text)
        self.assertIn("lease_expires_at=null",text)

    def test_recovery_requeues_expired_implementing_direct_work(self):
        text=MIGRATION.read_text()
        self.assertIn("r.status='implementing'",text)
        self.assertIn("r.lease_expires_at<=now()",text)
        self.assertIn("r.attempt_count<p_max_attempts",text)
        self.assertIn("set status='queued'",text)
        self.assertIn("set status='queued_execution'",text)
        self.assertIn("'execution.direct.requeued_after_expired_lease'",text)

    def test_internal_rpcs_remain_service_role_only(self):
        text=MIGRATION.read_text()
        self.assertIn("revoke all on function public.factory_block_change_set_work_unit(uuid,text,text)",text)
        self.assertIn("grant execute on function public.factory_block_change_set_work_unit(uuid,text,text)",text)
        self.assertIn("revoke all on function public.factory_recover_change_sets(integer)",text)


if __name__=="__main__":
    unittest.main()
