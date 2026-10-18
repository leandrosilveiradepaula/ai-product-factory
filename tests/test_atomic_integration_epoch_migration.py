"""Static guardrails for the privileged epoch integration migration.

Runtime behavior is independently exercised by isolated PostgreSQL 16 QA.
"""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261018013000_atomic_change_set_integration_epoch_writes.sql").read_text()


class AtomicIntegrationEpochMigrationTests(unittest.TestCase):
    def test_all_external_mutations_have_atomic_epoch_capabilities(self):
        for signature in (
            "factory_complete_change_set_integration_epoch(",
            "factory_prepare_change_set_release_epoch(",
        ):
            self.assertEqual(SQL.count("create or replace function public."+signature),1)
        self.assertIn("p_project_id uuid,p_generation bigint,p_worker_id text",SQL)
        self.assertIn("p_wave integer",SQL)
        self.assertIn("for share",SQL)
        self.assertIn("for update",SQL)
        self.assertIn("clock_timestamp()",SQL)
        self.assertIn("v_state is distinct from 'running'",SQL)
        self.assertIn("v_generation is distinct from p_generation",SQL)
        self.assertIn("v_set.lease_owner is distinct from p_worker_id",SQL)
        self.assertIn("v_set.current_wave is distinct from p_wave",SQL)

    def test_completion_proves_exact_changed_files_and_merges_repairs_atomically(self):
        self.assertIn("v_expected is distinct from v_provided",SQL)
        self.assertIn("u.base_commit is distinct from v_set.candidate_commit",SQL)
        self.assertIn("u.status is distinct from 'completed'",SQL)
        self.assertIn("v_updated<>v_count",SQL)
        self.assertIn("update public.factory_repair_jobs r",SQL)
        self.assertIn("v_status:='review_ready'",SQL)
        self.assertIn("v_status:='building'",SQL)
        self.assertIn("'integration_epoch_receipt'",SQL)
        self.assertIn("'repair_jobs_integrated'",SQL)

    def test_release_proves_receipt_and_is_transactionally_idempotent(self):
        self.assertIn("v_set.metadata->'integration_epoch_receipt' is distinct from v_receipt",SQL)
        self.assertIn("v_set.metadata->'integration_release_request' = v_request",SQL)
        self.assertIn("v_set.release_run_id is not null",SQL)
        self.assertIn("v_set.integration_branch is distinct from p_branch",SQL)
        self.assertIn("insert into public.factory_runs",SQL)
        self.assertIn("insert into public.factory_tool_usage",SQL)
        self.assertIn("insert into public.factory_audit_events",SQL)
        self.assertIn("'idempotent',true",SQL)

    def test_three_phase_checkpoints_and_readiness_gate(self):
        self.assertIn("factory_assert_change_set_integration_epoch(",SQL)
        self.assertIn("v_set.status='integrating'",SQL)
        self.assertIn("v_set.status='review_ready'",SQL)
        self.assertIn("v_set.status='ci_pending'",SQL)
        self.assertIn("factory_integration_epoch_write_readiness()",SQL)
        self.assertIn("unsafe legacy integration write grant still enabled",SQL)

    def test_invoker_only_and_no_legacy_mutation_grants(self):
        self.assertNotIn("security definer",SQL.lower())
        for legacy in (
            "factory_complete_change_set_integration(uuid,text,jsonb)",
            "factory_mark_repair_wave_integrated(uuid,integer,text)",
            "factory_prepare_change_set_release(uuid,integer,text,integer,text,text)",
        ):
            self.assertIn("revoke all on function public."+legacy,SQL)
        for active in (
            "factory_complete_change_set_integration_epoch(uuid,uuid,bigint,text,integer,text,jsonb)",
            "factory_prepare_change_set_release_epoch(uuid,uuid,bigint,text,integer,integer,text,integer,text,text)",
            "factory_integration_epoch_write_readiness()",
        ):
            self.assertIn("grant execute on function public."+active,SQL)
            self.assertIn("revoke all on function public."+active,SQL)


if __name__=="__main__":
    unittest.main()
