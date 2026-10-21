"""Specialist completion, traceability and DoD share one audited transaction."""
import re
import unittest
from pathlib import Path
from unittest.mock import patch
from ai_product_factory.specialist_lane_queue import (
    SupabaseSpecialistLaneQueue, SpecialistLaneItem,
)

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261021041000_atomic_specialist_traceability_evidence.sql").read_text()
SCRIPT=(ROOT/"scripts/verify_specialist_epoch_postgres.py").read_text()
RUNTIME=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()
QUEUE=(ROOT/"src/ai_product_factory/specialist_lane_queue.py").read_text()


def fake():
    return SpecialistLaneItem(
        job_id="123e4567-e89b-42d3-a456-426614174000",
        run_id="123e4567-e89b-42d3-a456-426614174001",
        project_key="new-product",repository="owner/repo",role="security",
        candidate_commit="a"*40,pr_number=1,issue_number=1,
        manifest={},acceptance_criteria=(),
        claim_token="123e4567-e89b-42d3-a456-426614174099",
    )


class SpecialistTraceabilityAtomicityTests(unittest.TestCase):
    def test_service_role_only_new_entrypoint_and_bounded_schema(self):
        funcs=re.findall(r"CREATE OR REPLACE FUNCTION public\.(factory_[a-z_0-9]+)\(",SQL)
        self.assertEqual(funcs,["factory_complete_specialist_lane_with_trace"])
        self.assertEqual(SQL.count("$function$;"),1)
        self.assertTrue(SQL.strip().endswith("COMMIT;"))
        for forbidden in ("SECURITY DEFINER","CREATE POLICY","CREATE TABLE",
                          "ALTER TABLE","DROP FUNCTION","merge_pull_request","OPENAI_API_KEY"):
            self.assertNotIn(forbidden,SQL)
        self.assertIn("SECURITY INVOKER",SQL)
        self.assertIn("REVOKE ALL ON FUNCTION public.factory_complete_specialist_lane_with_trace(uuid,text,jsonb,jsonb)",SQL)
        self.assertIn("FROM PUBLIC,anon,authenticated",SQL)
        self.assertIn("GRANT EXECUTE ON FUNCTION public.factory_complete_specialist_lane_with_trace(uuid,text,jsonb,jsonb)",SQL)
        self.assertIn("TO service_role",SQL)

    def test_single_transaction_binding_with_verified_job_fields(self):
        self.assertIn("public.factory_complete_specialist_lane_atomic(",SQL)
        self.assertIn("public.factory_record_delivery_evidence(",SQL)
        self.assertIn("v_job.run_id,v_job.role,p_status,v_job.candidate_commit",SQL)
        self.assertIn("'traceability_recorded',true",SQL)
        self.assertIn("'findings_count',jsonb_array_length",SQL)
        self.assertIn("traceability",QUEUE)
        self.assertIn('self._rpc("factory_complete_specialist_lane_with_trace"',QUEUE)
        self.assertNotIn('self._rpc("factory_complete_specialist_lane_atomic"',QUEUE)
        specialist=RUNTIME.split("def run_specialist_once(",1)[1].split("def _assess_release_policy(",1)[0]
        self.assertNotIn("record_delivery_evidence(",specialist)
        self.assertEqual(specialist.count("queue.complete("),1)

    def test_missing_receipt_or_invalid_counts_is_not_a_success(self):
        queue=SupabaseSpecialistLaneQueue(url="https://example.supabase.co",
                                           secret_key="sb_secret_test")
        basic={"post_review_applied":True}
        variants=[
            basic,
            {**basic,"traceability_recorded":True},
            {**basic,"traceability_recorded":True,
             "traceability":{"requirements_linked":True,"dod_checks_linked":0}},
            {**basic,"traceability_recorded":True,
             "traceability":{"requirements_linked":-1,"dod_checks_linked":0}},
            {**basic,"traceability_recorded":True,
             "traceability":{"requirements_linked":0,"dod_checks_linked":"0"}},
        ]
        with patch.object(queue,"_rpc") as rpc:
            for response in variants:
                with self.subTest(response=response):
                    rpc.return_value=response
                    with self.assertRaisesRegex(RuntimeError,"atomic traceability"):
                        queue.complete(fake(),status="passed",findings=[],evidence={})
        self.assertEqual(rpc.call_count,len(variants))

    def test_isolated_real_postgres_exercises_rollback_dod_and_deduplication(self):
        for term in ("REFUSING_NON_ISOLATED_SPECIALIST_EPOCH_DATABASE",
                     "factory_specialist_epoch_test","traceability-write-failure",
                     "trace_fn","trace_migration","factory_requirement_evidence",
                     "factory_definition_of_done_evidence",
                     "delivery.evidence.recorded","traceability_recorded",
                     "SPECIALIST_EPOCH_POSTGRES_PASS=1"):
            self.assertIn(term,SCRIPT)


if __name__=="__main__":
    unittest.main()
