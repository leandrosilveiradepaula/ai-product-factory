"""Specialist review-to-repair is one operator-fenced SQL transaction."""
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261021040500_atomic_specialist_repair_handoff.sql").read_text()
SCENARIO=(ROOT/"scripts/verify_specialist_epoch_postgres.py").read_text()
QUEUE=(ROOT/"src/ai_product_factory/specialist_lane_queue.py").read_text()


class AtomicReviewRepairContract(unittest.TestCase):
    def test_three_existing_security_invoker_replacements(self):
        self.assertEqual(re.findall(r"CREATE OR REPLACE FUNCTION public\.(factory_[a-z_]+)\(",SQL),
                         ["factory_enqueue_repair_from_specialist",
                          "factory_close_repairs_after_specialist_pass",
                          "factory_complete_specialist_lane",
                          "factory_complete_specialist_lane_atomic"])
        self.assertEqual(SQL.count("$function$;"),4)
        self.assertTrue(SQL.strip().endswith("COMMIT;"))
        for forbidden in ("SECURITY DEFINER","CREATE POLICY",
                          "CREATE TABLE","DROP FUNCTION","OPENAI_API_KEY","merge_pull_request"):
            self.assertNotIn(forbidden,SQL)
        self.assertIn("REVOKE ALL ON FUNCTION public.factory_complete_specialist_lane_atomic(uuid,text,jsonb,jsonb) FROM PUBLIC,anon,authenticated",SQL)
        self.assertIn("GRANT EXECUTE ON FUNCTION public.factory_complete_specialist_lane_atomic(uuid,text,jsonb,jsonb) TO service_role",SQL)
        self.assertIn("SECURITY INVOKER",SQL)

    def test_complete_invokes_repair_in_same_transaction(self):
        body=SQL.split("CREATE OR REPLACE FUNCTION public.factory_complete_specialist_lane(",1)[1]
        self.assertIn("public.factory_enqueue_repair_from_specialist(",body)
        self.assertIn("public.factory_close_repairs_after_specialist_pass(",body)
        self.assertIn("'post_review_applied',true",body)
        self.assertIn("'_factory_claim_token'",body)
        self.assertIn("for share of c,p;",body)
        self.assertNotIn("factory_enqueue_repair_from_specialist",QUEUE)
        self.assertNotIn("factory_close_repairs_after_specialist_pass",QUEUE)
        self.assertIn("post_review_applied",QUEUE)
        self.assertIn('self._rpc("factory_complete_specialist_lane_atomic"',QUEUE)
        self.assertNotIn('self._rpc("factory_complete_specialist_lane",{',QUEUE)

    def test_both_direct_rpcs_enforce_same_epoch_and_identity(self):
        for name in ("factory_enqueue_repair_from_specialist","factory_close_repairs_after_specialist_pass"):
            body=SQL.split("CREATE OR REPLACE FUNCTION public."+name+"(",1)[1]
            body=body.split("CREATE OR REPLACE FUNCTION",1)[0]
            self.assertIn("r.metadata->>'execution_generation'=c.generation::text",body)
            self.assertIn("v_job.evidence->>'_factory_epoch'=c.generation::text",body)
            self.assertIn("for share of c,p;",body)
            self.assertIn("using errcode='PT409'",body)
        self.assertIn("v_job.findings is distinct from coalesce(p_findings",SQL)
        self.assertIn("where specialist_job_id=p_job_id order by cycle asc limit 1 for update",SQL)

    def test_disposable_postgres_covers_rollback_idempotence_and_resume(self):
        for marker in ("REFUSING_NON_ISOLATED_SPECIALIST_EPOCH_DATABASE",
                       "atomic-repair","atomic-rollback","already_enqueued",
                       "repair.recheck.passed","specialist_review_failed",
                       "generation=2","SPECIALIST_EPOCH_POSTGRES_PASS=1"):
            self.assertIn(marker,SCENARIO)


if __name__=="__main__":
    unittest.main()
