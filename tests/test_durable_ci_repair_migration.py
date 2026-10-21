import pathlib
import unittest


SQL = pathlib.Path("supabase/migrations/20261021213414_durable_ci_repair_requests.sql").read_text(encoding="utf-8").lower()


class DurableCIRepairMigrationTests(unittest.TestCase):
    def test_is_private_and_durable(self):
        self.assertIn("create table public.factory_ci_repair_requests", SQL)
        self.assertIn("enable row level security", SQL)
        self.assertIn("revoke all on public.factory_ci_repair_requests from public, anon, authenticated", SQL)
        self.assertIn("unique(source_run_id, original_candidate_commit)", SQL)
        self.assertIn("lease_owner", SQL)
        self.assertIn("execution_generation", SQL)

    def test_enqueues_only_exact_candidate_with_bounded_attempts(self):
        self.assertIn("ci repair source identity or epoch revoked", SQL)
        self.assertIn("ci repair durable pr receipt revoked", SQL)
        self.assertIn("p_max_attempts not between 1 and 3", SQL)
        self.assertIn("ci_repair_attempts_exhausted", SQL)
        self.assertIn("non_code_ci_failure", SQL)
        self.assertIn("repair_scope_unknown", SQL)

    def test_reuses_change_set_and_records_later_ci_result(self):
        self.assertIn("factory_change_set_work_units", SQL)
        self.assertIn("factory_sync_ci_repair_request", SQL)
        self.assertIn("factory_sync_ci_repair_lease", SQL)
        self.assertIn("factory_record_ci_repair_result", SQL)
        self.assertIn("status='awaiting_ci'", SQL)
        self.assertIn("status='passed'", SQL)
        self.assertIn("status='ci_failed'", SQL)

    def test_cannot_create_auto_merge_or_public_access(self):
        self.assertNotIn("merge_pull_request", SQL)
        self.assertNotIn("grant all on public.factory_ci_repair_requests", SQL)
        self.assertNotIn("authenticated to public.factory_ci_repair_requests", SQL)
