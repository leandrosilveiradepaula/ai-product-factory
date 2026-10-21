"""Specialist leases must be transactionally epoch- and token-fenced."""
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ai_product_factory.specialist_lane_queue import (
    SupabaseSpecialistLaneQueue, SpecialistLaneItem,
)

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase/migrations/20261021030000_fence_specialist_epoch_and_lease_token.sql"
SCENARIO=ROOT/"scripts/verify_specialist_epoch_postgres.py"
WORKFLOW=ROOT/".github/workflows/manual-project-control-postgres.yml"


def item(token=None):
    return SpecialistLaneItem(
        job_id="123e4567-e89b-42d3-a456-426614174000",
        run_id="123e4567-e89b-42d3-a456-426614174001",
        project_key="greenfield-app", repository="owner/repo",
        role="operations",candidate_commit="a"*40,pr_number=3,
        issue_number=5,manifest={},acceptance_criteria=(),
        execution_generation=2,require_execution_generation=True,
        project_id="123e4567-e89b-42d3-a456-426614174002",
        claim_token=token,
    )


class SpecialistEpochContract(unittest.TestCase):
    def test_exact_existing_security_invoker_functions(self):
        sql=MIGRATION.read_text()
        self.assertEqual(
            re.findall(r"CREATE OR REPLACE FUNCTION public\.(factory_[a-z_]+)\(",sql),
            ["factory_enqueue_specialist_lanes","factory_claim_specialist_lane",
             "factory_complete_specialist_lane","factory_recover_specialist_lanes"],
        )
        self.assertEqual(sql.count("$function$;"),4)
        self.assertTrue(sql.strip().endswith("COMMIT;"))
        for forbidden in ("SECURITY DEFINER","GRANT EXECUTE","CREATE POLICY",
                          "CREATE TABLE","DROP FUNCTION","OPENAI_API_KEY",
                          "merge_pull_request"):
            self.assertNotIn(forbidden,sql)

    def test_epoch_bound_in_all_four_mutation_paths(self):
        sql=MIGRATION.read_text()
        for name in ("factory_enqueue_specialist_lanes","factory_claim_specialist_lane",
                     "factory_complete_specialist_lane","factory_recover_specialist_lanes"):
            body=sql.split("CREATE OR REPLACE FUNCTION public."+name+"(",1)[1]
            body=body.split("CREATE OR REPLACE FUNCTION",1)[0]
            self.assertIn("execution_generation",body)
            self.assertIn("_factory_epoch",body)
        self.assertIn("for share of c,p skip locked",sql)
        self.assertIn("for share of c,p;",sql)
        self.assertIn("'specialist.lane.epoch_quarantined'",sql)
        self.assertIn("v_job.lease_expires_at<=now()",sql)
        self.assertIn("'_factory_claim_token'",sql)

    def test_queue_rejects_tokenless_or_reserved_evidence_without_rpc(self):
        queue=SupabaseSpecialistLaneQueue(url="https://x.supabase.co",secret_key="sb_secret_test")
        with patch.object(queue,"_rpc") as rpc:
            with self.assertRaises(RuntimeError):
                queue.complete(item(),status="passed",findings=[],evidence={})
            with self.assertRaises(RuntimeError):
                queue.complete(item("token"),status="passed",findings=[],evidence={"_factory_claim_token":"forged"})
            rpc.assert_not_called()

    def test_token_is_bound_to_exact_rpc_and_not_echoed_into_evidence(self):
        queue=SupabaseSpecialistLaneQueue(url="https://x.supabase.co",secret_key="sb_secret_test")
        token="123e4567-e89b-42d3-a456-426614174099"
        with patch.object(queue,"_rpc",return_value={"status":"passed"}) as rpc:
            out=queue.complete(item(token),status="passed",findings=[],evidence={"model_call":False})
        self.assertEqual(out["status"],"passed")
        self.assertEqual(rpc.call_count,1)
        name,payload=rpc.call_args.args
        self.assertEqual(name,"factory_complete_specialist_lane")
        self.assertEqual(payload["p_evidence"],{"model_call":False,"_factory_claim_token":token})

    def test_real_pg16_regression_is_isolated_and_covers_pause_races(self):
        scenario=SCENARIO.read_text()
        for value in ("REFUSING_NON_ISOLATED_SPECIALIST_EPOCH_DATABASE",
                      "factory_specialist_epoch_test","127.0.0.1",
                      "claimed-before-pause","transactional-completion",
                      "same-epoch-lease","operator-lock-held",
                      "SPECIALIST_EPOCH_POSTGRES_PASS=1"):
            self.assertIn(value,scenario)
        workflow=WORKFLOW.read_text()
        self.assertIn("verify_specialist_epoch_postgres.py",workflow)
        self.assertIn("factory_specialist_epoch_test",workflow)


if __name__=="__main__":
    unittest.main()
