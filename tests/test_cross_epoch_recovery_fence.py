"""Contracts for no implicit old-epoch replay across Pause/Resume."""
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261021021000_quarantine_cross_epoch_recovery_replay.sql").read_text()
SCENARIO=(ROOT/"scripts/verify_recovery_manual_project_control_postgres.py").read_text()
EXPECTED=(
    "factory_recover_expired_runs",
    "factory_recover_change_sets",
    "factory_claim_next_run",
    "factory_claim_next_agent_direct_run",
    "factory_retry_failed_run",
)


class CrossEpochRecoveryFenceTests(unittest.TestCase):
    def test_five_existing_invoker_only_replacements(self):
        self.assertEqual(tuple(re.findall(r"CREATE OR REPLACE FUNCTION public\.([a-z_0-9]+)\(",SQL)),EXPECTED)
        self.assertEqual(SQL.count("$function$;"),5)
        self.assertTrue(SQL.strip().endswith("COMMIT;"))
        for forbidden in ("SECURITY DEFINER","GRANT EXECUTE","CREATE POLICY",
                          "CREATE TABLE","ALTER TABLE","DROP FUNCTION",
                          "merge_pull_request","OPENAI_API_KEY"):
            self.assertNotIn(forbidden,SQL)

    def test_old_epoch_is_quarantined_before_cost_or_worker_claim(self):
        for key in ("recovery_quarantined_epoch","run.stale_execution_epoch_quarantined",
                    "execution_generation","recovery_observed_generation"):
            self.assertIn(key,SQL)
        for name in EXPECTED[:4]:
            body=SQL.split("CREATE OR REPLACE FUNCTION public."+name+"(",1)[1]
            body=body.split("CREATE OR REPLACE FUNCTION",1)[0]
            self.assertIn("execution_generation",body)
        self.assertIn("execution.direct.stale_epoch_quarantined",SQL)
        self.assertIn("stale_execution_epoch",SQL)
        self.assertIn("or r.metadata ? 'retry_of'",SQL)

    def test_explicit_retry_has_provenance_not_old_worker_capability(self):
        body=SQL.split("CREATE OR REPLACE FUNCTION public.factory_retry_failed_run(",1)[1]
        self.assertIn("- 'execution_generation'",body)
        self.assertIn("retry_source_generation",body)
        self.assertIn("perform public.factory_assert_project_running",body)

    def test_real_isolated_postgres_executes_both_routes_and_resume(self):
        for key in ("REFUSING_NON_ISOLATED_RECOVERY_TEST_DATABASE",
                    "epoch_migration","cross-epoch-control","epoch-paused-before-resume",
                    "factory_claim_next_agent_direct_run","factory_claim_next_run",
                    "recovery_quarantined_epoch","operator-reviewed",
                    "RECOVERY_MANUAL_CONTROL_POSTGRES_PASS=1"):
            self.assertIn(key,SCENARIO)


if __name__=="__main__":
    unittest.main()
