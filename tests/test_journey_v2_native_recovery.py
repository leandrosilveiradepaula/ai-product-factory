"""Offline contract tests for the only permitted V2 empty-plan recovery."""
from pathlib import Path
from unittest.mock import MagicMock
import unittest

from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261031120000_native_journey_v2_recovery.sql").read_text()
JOURNEY="88e94d11-4ada-4630-aa6a-fbf2c5665b2b"
RUN="27d71826-4527-4dc4-b727-870bb5687c4e"
TASK="07837b7f-3fc1-43b9-8f5f-41dc65731810"
PROJECT="11111111-1111-4111-8111-111111111111"
SHA="fea4669258fcd832c7e187e7b00c1c5fb4d90a76"

class JourneyV2NativeRecoveryTests(unittest.TestCase):
    def test_sql_is_single_fenced_service_only_recovery(self):
        self.assertIn("factory_resume_failed_journey_v2",SQL)
        for token in ("SECURITY INVOKER","FOR UPDATE OF p0","FOR UPDATE","c.state IS DISTINCT FROM 'running'",
                      "j.execution_generation IS DISTINCT FROM c.generation","source.metadata->>'error' IS DISTINCT FROM 'planning has no actionable tasks or decisions'",
                      "source.metadata->'journey_binding_v2' IS DISTINCT FROM j.binding","journey_v2_planning_recovery_v1",
                      "project has active incompatible work","candidate_commit IS NOT NULL","REVOKE ALL","TO service_role"):
            self.assertIn(token,SQL)
        for forbidden in ("SECURITY DEFINER","merge_pull_request","OPENAI_API_KEY","factory_retry_failed_run","delivery_target"):
            self.assertNotIn(forbidden,SQL)

    def test_adapter_is_idempotent_and_never_calls_legacy_retry(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        q._rpc=MagicMock(return_value={"created":True,"journey_id":JOURNEY,"run_id":"new"})
        self.assertEqual(q.resume_failed_journey_v2(JOURNEY)["run_id"],"new")
        self.assertEqual(q._rpc.call_args.args[0],"factory_resume_failed_journey_v2")
        self.assertNotIn("retry",q._rpc.call_args.args[0])

    def test_recovery_scan_is_bounded_and_reports_only_control_plane_receipts(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        q._get=lambda path:[{"id":JOURNEY}]
        q.resume_failed_journey_v2=lambda ident:{"created":False,"journey_id":ident,"run_id":"existing"}
        result=q.recover_failed_journeys_v2()
        self.assertEqual(result["queued"],0)
        self.assertEqual(result["outcomes"][0]["status"],"already_queued")

    def test_invalid_identity_and_bound_recovery_limit_fail_before_rpc(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        q._rpc=MagicMock()
        with self.assertRaises(ValueError): q.resume_failed_journey_v2("not-a-uuid")
        with self.assertRaises(ValueError): q.recover_failed_journeys_v2(9)
        q._rpc.assert_not_called()

    def test_v2_checkpoint_rejects_cross_journey_or_generation_before_model(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        checkpoint={"schema":"journey_v2_planning_recovery_v1","journey_id":JOURNEY,
            "project_id":PROJECT,"source_run_id":RUN,"generation":16,"source_commit":SHA,
            "reconciliation":{"summary":"observed"},"gap_analysis":{"recommended_next_work":["work"]}}
        original={"journey_binding_v2":{"journey_id":JOURNEY,"request_id":"request","source_commit":SHA}}
        claimed={"journey_id":JOURNEY}
        metadata={"journey_id":JOURNEY,"stages":["planning"],"execution_generation":16}
        source={"id":RUN,"task_id":TASK,"journey_id":JOURNEY,"status":"failed","execution_route":"direct","source_commit":SHA,
          "metadata":{"error":"planning has no actionable tasks or decisions","stages":["reconciliation","gap_analysis","planning"],"execution_generation":16,
            "stage_evidence":{"reconciliation":{"output":checkpoint["reconciliation"]},"gap_analysis":{"output":checkpoint["gap_analysis"]}}}}
        q._get=lambda path:[source]
        context=q._v2_planning_resume_context("new",TASK,PROJECT,16,original,claimed,metadata,checkpoint)
        self.assertEqual(context["_verified_resume_prior_stages"]["gap_analysis"],checkpoint["gap_analysis"])
        checkpoint["generation"]=17
        with self.assertRaisesRegex(PermissionError,"checkpoint identity"):
            q._v2_planning_resume_context("new",TASK,PROJECT,16,original,claimed,metadata,checkpoint)

if __name__=="__main__": unittest.main()
