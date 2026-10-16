"""Exact one-off OpenAI credit-denial reconciliation contract (offline only).

The SQL is production gated. This test verifies the *shape* of the guarded
migration; it is not a substitute for human billing review or running it.
"""
from pathlib import Path
import unittest

SQL=(Path(__file__).resolve().parents[1]/
    "supabase/migrations/20261016040600_reconcile_openai_credit_denial.sql").read_text()


class CreditDenialReconciliationSQLTests(unittest.TestCase):
    def test_exact_historical_identity_and_refusal(self):
        for marker in (
            "where id=117 for update",
            "fffee538-9781-4905-a69d-f3427d6f66b3",
            "ab1cb363-3716-4cd6-af12-18d856e16fd4",
            "effc36be-212c-42f2-928b-97381b6d8a28",
            "req_c83153187db74f209bf372a1f42d4f5b",
            "HTTP 429; type=insufficient_quota; code=credit_balance_exhausted",
            "model_call_cost_unknown",
            "cost_unknown",
            "u.estimated_cost is not null",
            "s.status<>'blocked'",
            "w.output_commit is not null",
            "v_unknowns<>1",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker,SQL)

    def test_immutable_evidence_and_no_resume_inside_migration(self):
        for marker in (
            "pg_advisory_xact_lock",
            "previous_usage",
            "to_jsonb(u)",
            "model.usage.credit_rejection_reconciled",
            "human-gated-versioned-production-migration",
            "run_unblocked',false",
            "automatic_retry',false",
            "model_called',false",
            "model_call_rejected_credit_exhausted",
            "estimated_cost=0",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker,SQL)
        self.assertNotIn("update public.factory_runs",SQL.lower())
        self.assertNotIn("update public.factory_change_sets",SQL.lower())
        self.assertNotIn("update public.factory_change_set_work_units",SQL.lower())
        self.assertNotIn("/factory-wake",SQL)
        self.assertNotIn("merge_pull_request",SQL)

    def test_repair_is_idempotent_and_rejects_stale_data(self):
        self.assertIn("if exists(",SQL)
        self.assertIn("prior audit conflicts with ledger row",SQL)
        self.assertIn("original run state differs",SQL)
        self.assertIn("unrelated unknown-cost paid events present",SQL)
        self.assertIn("original usage row changed concurrently",SQL)


if __name__=="__main__":
    unittest.main()
