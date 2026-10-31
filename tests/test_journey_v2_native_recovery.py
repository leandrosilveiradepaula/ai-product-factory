"""Offline contract tests for the only permitted V2 empty-plan recovery."""
from pathlib import Path
from unittest.mock import MagicMock
import unittest

from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261031120000_native_journey_v2_recovery.sql").read_text()
REQUEUE_SQL=(ROOT/"supabase/migrations/20261031130000_v2_preflight_requeue_same_run.sql").read_text()
JOURNEY="88e94d11-4ada-4630-aa6a-fbf2c5665b2b"
RUN="27d71826-4527-4dc4-b727-870bb5687c4e"
TASK="07837b7f-3fc1-43b9-8f5f-41dc65731810"
PROJECT="11111111-1111-4111-8111-111111111111"
SHA="fea4669258fcd832c7e187e7b00c1c5fb4d90a76"

class JourneyV2DispatchIntegrationContractTests(unittest.TestCase):
    def test_v2_route_has_epoch_before_status_trigger_and_keeps_v1_path(self):
        sql=(ROOT/"supabase/migrations/20261031144500_v2_routed_epoch_and_integration_binding.sql").read_text()
        self.assertIn("v_run_md:=v_run_md||jsonb_build_object(",sql)
        self.assertIn("'execution_generation',v_generation",sql)
        self.assertIn("'journey_binding_v2',v_journey.binding",sql)
        self.assertIn("values(v_task.id,'created',v_journey.source_commit,v_run_md)",sql)
        self.assertIn("v_set.journey_id is distinct from v_task.journey_id",sql)
        self.assertIn("v_journey.execution_generation is distinct from v_generation",sql)
        self.assertIn("v_journey.binding->>'source_commit' is distinct from v_journey.source_commit",sql)
        self.assertIn("s.journey_id is not null and exists",sql)
        self.assertIn("s.journey_id is null and (",sql)
        self.assertIn("j.binding->>'integration_branch'=s.integration_branch",sql)
        self.assertIn("p.manifest->'delivery_target'->>'sha'=s.source_commit",sql)
        self.assertEqual(sql.count("SECURITY INVOKER"),2)
        self.assertIn("FROM PUBLIC,anon,authenticated",sql)
        self.assertTrue(sql.rstrip().endswith("COMMIT;"))

