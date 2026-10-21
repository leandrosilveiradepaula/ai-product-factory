"""Contracts for exactly-once, human-only release observation and durable replay."""
from pathlib import Path
import unittest
import re

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261021090000_atomic_release_state_and_replay_outbox.sql").read_text()
SCRIPT=(ROOT/"scripts/verify_atomic_project_release_postgres.py").read_text()
ADAPTER=(ROOT/"src/ai_product_factory/project_release_reconciliation.py").read_text()
RUNTIME=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()
RUNNER=(ROOT/".github/workflows/autonomous-runner.yml").read_text()


class AtomicProjectReleaseTests(unittest.TestCase):
    def test_private_invoker_only_functions_without_implicit_merge(self):
        names=re.findall(r"CREATE OR REPLACE FUNCTION public\.(factory_[a-z0-9_]+)\(",SQL)
        self.assertEqual(names,[
            "factory_mark_release_report_released",
            "factory_pending_release_reconciliations_v1",
            "factory_reconcile_observed_release_v1",
            "factory_defer_release_reconciliation_v1",
        ])
        self.assertEqual(SQL.count("$function$;"),4)
        self.assertTrue(SQL.strip().endswith("COMMIT;"))
        for forbidden in ("SECURITY DEFINER","CREATE POLICY","CREATE TABLE",
                          "ALTER TABLE","DROP FUNCTION","merge_pull_request",
                          "OPENAI_API_KEY","FACTORY_PRIMARY_MODEL_ENABLED"):
            self.assertNotIn(forbidden,SQL)
        for signature in (
            "factory_mark_release_report_released(uuid,text)",
            "factory_pending_release_reconciliations_v1(bigint,integer)",
            "factory_reconcile_observed_release_v1(uuid,uuid,text,jsonb,jsonb)",
            "factory_defer_release_reconciliation_v1(bigint)",
        ):
            self.assertIn("REVOKE ALL ON FUNCTION public."+signature,SQL)
            self.assertIn("GRANT EXECUTE ON FUNCTION public."+signature,SQL)
        self.assertEqual(SQL.count("FROM PUBLIC,anon,authenticated;"),4)
        self.assertEqual(SQL.count("TO service_role;"),4)

    def test_merged_provenance_and_fail_closed_product_evidence(self):
        self.assertIn("release.human_merge_observed",SQL)
        self.assertIn("release.reconciliation_requested",SQL)
        self.assertIn("release.reconciliation_needs_review",SQL)
        self.assertIn("r.status='merged'",SQL)
        self.assertIn("rp.status='released'",SQL)
        self.assertIn("rp.report=p_release_report",SQL)
        self.assertIn("stale release cannot overwrite newer observation",SQL)
        self.assertIn("v_report.report->>'merge_sha'",SQL)
        self.assertIn("release_provenance_requires_review",SQL)
        self.assertIn("'product_ready',false",SQL)
        self.assertIn("'global_readiness_evidence_required'",SQL)
        self.assertIn("v_project.manifest=v_new_manifest",SQL)
        self.assertIn("FOR UPDATE",SQL)
        self.assertIn("FOR SHARE OF rp,r,t",SQL)

    def test_no_split_rest_writes_or_stale_project_fallback(self):
        self.assertNotIn('"PATCH"',ADAPTER)
        self.assertNotIn('"factory_project_state_snapshots"',ADAPTER)
        self.assertNotIn('"factory_audit_events"',ADAPTER)
        self.assertIn("rpc/factory_reconcile_observed_release_v1",ADAPTER)
        self.assertIn("rpc/factory_pending_release_reconciliations_v1",ADAPTER)
        self.assertIn("rpc/factory_defer_release_reconciliation_v1",ADAPTER)
        self.assertIn("ReleaseReconciliationRejected",ADAPTER)
        self.assertIn("release_reconciliation_retryable",ADAPTER)
        self.assertIn("run_release_state_settlement(",RUNTIME)
        self.assertIn('"release-state-settle"',RUNTIME)
        self.assertIn("--mode release-state-settle --batch-items 4",RUNNER)
        self.assertIn("continue-on-error: true",RUNNER)

    def test_production_never_implicitly_proves_greenfield_or_pays(self):
        for marker in ("REFUSING_NON_ISOLATED_RELEASE_ATOMIC_DATABASE",
                       "factory_release_atomic_test","human_merge_observed",
                       "rollback","snapshot persistence failure",
                       "out-of-order-release-protection",
                       "factory_defer_release_reconciliation_v1",
                       "FACTORY_ATOMIC_RELEASE_POSTGRES_PASS=1"):
            self.assertIn(marker,SCRIPT)
        self.assertNotIn("github.com/",SCRIPT)
        self.assertNotIn("OPENAI_API_KEY",SCRIPT)


if __name__=="__main__":
    unittest.main()
