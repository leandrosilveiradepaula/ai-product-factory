import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock,patch

from ai_product_factory.product_stage_executor import ProductStageExecutor
from ai_product_factory.runtime_auth import AuthKind
from ai_product_factory.runtime_cli import build_handler, require_codex_runtime_enabled, require_paid_runtime_budget, require_primary_runtime_enabled, run_alerts_once, run_ci_once, run_codex_once, run_direct_once, run_health_once, run_product_once, run_release_once, run_preview_once, run_preview_probe_once, run_dispatch_once, run_specialist_once, run_replay_once, run_replan_once, run_retry_once, run_recovery_once


class RuntimeCliTests(unittest.TestCase):
    def test_runtime_builds_primary_handler_for_api_key(self):
        scheduler=MagicMock();scheduler.profiles.return_value=()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test","FACTORY_PRIMARY_MODEL_ENABLED":"true"}, clear=True), \
             patch("ai_product_factory.runtime_cli.SupabaseAgentScheduler",return_value=scheduler):
            handler = build_handler()
        self.assertIsInstance(handler, ProductStageExecutor)
        scheduler.profiles.assert_called_once()

    def test_primary_runtime_flag_is_required_intrinsically(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY":"test"}, clear=True):
            with self.assertRaises(PermissionError):
                require_primary_runtime_enabled()

    def test_product_blocks_before_queue_when_primary_flag_is_off(self):
        env={"OPENAI_API_KEY":"test","FACTORY_MODEL_BUDGET_USD":"5","FACTORY_MODEL_RESERVE_USD":"0.25"}
        with patch.dict("os.environ",env,clear=True), patch("ai_product_factory.runtime_cli.SupabaseRuntimeQueue") as queue:
            out=run_product_once("w")
        self.assertEqual(out["status"],"blocked")
        queue.assert_not_called()

    def test_direct_blocks_before_claim_when_primary_flag_is_off(self):
        env={"OPENAI_API_KEY":"test","FACTORY_MODEL_BUDGET_USD":"5","FACTORY_MODEL_RESERVE_USD":"0.25"}
        with patch.dict("os.environ",env,clear=True), patch("ai_product_factory.runtime_cli.SupabaseDirectRunQueue") as queue:
            out=run_direct_once("w")
        self.assertEqual(out["status"],"blocked")
        queue.assert_not_called()
    def test_codex_blocks_before_claim_when_not_explicitly_enabled(self):
        env={"OPENAI_FEDERATION_RULE_ID":"rule","OPENAI_WIF_AUDIENCE":"aud","OPENAI_IDENTITY_TOKEN_FILE":"/tmp/missing","FACTORY_GITHUB_TOKEN":"gh"}
        with patch.dict("os.environ",env,clear=True), patch("ai_product_factory.runtime_cli.SupabaseCodexRunQueue") as queue:
            out=run_codex_once("w")
        self.assertEqual(out["status"],"blocked")
        queue.assert_not_called()

    def test_codex_runtime_requires_cross_repo_credential(self):
        import tempfile
        with tempfile.NamedTemporaryFile() as identity:
            env={
                "FACTORY_CODEX_ENABLED":"true",
                "OPENAI_FEDERATION_RULE_ID":"rule",
                "OPENAI_WIF_AUDIENCE":"aud",
                "OPENAI_IDENTITY_TOKEN_FILE":identity.name,
            }
            with patch.dict("os.environ",env,clear=True):
                with self.assertRaises(PermissionError) as ctx:
                    require_codex_runtime_enabled()
        self.assertIn("FACTORY_GITHUB_TOKEN",str(ctx.exception))

    def test_codex_empty_queue_has_no_github_or_cli_side_effect(self):
        import tempfile
        with tempfile.NamedTemporaryFile() as identity:
            env={
                "FACTORY_CODEX_ENABLED":"true",
                "OPENAI_FEDERATION_RULE_ID":"rule",
                "OPENAI_WIF_AUDIENCE":"aud",
                "OPENAI_IDENTITY_TOKEN_FILE":identity.name,
                "FACTORY_GITHUB_TOKEN":"factory-gh",
            }
            queue=MagicMock();queue.claim_next.return_value=None
            with patch.dict("os.environ",env,clear=True), \
                 patch("ai_product_factory.runtime_cli.SupabaseAgentScheduler") as scheduler, \
                 patch("ai_product_factory.runtime_cli.SupabaseCodexRunQueue",return_value=queue), \
                 patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github, \
                 patch("ai_product_factory.runtime_cli.CodexCLIProducer") as producer:
                out=run_codex_once("w")
        self.assertEqual(out,{"claimed":False,"status":"empty"})
        github.assert_not_called()
        producer.assert_not_called()


    def test_exact_direct_run_does_not_schedule_unrelated_work(self):
        scheduler=MagicMock()
        queue=MagicMock();queue.claim_next.return_value=None
        auth=MagicMock();auth.resolve_primary_api.return_value=SimpleNamespace(kind=AuthKind.OPENAI_API_KEY)
        with patch("ai_product_factory.runtime_cli.require_primary_runtime_enabled"), \
             patch("ai_product_factory.runtime_cli.require_paid_runtime_budget"), \
             patch("ai_product_factory.runtime_cli.RuntimeAuthResolver",return_value=auth), \
             patch("ai_product_factory.runtime_cli.SupabaseAgentScheduler",return_value=scheduler), \
             patch("ai_product_factory.runtime_cli.SupabaseDirectRunQueue",return_value=queue):
            out=run_direct_once("worker","development","run-1")
        self.assertEqual(out,{"claimed":False,"status":"empty"})
        scheduler.schedule_next.assert_not_called()
        scheduler.require_route_tools.assert_called_once_with("development","direct")
        queue.claim_next.assert_called_once_with("worker","development","run-1")

    def test_exact_codex_run_does_not_schedule_unrelated_work(self):
        scheduler=MagicMock()
        queue=MagicMock();queue.claim_next.return_value=None
        with patch("ai_product_factory.runtime_cli.require_codex_runtime_enabled"), \
             patch("ai_product_factory.runtime_cli.SupabaseAgentScheduler",return_value=scheduler), \
             patch("ai_product_factory.runtime_cli.SupabaseCodexRunQueue",return_value=queue):
            out=run_codex_once("worker","development","run-2")
        self.assertEqual(out,{"claimed":False,"status":"empty"})
        scheduler.schedule_next.assert_not_called()
        scheduler.require_route_tools.assert_called_once_with("development","codex")
        queue.claim_next.assert_called_once_with("worker","development","run-2")

    def test_runtime_fails_before_claim_when_auth_is_missing(self):
        with patch.dict("os.environ", {"FACTORY_PRIMARY_MODEL_ENABLED":"true"}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                build_handler()
        self.assertIn(AuthKind.NONE.value, str(ctx.exception))

    def test_unofficial_chatgpt_token_is_ignored_by_primary_runtime(self):
        with patch.dict("os.environ", {"CHATGPT_ACCESS_TOKEN": "x","FACTORY_PRIMARY_MODEL_ENABLED":"true"}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                build_handler()
        self.assertIn(AuthKind.NONE.value, str(ctx.exception))

    def test_paid_runtime_budget_is_fail_closed_when_unconfigured(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(PermissionError):
                require_paid_runtime_budget()

    def test_paid_runtime_budget_accepts_ledger_known_spend(self):
        env={"FACTORY_MODEL_BUDGET_USD":"5","FACTORY_MODEL_RESERVE_USD":"0.25"}
        reader=MagicMock()
        reader.read.return_value=SimpleNamespace(known_cost=Decimal("1"),unknown_cost_events=0)
        with patch.dict("os.environ", env, clear=True):
            require_paid_runtime_budget(health_reader=reader)
        reader.read.assert_called_once()

    def test_paid_runtime_budget_blocks_unknown_paid_cost(self):
        env={"FACTORY_MODEL_BUDGET_USD":"5","FACTORY_MODEL_RESERVE_USD":"0.25"}
        reader=MagicMock()
        reader.read.return_value=SimpleNamespace(known_cost=Decimal("1"),unknown_cost_events=1)
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaises(PermissionError):
                require_paid_runtime_budget(health_reader=reader)

    def test_paid_runtime_budget_blocks_when_ledger_exhausts_budget(self):
        env={"FACTORY_MODEL_BUDGET_USD":"5","FACTORY_MODEL_RESERVE_USD":"0.25"}
        reader=MagicMock()
        reader.read.return_value=SimpleNamespace(known_cost=Decimal("4.9"),unknown_cost_events=0)
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaises(PermissionError):
                require_paid_runtime_budget(health_reader=reader)




    def test_recovery_resumes_decisions_without_model_calls(self):
        queue=MagicMock()
        queue.recover_expired.return_value={"requeued":0,"failed":0}
        queue.resume_resolved_decisions.return_value={"created":1,"existing":0,"blocked":0}
        agents=MagicMock();agents.recover_expired.return_value={"requeued":0}
        lanes=MagicMock();lanes.recover_expired.return_value={"requeued":0}
        change_sets=MagicMock();change_sets.recover_expired.return_value={"requeued":0}
        with patch("ai_product_factory.runtime_cli.SupabaseRuntimeQueue",return_value=queue), \
             patch("ai_product_factory.runtime_cli.SupabaseAgentScheduler",return_value=agents), \
             patch("ai_product_factory.runtime_cli.SupabaseSpecialistLaneQueue",return_value=lanes), \
             patch("ai_product_factory.runtime_cli.SupabaseChangeSetStore",return_value=change_sets), \
             patch("ai_product_factory.runtime_cli.OpenAIResponsesProvider") as provider:
            out=run_recovery_once(3)
        self.assertEqual(out["decisions"]["created"],1)
        queue.recover_expired.assert_called_once_with(3)
        queue.resume_resolved_decisions.assert_called_once_with()
        provider.assert_not_called()

    def test_retry_mode_is_model_free_and_delegates_to_queue(self):
        queue=MagicMock()
        queue.retry_failed_run.return_value={"source_run_id":"old","run_id":"new","status":"queued"}
        with patch("ai_product_factory.runtime_cli.SupabaseRuntimeQueue",return_value=queue), \
             patch("ai_product_factory.runtime_cli.OpenAIResponsesProvider") as provider:
            out=run_retry_once("old","fixed root cause")
        self.assertEqual(out["run_id"],"new")
        queue.retry_failed_run.assert_called_once_with("old","fixed root cause")
        provider.assert_not_called()

    def test_retry_mode_requires_source_and_reason(self):
        with self.assertRaises(ValueError):run_retry_once("","reason")
        with self.assertRaises(ValueError):run_retry_once("old"," ")

    def test_replan_mode_reuses_persisted_plan_without_model_call(self):
        queue=MagicMock()
        queue.rebuild_team_plan.return_value={"status":"ready","team_plan_id":"tp","change_set":{"change_set_id":"cs"}}
        scheduler=MagicMock()
        profiles=(SimpleNamespace(agent_key="development"),)
        scheduler.profiles.return_value=profiles
        with patch("ai_product_factory.runtime_cli.SupabaseRuntimeQueue",return_value=queue), \
             patch("ai_product_factory.runtime_cli.SupabaseAgentScheduler",return_value=scheduler), \
             patch("ai_product_factory.runtime_cli.OpenAIResponsesProvider") as provider:
            out=run_replan_once("run-1")
        self.assertEqual(out["status"],"ready")
        queue.rebuild_team_plan.assert_called_once_with("run-1",profiles)
        provider.assert_not_called()

    def test_replay_mode_is_zero_effect_and_model_free(self):
        store=MagicMock()
        store.create_replay.return_value=SimpleNamespace(
            replay_id="rp",source_run_id="run",mode="shadow",status="ready",
            effect="none",model_calls_allowed=False,snapshot_hash="a"*64,
        )
        with patch("ai_product_factory.runtime_cli.SupabaseProvenanceStore",return_value=store):
            out=run_replay_once("run","shadow")
        self.assertEqual(out["effect"],"none")
        self.assertFalse(out["model_calls_allowed"])
        store.create_replay.assert_called_once_with("run","shadow")

    def test_health_is_side_effect_free_configuration_report(self):
        with patch.dict("os.environ", {"SUPABASE_URL":"https://example.supabase.co","SUPABASE_SERVICE_ROLE_KEY":"secret"}, clear=True):
            out=run_health_once()
        self.assertEqual(out["status"],"healthy")
        self.assertTrue(out["control_plane_configured"])
        self.assertFalse(out["primary_enabled"])
        self.assertFalse(out["budget_configured"])
        self.assertFalse(out["vercel_preview_api"]["ready"])
        self.assertFalse(out["vercel_preview_github"]["ready"])
        self.assertFalse(out["github_alerts"]["ready"])

    def test_ci_followup_empty_queue_has_no_github_side_effect(self):
        queue=MagicMock()
        queue.next_pending.return_value=None
        with patch("ai_product_factory.runtime_cli.SupabaseCIFollowupQueue",return_value=queue), patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github:
            out=run_ci_once()
        self.assertEqual(out,{"claimed":False,"status":"empty"})
        github.assert_not_called()

    def test_green_ci_persists_quality_gate_evidence(self):
        item=SimpleNamespace(
            repository="owner/repo",issue_number=7,pr_number=9,candidate_commit="abc",
            branch="factory/t",run_id="r",human_gate_required=False,
        )
        queue=MagicMock();queue.next_pending.return_value=item
        github=MagicMock()
        github.get_issue.return_value=SimpleNamespace(number=7)
        github.get_pull_request.return_value=SimpleNamespace(number=9,head_sha="abc")
        store=MagicMock()
        loop=MagicMock()
        loop.evaluate.return_value=SimpleNamespace(
            action=SimpleNamespace(value="preview_ready"),
            ci_state=SimpleNamespace(value="success"),
        )
        lanes=MagicMock();lanes.enqueue.return_value={"status":"specialist_review_pending","roles":["security","qa"]}
        trace=MagicMock()
        with patch("ai_product_factory.runtime_cli.SupabaseCIFollowupQueue",return_value=queue), \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter",return_value=github), \
             patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore",return_value=store), \
             patch("ai_product_factory.runtime_cli.SupabaseSpecialistLaneQueue",return_value=lanes), \
             patch("ai_product_factory.runtime_cli.SupabaseTraceabilityStore",return_value=trace), \
             patch("ai_product_factory.runtime_cli.AutonomousGitHubLoop",return_value=loop):
            out=run_ci_once()
        self.assertEqual(out["status"],"specialist_review_pending")
        lanes.enqueue.assert_called_once_with("r")
        trace.record_delivery_evidence.assert_called_once()
        self.assertEqual(trace.record_delivery_evidence.call_args.kwargs["evidence_type"],"github_ci")
        store.record_evaluation.assert_called_once()
        kwargs=store.record_evaluation.call_args.kwargs
        self.assertEqual(kwargs["eval_type"],"quality_gate")
        self.assertEqual(kwargs["baseline_ref"],"abc")
        self.assertEqual(kwargs["status"],"success")



    def test_specialist_empty_queue_has_no_github_side_effect(self):
        queue=MagicMock();queue.claim.return_value=None
        with patch("ai_product_factory.runtime_cli.SupabaseSpecialistLaneQueue",return_value=queue), \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github:
            out=run_specialist_once("security","worker")
        self.assertEqual(out,{"claimed":False,"status":"empty","role":"security"})
        github.assert_not_called()

    def test_specialist_persists_deterministic_result(self):
        item=SimpleNamespace(job_id="j",run_id="r",repository="owner/repo",role="qa",candidate_commit="abc")
        queue=MagicMock();queue.claim.return_value=item;queue.complete.return_value={"run_status":"preview_ready"}
        result=SimpleNamespace(status="passed",findings=(),evidence={"model_call":False})
        trace=MagicMock()
        with patch("ai_product_factory.runtime_cli.SupabaseSpecialistLaneQueue",return_value=queue), \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github_cls, \
             patch("ai_product_factory.runtime_cli.SupabaseTraceabilityStore",return_value=trace), \
             patch("ai_product_factory.runtime_cli.evaluate_specialist_lane",return_value=result) as evaluate:
            out=run_specialist_once("qa","worker")
        self.assertEqual(out["status"],"passed")
        self.assertEqual(out["run_status"],"preview_ready")
        evaluate.assert_called_once()
        queue.complete.assert_called_once_with(item,status="passed",findings=[],evidence={"model_call":False})
        self.assertEqual(trace.record_delivery_evidence.call_args.kwargs["evidence_type"],"qa")
        self.assertEqual(trace.record_delivery_evidence.call_args.kwargs["evidence_ref"],"abc")

    def test_preview_probe_empty_has_no_github_side_effect(self):
        queue=MagicMock();queue.next_pending.return_value=None
        with patch("ai_product_factory.runtime_cli.SupabasePreviewFollowupQueue",return_value=queue), patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github:
            out=run_preview_probe_once()
        self.assertEqual(out["status"],"empty")
        self.assertFalse(out["preview_required"])
        github.assert_not_called()

    def test_preview_probe_reports_non_applicable_without_external_readiness(self):
        item=SimpleNamespace(run_id="r",repository="owner/repo",manifest={"preview":{"required":False,"reason":"backend only"}},pr_number=9,candidate_commit="abc")
        queue=MagicMock();queue.next_pending.return_value=item
        github=MagicMock();github.get_pull_request.return_value=SimpleNamespace(head_sha="abc");github.get_pull_request_files.return_value=("src/core.py",)
        with patch("ai_product_factory.runtime_cli.SupabasePreviewFollowupQueue",return_value=queue), patch("ai_product_factory.runtime_cli.GitHubRestAdapter",return_value=github):
            out=run_preview_probe_once()
        self.assertEqual(out["status"],"ready")
        self.assertFalse(out["preview_required"])

    def test_dispatch_without_project_uses_global_selector(self):
        dispatch=MagicMock()
        dispatch.dispatch_next_any.return_value=None
        scheduler=MagicMock()
        adaptive=MagicMock();adaptive.work_matrix.return_value={"direct":[],"codex":[],"decisions":[]}
        with patch("ai_product_factory.runtime_cli.SupabaseBacklogDispatch",return_value=dispatch), \
             patch("ai_product_factory.runtime_cli.SupabaseAgentScheduler",return_value=scheduler), \
             patch("ai_product_factory.runtime_cli.SupabaseAdaptiveConcurrencyController",return_value=adaptive):
            out=run_dispatch_once()
        self.assertEqual(out["status"],"empty")
        dispatch.dispatch_next_any.assert_called_once()
        adaptive.work_matrix.assert_called_once()

    def test_preview_mode_empty_queue_does_not_require_external_readiness(self):
        queue=MagicMock();queue.next_pending.return_value=None
        with patch.dict("os.environ", {}, clear=True), patch("ai_product_factory.runtime_cli.SupabasePreviewFollowupQueue",return_value=queue), patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github:
            out=run_preview_once()
        self.assertEqual(out,{"claimed":False,"status":"empty"})
        github.assert_not_called()

    def test_preview_not_required_bypasses_external_preview_credentials(self):
        item=SimpleNamespace(run_id="r",project_key="demo",repository="owner/repo",manifest={"preview":{"required":False,"reason":"backend only"}},issue_number=7,branch="factory/t",pr_number=9,candidate_commit="abc")
        queue=MagicMock();queue.next_pending.return_value=item
        github=MagicMock();github.get_issue.return_value=SimpleNamespace(number=7);github.get_pull_request.return_value=SimpleNamespace(number=9,head_sha="abc");github.get_pull_request_files.return_value=("src/core.py",)
        loop=MagicMock();loop.finalize_preview_not_required.return_value="awaiting_release"
        with patch.dict("os.environ",{},clear=True), \
             patch("ai_product_factory.runtime_cli.SupabasePreviewFollowupQueue",return_value=queue), \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter",return_value=github), \
             patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore",return_value=MagicMock()), \
             patch("ai_product_factory.runtime_cli._assess_release_policy",return_value=(SimpleNamespace(decision=SimpleNamespace(blocked=False,reasons=())),{"report_id":"report"})), \
             patch("ai_product_factory.runtime_cli.AutonomousGitHubLoop",return_value=loop), \
             patch("ai_product_factory.runtime_cli.VercelPreviewAdapter") as vercel:
            out=run_preview_once()
        self.assertEqual(out["status"],"awaiting_release")
        self.assertFalse(out["preview_required"])
        self.assertEqual(out["reason"],"backend only")
        loop.finalize_preview_not_required.assert_called_once()
        vercel.assert_not_called()

    def test_release_policy_block_prevents_awaiting_release_after_preview(self):
        item=SimpleNamespace(run_id="r",project_key="demo",repository="owner/repo",manifest={"preview":{"required":False,"reason":"backend only"}},issue_number=7,branch="factory/t",pr_number=9,candidate_commit="abc",risk={})
        queue=MagicMock();queue.next_pending.return_value=item
        github=MagicMock();github.get_issue.return_value=SimpleNamespace(number=7);github.get_pull_request.return_value=SimpleNamespace(number=9,head_sha="abc");github.get_pull_request_files.return_value=("src/core.py",)
        loop=MagicMock();loop.finalize_preview_not_required.return_value="awaiting_release"
        decision=SimpleNamespace(blocked=True,reasons=("missing Definition of Done checks: qa",))
        with patch("ai_product_factory.runtime_cli.SupabasePreviewFollowupQueue",return_value=queue), \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter",return_value=github), \
             patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore",return_value=MagicMock()), \
             patch("ai_product_factory.runtime_cli._assess_release_policy",return_value=(SimpleNamespace(decision=decision),{"report_id":"report"})), \
             patch("ai_product_factory.runtime_cli.AutonomousGitHubLoop",return_value=loop):
            out=run_preview_once()
        self.assertEqual(out["status"],"release_policy_blocked")
        self.assertIn("qa",out["policy_reasons"][0])
        loop.finalize_preview_not_required.assert_not_called()

    def test_preview_mode_wires_verified_preview_and_stops_at_release_gate(self):
        item=SimpleNamespace(run_id="r",project_key="demo",repository="owner/repo",manifest={"preview":{"team_id":"team","project_name":"web"}},issue_number=7,branch="factory/t",pr_number=9,candidate_commit="abc")
        queue=MagicMock();queue.next_pending.return_value=item
        github=MagicMock();github.get_issue.return_value=SimpleNamespace(number=7);github.get_pull_request.return_value=SimpleNamespace(number=9,head_sha="abc");github.get_pull_request_files.return_value=("apps/console/app/page.tsx",)
        verified=SimpleNamespace(deployment=SimpleNamespace(preview_url="https://preview.example",deployment_ref="dep-1"))
        coordinator=MagicMock();coordinator.execute.return_value=verified
        loop=MagicMock();loop.finalize_verified_preview.return_value="awaiting_release"
        env={
            "FACTORY_VERCEL_PREVIEW_ENABLED":"true","VERCEL_TOKEN":"token",
            "FACTORY_BROWSER_EVIDENCE_ENABLED":"true","FACTORY_BROWSER_EVIDENCE_COMMAND_JSON":'["verify"]',
        }
        with patch.dict("os.environ",env,clear=True), \
             patch("ai_product_factory.runtime_cli.SupabasePreviewFollowupQueue",return_value=queue), \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter",return_value=github), \
             patch("ai_product_factory.runtime_cli.VercelPreviewAdapter"), \
             patch("ai_product_factory.runtime_cli.DurablePreviewAdapter"), \
             patch("ai_product_factory.runtime_cli.SupabaseDeploymentEvidenceStore"), \
             patch("ai_product_factory.runtime_cli.CommandBrowserEvidenceConfig.from_env",return_value=MagicMock()), \
             patch("ai_product_factory.runtime_cli.CommandBrowserEvidenceAdapter"), \
             patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore",return_value=MagicMock()), \
             patch("ai_product_factory.runtime_cli.BrowserEvidenceRecorder"), \
             patch("ai_product_factory.runtime_cli.VerifiedPreviewCoordinator",return_value=coordinator), \
             patch("ai_product_factory.runtime_cli.SupabaseTraceabilityStore",return_value=MagicMock()), \
             patch("ai_product_factory.runtime_cli._assess_release_policy",return_value=(SimpleNamespace(decision=SimpleNamespace(blocked=False,reasons=())),{"report_id":"report"})), \
             patch("ai_product_factory.runtime_cli.AutonomousGitHubLoop",return_value=loop):
            out=run_preview_once()
        self.assertEqual(out["status"],"awaiting_release")
        self.assertTrue(out["preview_required"])
        self.assertEqual(out["preview_url"],"https://preview.example")
        loop.finalize_verified_preview.assert_called_once()


    def test_github_integrated_preview_needs_no_vercel_token(self):
        item=SimpleNamespace(run_id="r",project_key="demo",repository="owner/repo",manifest={"preview":{"provider":"vercel","mode":"github"}},issue_number=7,branch="factory/t",pr_number=9,candidate_commit="abc")
        queue=MagicMock();queue.next_pending.return_value=item
        github=MagicMock();github.get_issue.return_value=SimpleNamespace(number=7);github.get_pull_request.return_value=SimpleNamespace(number=9,head_sha="abc");github.get_pull_request_files.return_value=("web/page.tsx",)
        verified=SimpleNamespace(deployment=SimpleNamespace(preview_url="https://preview.example",deployment_ref="check-1"))
        coordinator=MagicMock();coordinator.execute.return_value=verified
        loop=MagicMock();loop.finalize_verified_preview.return_value="awaiting_release"
        env={
            "FACTORY_VERCEL_PREVIEW_ENABLED":"true","GITHUB_TOKEN":"gh",
            "FACTORY_BROWSER_EVIDENCE_ENABLED":"true","FACTORY_BROWSER_EVIDENCE_COMMAND_JSON":'["verify"]',
        }
        with patch.dict("os.environ",env,clear=True), \
             patch("ai_product_factory.runtime_cli.SupabasePreviewFollowupQueue",return_value=queue), \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter",return_value=github), \
             patch("ai_product_factory.runtime_cli.GitHubVercelPreviewAdapter") as github_vercel, \
             patch("ai_product_factory.runtime_cli.DurablePreviewAdapter"), \
             patch("ai_product_factory.runtime_cli.SupabaseDeploymentEvidenceStore"), \
             patch("ai_product_factory.runtime_cli.CommandBrowserEvidenceConfig.from_env",return_value=MagicMock()), \
             patch("ai_product_factory.runtime_cli.CommandBrowserEvidenceAdapter"), \
             patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore",return_value=MagicMock()), \
             patch("ai_product_factory.runtime_cli.BrowserEvidenceRecorder"), \
             patch("ai_product_factory.runtime_cli.VerifiedPreviewCoordinator",return_value=coordinator), \
             patch("ai_product_factory.runtime_cli.SupabaseTraceabilityStore",return_value=MagicMock()), \
             patch("ai_product_factory.runtime_cli._assess_release_policy",return_value=(SimpleNamespace(decision=SimpleNamespace(blocked=False,reasons=())),{"report_id":"report"})), \
             patch("ai_product_factory.runtime_cli.AutonomousGitHubLoop",return_value=loop):
            out=run_preview_once()
        self.assertEqual(out["status"],"awaiting_release")
        github_vercel.assert_called_once()
        self.assertNotIn("VERCEL_TOKEN",env)

    def test_release_followup_empty_queue_has_no_github_side_effect(self):
        queue=MagicMock()
        queue.next_pending.return_value=None
        with patch("ai_product_factory.runtime_cli.SupabaseReleaseFollowupQueue",return_value=queue), patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github:
            out=run_release_once()
        self.assertEqual(out,{"claimed":False,"status":"empty"})
        github.assert_not_called()

    def test_release_followup_observes_human_merge_without_merging(self):
        item=SimpleNamespace(repository="owner/repo",issue_number=7,pr_number=9,candidate_commit="abc",branch="factory/t",run_id="r")
        queue=MagicMock();queue.next_pending.return_value=item
        github=MagicMock()
        issue=SimpleNamespace(number=7)
        pr=SimpleNamespace(number=9,head_sha="abc")
        github.get_issue.return_value=issue
        github.get_pull_request.return_value=pr
        store=MagicMock();trace=MagicMock();policy=MagicMock();change_sets=MagicMock()
        change_sets.finalize_released_run.return_value={"matched":True,"change_set_id":"cs","status":"completed","idempotent":False}
        loop=MagicMock();loop.observe_manual_merge.return_value="merge123"
        with patch("ai_product_factory.runtime_cli.SupabaseReleaseFollowupQueue",return_value=queue), \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter",return_value=github), \
             patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore",return_value=store), \
             patch("ai_product_factory.runtime_cli.AutonomousGitHubLoop",return_value=loop), \
             patch("ai_product_factory.runtime_cli.SupabaseTraceabilityStore",return_value=trace), \
             patch("ai_product_factory.runtime_cli.SupabaseReleasePolicyStore",return_value=policy), \
             patch("ai_product_factory.runtime_cli.SupabaseChangeSetStore",return_value=change_sets), \
             patch("ai_product_factory.runtime_cli.SupabaseAgentScheduler") as scheduler:
            out=run_release_once()
        self.assertEqual(out["status"],"merged")
        self.assertEqual(out["merge_sha"],"merge123")
        self.assertEqual(out["change_set"]["status"],"completed")
        self.assertEqual(trace.record_delivery_evidence.call_args.kwargs["evidence_type"],"human_release")
        policy.mark_released.assert_called_once_with("r","merge123")
        change_sets.finalize_released_run.assert_called_once_with("r","merge123")
        github.merge_pull_request.assert_not_called()
    def test_direct_failure_releases_agent_assignment_and_scope(self):
        item=SimpleNamespace(run_id="r",task_id="t",project_key="demo",repository="owner/repo",issue_number=None,title="x",description="",branch="factory/development/task-t",human_gate_required=False)
        scheduler=MagicMock()
        queue=MagicMock();queue.claim_next.return_value=item
        worker=MagicMock();worker.execute.side_effect=RuntimeError("implementation failed")
        auth=SimpleNamespace(kind=AuthKind.OPENAI_API_KEY)
        with patch("ai_product_factory.runtime_cli.require_primary_runtime_enabled"), \
             patch("ai_product_factory.runtime_cli.RuntimeAuthResolver") as resolver, \
             patch("ai_product_factory.runtime_cli.require_paid_runtime_budget"), \
             patch("ai_product_factory.runtime_cli.SupabaseAgentScheduler",return_value=scheduler), \
             patch("ai_product_factory.runtime_cli.SupabaseDirectRunQueue",return_value=queue), \
             patch("ai_product_factory.runtime_cli.DirectExecutionWorker",return_value=worker), \
             patch("ai_product_factory.runtime_cli.ModelImplementationProducer"), \
             patch("ai_product_factory.runtime_cli.OpenAIResponsesProvider"), \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter"), \
             patch("ai_product_factory.runtime_cli.AutonomousGitHubLoop"), \
             patch("ai_product_factory.runtime_cli.GitHubIssueMaterializer"), \
             patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore"), \
             patch("ai_product_factory.runtime_cli.SupabaseIssueBindingStore"):
            resolver.return_value.resolve_primary_api.return_value=auth
            with self.assertRaisesRegex(RuntimeError,"implementation failed"):
                run_direct_once("w")
        scheduler.release.assert_called_once_with("r","blocked")

    def test_codex_failure_releases_agent_assignment_and_scope(self):
        item=SimpleNamespace(run_id="r",task_id="t",project_key="demo",repository="owner/repo",issue_number=None,title="x",description="",branch="factory/development/task-t",codex_level=2,human_gate_required=False)
        scheduler=MagicMock()
        queue=MagicMock();queue.claim_next.return_value=item
        worker=MagicMock();worker.execute.side_effect=RuntimeError("codex failed")
        with patch("ai_product_factory.runtime_cli.require_codex_runtime_enabled"), \
             patch("ai_product_factory.runtime_cli.SupabaseAgentScheduler",return_value=scheduler), \
             patch("ai_product_factory.runtime_cli.SupabaseCodexRunQueue",return_value=queue), \
             patch("ai_product_factory.runtime_cli.DirectExecutionWorker",return_value=worker), \
             patch("ai_product_factory.runtime_cli.CodexCLIProducer"), \
             patch("ai_product_factory.runtime_cli.SupabaseCodexUsageRecorder"), \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter"), \
             patch("ai_product_factory.runtime_cli.AutonomousGitHubLoop"), \
             patch("ai_product_factory.runtime_cli.GitHubIssueMaterializer"), \
             patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore"), \
             patch("ai_product_factory.runtime_cli.SupabaseIssueBindingStore"):
            with self.assertRaisesRegex(RuntimeError,"codex failed"):
                run_codex_once("w")
        scheduler.release.assert_called_once_with("r","blocked")

    def test_alert_mode_is_blocked_without_explicit_enable_and_config(self):
        with patch.dict("os.environ", {}, clear=True):
            out=run_alerts_once()
        self.assertEqual(out["status"],"blocked")
        self.assertEqual(out["published"],0)
        self.assertIn("GITHUB_TOKEN",out["missing"])

    def test_alert_mode_reconciles_resolved_issues_when_health_is_clean(self):
        readiness=SimpleNamespace(ready=True,missing=())
        reader=MagicMock()
        reader.read.return_value=object()
        adapter=MagicMock()
        adapter.publish_many.return_value=()
        adapter.resolve_inactive.return_value=(SimpleNamespace(code="failed_runs",issue_number=61),)
        with patch.dict("os.environ", {"FACTORY_ALERTS_GITHUB_REPOSITORY":"owner/repo"}, clear=True), \
             patch("ai_product_factory.runtime_cli.github_alerts_readiness",return_value=readiness), \
             patch("ai_product_factory.runtime_cli.SupabaseOperationalHealthReader",return_value=reader), \
             patch("ai_product_factory.runtime_cli.evaluate_operational_alerts",return_value=()), \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter"), \
             patch("ai_product_factory.runtime_cli.GitHubIssueAlertAdapter",return_value=adapter):
            out=run_alerts_once()
        self.assertEqual(out["status"],"ok")
        self.assertEqual(out["published"],0)
        self.assertEqual(out["resolved"],1)
        self.assertEqual(out["resolutions"],[{"code":"failed_runs","issue_number":61}])
        adapter.publish_many.assert_called_once_with(())
        called=adapter.resolve_inactive.call_args.kwargs
        self.assertEqual(called["active_codes"],set())
        self.assertIn("failed_runs",called["known_codes"])

    def test_health_recognizes_modern_supabase_secret_key(self):
        env={"SUPABASE_URL":"https://example.supabase.co","SUPABASE_SECRET_KEY":"sb_secret_modern"}
        with patch.dict("os.environ", env, clear=True):
            out=run_health_once()
        self.assertTrue(out["control_plane_configured"])

if __name__ == "__main__":
    unittest.main()
