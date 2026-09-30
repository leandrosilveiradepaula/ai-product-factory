import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase/migrations/20260930145500_factory_retry_failed_run.sql"


class FailedRunRetryMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql=MIGRATION.read_text()

    def test_retry_rpc_is_fail_closed_and_privileged(self):
        sql=self.sql
        self.assertIn("factory_retry_failed_run",sql)
        self.assertIn("security invoker",sql.lower())
        self.assertIn("source run is not failed",sql)
        self.assertIn("where id=p_source_run_id",sql)
        self.assertIn("for update",sql.lower())
        self.assertIn("retry already exists for source run",sql)
        self.assertIn("metadata->>'retry_of'=p_source_run_id::text",sql)
        self.assertIn("revoke all on function public.factory_retry_failed_run(uuid,text) from public,anon,authenticated",sql.lower())
        self.assertIn("grant execute on function public.factory_retry_failed_run(uuid,text) to service_role",sql.lower())

    def test_retry_creates_new_run_and_preserves_source(self):
        sql=self.sql
        self.assertIn("insert into public.factory_runs",sql)
        self.assertIn("'retry_of',p_source_run_id::text",sql)
        self.assertIn("'retry_reason',v_reason",sql)
        self.assertIn("'retry_source_commit',v_source.source_commit",sql)
        self.assertIn("v_source.source_commit",sql)
        self.assertNotIn("update public.factory_runs set status='queued' where id=p_source_run_id",sql.lower())

    def test_retry_records_audit_and_requeues_task_compatibly(self):
        sql=self.sql
        self.assertIn("'run.retry_queued'",sql)
        self.assertIn("when v_source.execution_route is null or v_source.metadata ? 'stages' then 'queued'",sql)
        self.assertIn("else 'queued_execution'",sql)
        self.assertIn("update public.factory_tasks",sql)


if __name__=="__main__":
    unittest.main()