class JourneyV2MigrationSyntaxRegressionTests(unittest.TestCase):
    def test_complete_function_bodies(self):
        for name,count in (
            ("20261031144500_v2_routed_epoch_and_integration_binding.sql",2),
            ("20261031151500_v2_dispatch_epoch_repair.sql",1),
            ("20261031151600_v2_integration_lineage_repair.sql",1),
        ):
            sql=(ROOT/"supabase/migrations"/name).read_text()
            self.assertEqual(sql.count("CREATE OR REPLACE FUNCTION"),count)
            self.assertEqual(sql.count("$function$"),2*count)
            self.assertTrue(sql.rstrip().endswith("COMMIT;"))

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

    def test_checkpoint_requeue_requires_empty_failed_planning_and_single_use(self):
        sql = (ROOT / "supabase/migrations/20261031140000_v2_checkpoint_failure_requeue_once.sql").read_text()
        self.assertIn("verified planning checkpoint is invalid", sql)
        self.assertIn("r.metadata->'stage_evidence'->'planning'->>'status'='failed'", sql)
        self.assertIn("r.metadata->'stage_evidence'->'planning'->'output'='{}'::jsonb", sql)
        self.assertIn("jsonb_object_keys", sql)
        self.assertIn("journey.planning.checkpoint_requeued", sql)
        self.assertIn("journey.planning.preflight_requeued", sql)
        self.assertIn("metadata-'worker_id'-'claimed_at'-'error'-'stage_evidence'", sql)
        self.assertIn("WHERE id=prior AND status='failed'", sql)
        self.assertNotIn("SECURITY DEFINER", sql)

    def test_retry_event_integrity_is_bound_to_failed_run_before_metadata_cleanup(self):
        sql=(ROOT/"supabase/migrations/20261031141500_v2_recovery_retry_event_integrity.sql").read_text()
        self.assertIn("INTO retry_event",sql)
        self.assertIn("IF FOUND AND retry_event IS NOT NULL",sql)
        self.assertIn("ae.event_type=retry_event",sql)
        self.assertIn("'journey-v2-recovery',retry_event",sql)
        self.assertIn("metadata-'worker_id'-'claimed_at'-'error'-'stage_evidence'",sql)
        self.assertIn("r.metadata->'stage_evidence'->'planning'->'output'='{}'::jsonb",sql)
        self.assertIn("r.metadata#>>'{resume_checkpoint,source_run_id}'=source.id::text",sql)
        self.assertNotIn("SECURITY DEFINER",sql)
        self.assertNotIn("check_run.metadata->>'error'",sql)

    def test_preflight_requeue_is_same_run_single_use_and_fail_closed(self):
        self.assertIn("CREATE OR REPLACE FUNCTION public.factory_resume_failed_journey_v2", REQUEUE_SQL)
        self.assertIn("WHERE id=prior AND status='failed'", REQUEUE_SQL)
        self.assertIn("r.metadata->>'error'='planning_resume_provenance_preflight_failed'", REQUEUE_SQL)
        self.assertIn("NOT (r.metadata ? 'stage_evidence')", REQUEUE_SQL)
        self.assertIn("ae.event_type='journey.planning.preflight_requeued'", REQUEUE_SQL)
        self.assertIn("other.status IN ('created','queued','running')", REQUEUE_SQL)
        self.assertIn("'paid_calls',0", REQUEUE_SQL)
        self.assertIn("'requeued',true", REQUEUE_SQL)
        self.assertIn("GRANT EXECUTE ON FUNCTION public.factory_resume_failed_journey_v2(uuid) TO service_role", REQUEUE_SQL)
        self.assertNotIn("SECURITY DEFINER", REQUEUE_SQL)
        self.assertNotIn("factory_retry_failed_run", REQUEUE_SQL)

    def test_adapter_is_idempotent_and_never_calls_legacy_retry(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        q._rpc=MagicMock(return_value={"created":True,"journey_id":JOURNEY,"run_id":"new"})
        self.assertEqual(q.resume_failed_journey_v2(JOURNEY)["run_id"],"new")
        self.assertEqual(q._rpc.call_args.args[0],"factory_resume_failed_journey_v2")
        self.assertNotIn("retry",q._rpc.call_args.args[0])

    def test_recovery_scan_is_bounded_and_reports_only_control_plane_receipts(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        paths=[]
        def scan(path):
            paths.append(path)
            return [{"journey_id":JOURNEY}]
        q._get=scan
        receipts=[]
        def resume(ident):
            receipts.append(ident)
            return {"created":False,"journey_id":ident,"run_id":"existing"}
        q.resume_failed_journey_v2=resume
        result=q.recover_failed_journeys_v2()
        self.assertEqual(receipts,[JOURNEY])
        self.assertTrue(any("select=journey_id" in path for path in paths))
        self.assertEqual(result["attempted"],1)
        self.assertEqual(result["queued"],0)
        self.assertEqual(result["outcomes"][0]["journey_id"],JOURNEY)
        self.assertEqual(result["outcomes"][0]["status"],"already_queued")

    def test_recovery_scan_skips_rows_without_journey_identity(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        q._get=lambda path:[{"id":RUN}, {}, {"journey_id":JOURNEY}]
        receipts=[]
        q.resume_failed_journey_v2=lambda ident:(receipts.append(ident) or {"created":True,"run_id":"new"})
        result=q.recover_failed_journeys_v2()
        self.assertEqual(receipts,[JOURNEY])
        self.assertEqual(result["attempted"],1)
        self.assertEqual(result["queued"],1)

    def test_public_claim_recovers_journey_id_from_the_claimed_row(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        q._rpc=lambda *_: {"run_id":"new","task_id":TASK,"project_id":PROJECT,"project_key":"crm-infodive","stages":["planning"],"execution_generation":16,"context":{"manifest":{"journey_delivery_binding_v2":{}}}}
        seen=[]
        def get(path):
            seen.append(path)
            if path.startswith("factory_runs?select=journey_id&id=eq.new"): return [{"journey_id":JOURNEY}]
            if path.startswith("factory_projects?"): return [{"repository":"leandrosilveiradepaula/crm-infodive"}]
            if path.startswith("factory_journeys?"): return [{"id":JOURNEY,"project_id":PROJECT,"request_id":"request","request_digest":"d"*64,"state":"executing","execution_generation":16,"request_snapshot":{"text":"work","digest":"d"*64},"binding":{"journey_id":JOURNEY,"project_id":PROJECT,"request_id":"request","execution_generation":16,"policy_version":2,"policy_digest":"a"*64,"repository":"leandrosilveiradepaula/crm-infodive","source_commit":SHA,"source_ref":"main","source_mode":"main_snapshot","integration_branch":"factory/journey-"+JOURNEY,"preview_base_ref":"main","release_base_ref":"main","binding_version":2}}]
            if path.startswith("factory_runs?select=id,task_id,journey_id,status,metadata&id=eq.new"): return [{"id":"new","task_id":TASK,"journey_id":JOURNEY,"status":"running","metadata":{}}]
            raise AssertionError(path)
        q._get=get
        # Ordinary planning without a checkpoint returns after V2 identity hydration.
        item=q.claim_next("worker")
        self.assertEqual(item.journey_id,JOURNEY)
        self.assertTrue(any("journey_id,status,metadata" in path for path in seen))

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
        metadata={"stages":["planning"],"execution_generation":16}
        source={"id":RUN,"task_id":TASK,"journey_id":JOURNEY,"status":"failed","execution_route":"direct","source_commit":SHA,
          "metadata":{"error":"planning has no actionable tasks or decisions","stages":["reconciliation","gap_analysis","planning"],"execution_generation":16,
            "stage_evidence":{"reconciliation":{"output":checkpoint["reconciliation"]},"gap_analysis":{"output":checkpoint["gap_analysis"]}}}}
        q._get=lambda path:[source]
        context=q._v2_planning_resume_context("new",TASK,PROJECT,16,original,claimed,metadata,checkpoint)
        self.assertEqual(context["_verified_resume_prior_stages"]["gap_analysis"],checkpoint["gap_analysis"])
        with self.assertRaisesRegex(PermissionError,"checkpoint identity"):
            q._v2_planning_resume_context("new",TASK,PROJECT,16,original,{"journey_id":"22222222-2222-4222-8222-222222222222"},metadata,checkpoint)
        checkpoint["generation"]=17
        with self.assertRaisesRegex(PermissionError,"checkpoint identity"):
            q._v2_planning_resume_context("new",TASK,PROJECT,16,original,claimed,metadata,checkpoint)

if __name__=="__main__": unittest.main()
