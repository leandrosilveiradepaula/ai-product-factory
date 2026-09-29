from __future__ import annotations

from pathlib import Path
import re
import unittest

from ai_product_factory.models import (
    Complexity,
    ExecutionRoute,
    LifecycleStage,
    ProjectState,
    RiskProfile,
    TaskProfile,
)
from ai_product_factory.orchestrator import decide_execution
from ai_product_factory.preview_policy import evaluate_preview_applicability
from ai_product_factory.state_machine import transition


ROOT = Path(__file__).resolve().parents[1]


class FactoryAcceptanceTests(unittest.TestCase):
    def test_lifecycle_covers_product_factory_chain(self):
        expected = {
            LifecycleStage.DISCOVERY,
            LifecycleStage.SPECIFICATION,
            LifecycleStage.PLANNING,
            LifecycleStage.IMPLEMENTATION,
            LifecycleStage.REVIEW,
            LifecycleStage.VALIDATION,
            LifecycleStage.PREVIEW,
            LifecycleStage.HUMAN_GATE,
            LifecycleStage.RELEASE,
            LifecycleStage.OPERATIONS,
        }
        self.assertTrue(expected.issubset(set(LifecycleStage)))

        state = ProjectState(project_key="factory-acceptance")
        for stage in (
            LifecycleStage.SPECIFICATION,
            LifecycleStage.PLANNING,
            LifecycleStage.IMPLEMENTATION,
            LifecycleStage.REVIEW,
            LifecycleStage.VALIDATION,
            LifecycleStage.PREVIEW,
            LifecycleStage.RELEASE,
            LifecycleStage.OPERATIONS,
        ):
            transition(state, stage)
        self.assertEqual(state.stage, LifecycleStage.OPERATIONS)

    def test_routing_and_production_gate_are_independent(self):
        direct = decide_execution(
            TaskProfile(
                complexity=Complexity.LOW,
                estimated_files=2,
                direct_tools_sufficient=True,
            ),
            RiskProfile(),
        )
        self.assertEqual(direct.route, ExecutionRoute.DIRECT)
        self.assertFalse(direct.human_gate_required)

        codex = decide_execution(
            TaskProfile(
                complexity=Complexity.HIGH,
                estimated_files=12,
                broad_repo_investigation=True,
                direct_tools_sufficient=False,
            ),
            RiskProfile(),
        )
        self.assertEqual(codex.route, ExecutionRoute.CODEX)
        self.assertFalse(codex.human_gate_required)

        production = decide_execution(
            TaskProfile(complexity=Complexity.LOW),
            RiskProfile(production_change=True),
        )
        self.assertTrue(production.human_gate_required)

    def test_preview_policy_is_fail_closed_and_supports_explicit_non_applicability(self):
        implicit = evaluate_preview_applicability(
            manifest={},
            changed_files=("src/example.py",),
        )
        self.assertTrue(implicit.required)

        explicit = evaluate_preview_applicability(
            manifest={
                "preview": {
                    "required": False,
                    "reason": "backend-only project",
                }
            },
            changed_files=("src/example.py",),
        )
        self.assertFalse(explicit.required)
        self.assertEqual(explicit.reason, "backend-only project")

        monorepo = evaluate_preview_applicability(
            manifest={"preview": {"required_paths": ["apps/console/**"]}},
            changed_files=("src/example.py",),
        )
        self.assertFalse(monorepo.required)

    def test_autonomous_runner_wires_all_operational_workers(self):
        workflow = (ROOT / ".github/workflows/autonomous-runner.yml").read_text()
        for job in (
            "product-stage",
            "ci-followup",
            "specialist-security",
            "specialist-qa",
            "specialist-operations",
            "release-followup",
            "dispatch",
            "direct",
            "codex",
            "codex-manual",
            "preview",
            "alerts",
        ):
            self.assertIn(f"\n  {job}:", workflow)
        self.assertIn('cron: "17 * * * *"', workflow)
        self.assertIn("ai_product_factory.manual_codex_handoff --mode prepare", workflow)
        self.assertIn("ai_product_factory.manual_codex_handoff --mode followup", workflow)
        self.assertIn("FACTORY_CODEX_MANUAL_FALLBACK_ENABLED", workflow)
        for mode in (
            "health",
            "recovery",
            "product",
            "ci",
            "specialist",
            "release",
            "dispatch",
            "direct",
            "codex",
            "preview-probe",
            "preview",
            "alerts",
        ):
            self.assertIn(f"--mode {mode}", workflow)

    def test_scheduled_workers_skip_cleanly_without_control_plane_credentials(self):
        workflow = (ROOT / ".github/workflows/autonomous-runner.yml").read_text()
        self.assertGreaterEqual(workflow.count("Detect Control Plane readiness"), 6)
        for message in (
            "Dispatch is inert: Control Plane credentials are not configured.",
            "Manual Codex handoff is inert: Control Plane credentials are not configured.",
            "Preview follow-up is inert: Control Plane credentials are not configured.",
            "Operational alerts are inert: Control Plane credentials are not configured.",
        ):
            self.assertIn(message, workflow)
        self.assertIn("steps.readiness.outputs.control_plane == 'true'", workflow)

    def test_production_merge_is_observed_not_executed_by_runtime(self):
        adapter = (ROOT / "src/ai_product_factory/github_rest.py").read_text()
        runtime = (ROOT / "src/ai_product_factory/runtime_cli.py").read_text()
        self.assertNotIn("def merge_pull_request", adapter)
        self.assertNotIn("merge_pull_request(", runtime)
        self.assertIn("observe_manual_merge", runtime)
        self.assertIn('"awaiting_release"', runtime)

    def test_paid_and_codex_paths_remain_explicitly_fail_closed(self):
        workflow = (ROOT / ".github/workflows/autonomous-runner.yml").read_text()
        runtime = (ROOT / "src/ai_product_factory/runtime_cli.py").read_text()
        codex = (ROOT / "src/ai_product_factory/codex_cli_producer.py").read_text()

        self.assertIn("FACTORY_PRIMARY_MODEL_ENABLED", workflow)
        self.assertIn("FACTORY_MODEL_BUDGET_USD", workflow)
        self.assertIn("FACTORY_MODEL_RESERVE_USD", workflow)
        self.assertIn("OPENAI_IDENTITY_PROVIDER_ID", workflow)
        self.assertIn("OPENAI_SERVICE_ACCOUNT_ID", workflow)
        self.assertIn("OPENAI_WIF_AUDIENCE", workflow)
        self.assertIn("environment: openai-api", workflow)
        self.assertIn("environment: openai-codex", workflow)
        self.assertIn("require_paid_runtime_budget", runtime)

        provider = (ROOT / "src/ai_product_factory/openai_provider.py").read_text()
        self.assertIn("https://auth.openai.com/oauth/token", provider)
        self.assertIn("OPENAI_IDENTITY_PROVIDER_ID", provider)
        self.assertIn("OPENAI_SERVICE_ACCOUNT_ID", provider)

        self.assertIn("FACTORY_CODEX_ENABLED", workflow)
        self.assertIn("OPENAI_FEDERATION_RULE_ID", workflow)
        self.assertIn("OPENAI_WIF_AUDIENCE", workflow)
        self.assertIn("CODEX_ACCESS_TOKEN", workflow)
        self.assertIn("OPENAI_IDENTITY_TOKEN_FILE", workflow)
        self.assertIn("environment: openai-codex", workflow)
        self.assertIn("python -m ai_product_factory.codex_oidc --refresh-seconds 240", workflow)

        preflight = (ROOT / ".github/workflows/codex-wif-preflight.yml").read_text()
        self.assertIn("environment: openai-codex", preflight)
        self.assertIn("python -m ai_product_factory.codex_oidc", preflight)
        self.assertIn("@openai/codex@0.157.0", preflight)
        self.assertIn("workspace-write", codex)
        self.assertNotIn("danger-full-access", codex)
        self.assertNotIn("OPENAI_API_KEY", codex)

    def test_intake_control_plane_and_console_surfaces_exist(self):
        required_paths = (
            "apps/console",
            "src/ai_product_factory",
            "supabase/migrations",
            "config/factory.example.json",
            "PROJECT_PLAN.md",
            "docs/OPERATIONS.md",
            "docs/STATUS.md",
        )
        for relative in required_paths:
            self.assertTrue((ROOT / relative).exists(), relative)

        migration_names = {
            path.name for path in (ROOT / "supabase/migrations").glob("*.sql")
        }
        expected_history = {
            "20260925172455_create_factory_control_plane.sql",
            "20260925172519_add_control_plane_fk_indexes.sql",
            "20260925200339_factory_create_project_intake_rpc.sql",
            "20260925200742_factory_enqueue_project_bootstrap_rpc.sql",
            "20260925201128_factory_runtime_worker_rpcs.sql",
            "20260925202145_factory_persist_product_stage_rpc.sql",
            "20260925202913_factory_backlog_dispatch_rpcs.sql",
            "20260925232713_factory_console_auth_and_gate_resolution.sql",
            "20260925233709_factory_run_leases_and_recovery.sql",
            "20260925234331_factory_console_operator_admin.sql",
            "20260927010724_factory_claim_next_codex_run.sql",
            "20260927014211_reconcile_runtime_delivery_functions.sql",
            "20260927014826_add_factory_audit_task_id.sql",
            "20260927152310_manual_codex_handoff.sql",
            "20260928042922_factory_existing_project_reconciliation.sql",
            "20260928042939_factory_project_attachments.sql",
            "20260928042946_factory_project_state_snapshots.sql",
            "20260928043102_factory_project_state_snapshot_run_index.sql",
            "20260928145528_factory_authenticated_visual_evidence.sql",
            "20260928163442_factory_existing_project_runtime_stages.sql",
            "20260928170000_factory_project_database_registry.sql",
            "20260928170600_factory_project_database_verification.sql",
            "20260928202000_factory_resource_limit_snapshots.sql",
            "20260928204500_factory_project_database_oauth_vault.sql",
            "20260928212700_factory_agent_registry.sql",
            "20260928222200_factory_agent_scope_lock_agent_index.sql",
            "20260929011251_factory_execution_team_plans.sql",
            "20260929011724_factory_execution_team_plan_serialization.sql",
            "20260929011745_factory_execution_team_plan_serialization.sql",
            "20260929011847_factory_team_plan_dispatch_gate.sql",
            "20260929012059_factory_team_plan_dispatch_gate.sql",
            "20260929015617_factory_specialist_lanes.sql",
            "20260929021253_factory_adaptive_concurrency.sql",
            "20260929032833_factory_adaptive_concurrency.sql",
            "20260929033251_factory_change_sets.sql",
            "20260929033948_factory_project_brain.sql",
            "20260929033953_factory_impact_analysis.sql",
            "20260929034912_factory_requirement_traceability.sql",
            "20260929035910_factory_release_policy.sql",
            "20260929044153_factory_sandbox_context_repair.sql",
            "20260929044647_factory_incident_portfolio.sql",
            "20260929045025_factory_replay_shadow_provenance.sql",
            "20260929050701_factory_routing_policy_v2.sql",
            "20260929130616_factory_fk_indexes.sql",
        }
        self.assertEqual(migration_names, expected_history)

    def test_existing_project_reconciliation_is_executable_and_evidence_bounded(self):
        executor=(ROOT/"src/ai_product_factory/product_stage_executor.py").read_text()
        migration=(ROOT/"supabase/migrations/20260928163442_factory_existing_project_runtime_stages.sql").read_text()
        self.assertIn('"reconciliation"',executor)
        self.assertIn('"gap_analysis"',executor)
        self.assertIn("durable state snapshot",executor)
        self.assertIn("Do not claim tests",executor)
        self.assertIn("'state_snapshot',v_snapshot",migration)
        self.assertIn("'intake_spec'",migration)
        self.assertIn("'reconciliation','gap_analysis'",migration)
        self.assertIn("factory_project_state_snapshots",migration)

    def test_operational_console_surface_is_complete_and_server_bounded(self):
        required_routes = (
            "apps/console/app/page.tsx",
            "apps/console/app/projects/page.tsx",
            "apps/console/app/projects/[key]/page.tsx",
            "apps/console/app/projects/new/page.tsx",
            "apps/console/app/projects/new/review/page.tsx",
            "apps/console/app/runs/page.tsx",
            "apps/console/app/runs/[id]/page.tsx",
            "apps/console/app/queue/page.tsx",
            "apps/console/app/agents/page.tsx",
            "apps/console/app/orchestration/page.tsx",
            "apps/console/app/gates/page.tsx",
            "apps/console/app/evals/page.tsx",
            "apps/console/app/deployments/page.tsx",
            "apps/console/app/usage/page.tsx",
            "apps/console/app/audit/page.tsx",
            "apps/console/app/configuration/page.tsx",
            "apps/console/app/admin/operators/page.tsx",
        )
        for relative in required_routes:
            self.assertTrue((ROOT / relative).is_file(), relative)

        control_plane = (ROOT / "apps/console/lib/control-plane.ts").read_text()
        for function_name in (
            "getDashboard",
            "getProjectDetail",
            "getProjectOperations",
            "getProjectStateContext",
            "getProjectExecutionTeamPlan",
            "getOrchestrationOverview",
            "getRuns",
            "getRunDetail",
            "getWorkQueue",
            "getFactoryAgents",
            "getHumanGates",
            "getEvaluations",
            "getDeployments",
            "getUsageOverview",
            "getAuditEvents",
            "getConsoleConfiguration",
        ):
            self.assertIn(f"function {function_name}", control_plane)
        self.assertIn("requireConsoleOperator()", control_plane)

        client_surface = "\n".join(
            path.read_text()
            for path in (ROOT / "apps/console/app").rglob("*.tsx")
            if path.name not in {"auth-actions.tsx"}
        )
        self.assertNotIn("SUPABASE_SECRET_KEY", client_surface)
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", client_surface)
        self.assertNotIn("OPENAI_API_KEY", client_surface)
        self.assertNotIn("FACTORY_GITHUB_TOKEN", client_surface)
        project_page = (ROOT / "apps/console/app/projects/[key]/page.tsx").read_text()
        self.assertIn("Estado reconciliado", project_page)
        self.assertIn("Lacunas restantes", project_page)
        self.assertIn("Evidências confirmadas", project_page)
        self.assertIn("Equipe de execução", project_page)
        self.assertIn("Pico de workers", project_page)
        snapshot_migration = (ROOT / "supabase/migrations/20260928042946_factory_project_state_snapshots.sql").read_text()
        self.assertIn("factory_project_state_snapshots", snapshot_migration)
        self.assertIn("factory_record_project_state_snapshot", snapshot_migration)


        theme = (ROOT / "apps/console/app/theme.css").read_text()
        globals_css = (ROOT / "apps/console/app/globals.css").read_text()
        ui = (ROOT / "apps/console/app/ui.tsx").read_text()
        for token in (
            "--font-sans",
            "--font-mono",
            "--color-canvas",
            "--color-accent",
            "--color-success",
            "--color-warning",
            "--color-danger",
            "--radius-lg",
        ):
            self.assertIn(token, theme)
        self.assertIn("var(--font-sans)", globals_css)
        self.assertIn("var(--color-canvas)", globals_css)
        self.assertNotIn("font-family:Inter", globals_css)
        for primitive in (
            "PageHeader",
            "MetricCard",
            "StatusPill",
            "SectionHeader",
            "EmptyState",
            "ActionLink",
            "Button",
        ):
            self.assertIn("function "+primitive, ui)

        console_workflow = (ROOT / ".github/workflows/console.yml").read_text()
        self.assertIn("npm run typecheck", console_workflow)
        self.assertIn("npm run build", console_workflow)

    def test_manual_codex_fallback_preserves_release_and_credential_boundaries(self):
        workflow = (ROOT / ".github/workflows/autonomous-runner.yml").read_text()
        manual = (ROOT / "src/ai_product_factory/manual_codex_handoff.py").read_text()
        migration = (ROOT / "supabase/migrations/20260927152310_manual_codex_handoff.sql").read_text()

        self.assertIn("awaiting_codex_manual", manual)
        self.assertIn("Factory run:", manual)
        self.assertIn("Do not merge", manual)
        self.assertIn("factory_adopt_manual_codex_pr", manual)
        self.assertNotIn("OPENAI_API_KEY", manual)
        self.assertNotIn("CODEX_ACCESS_TOKEN", manual)
        self.assertNotIn("merge_pull_request", manual)
        self.assertIn("estimated_cost,metadata", migration)
        self.assertIn("'github','create_pr',1,0", migration)
        self.assertIn("preparing_codex_manual", migration)
        self.assertIn("awaiting_codex_manual", migration)
        self.assertIn("FACTORY_CODEX_ENABLED != 'true'", workflow)

    def test_codex_official_access_token_fallback_is_fail_closed(self):
        auth = (ROOT / "src/ai_product_factory/runtime_auth.py").read_text()
        producer = (ROOT / "src/ai_product_factory/codex_cli_producer.py").read_text()
        workflow = (ROOT / ".github/workflows/autonomous-runner.yml").read_text()
        preflight = (ROOT / ".github/workflows/codex-wif-preflight.yml").read_text()

        self.assertIn("CODEX_ACCESS_TOKEN", auth)
        self.assertIn("CODEX_ACCESS_TOKEN", producer)
        self.assertIn("CODEX_ACCESS_TOKEN: ${{ secrets.CODEX_ACCESS_TOKEN }}", workflow)
        self.assertIn("CODEX_ACCESS_TOKEN: ${{ secrets.CODEX_ACCESS_TOKEN }}", preflight)
        self.assertIn("Codex WIF is partially configured; refusing access-token fallback.", workflow)
        self.assertIn("Codex WIF is partially configured; refusing access-token fallback.", preflight)
        self.assertNotIn("CHATGPT_ACCESS_TOKEN", workflow)
        self.assertNotIn("CHATGPT_ACCESS_TOKEN", preflight)

    def test_no_legacy_unmetered_paid_model_entrypoints(self):
        workflows = ROOT / ".github/workflows"
        for retired in (
            "openai-runtime.yml",
            "openai-runtime-execute.yml",
            "openai-billing-smoke-once.yml",
        ):
            self.assertFalse((workflows / retired).exists(), retired)

        cli = (ROOT / "src/ai_product_factory/cli.py").read_text()
        self.assertNotIn('"openai-execute"', cli)
        self.assertFalse((ROOT / "src/ai_product_factory/openai_billing_smoke.py").exists())

        runtime = (ROOT / "src/ai_product_factory/runtime_cli.py").read_text()
        self.assertIn("MeteredPrimaryProvider", runtime)
        self.assertIn("require_paid_runtime_budget", runtime)
        self.assertIn('FACTORY_MODEL_RESERVE_USD', runtime)

    def test_api_wif_preflight_is_manual_and_non_model(self):
        workflow = (ROOT / ".github/workflows/openai-api-wif-preflight.yml").read_text()
        module = (ROOT / "src/ai_product_factory/openai_wif_preflight.py").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("environment: openai-api", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("GitHubActionsOpenAIWorkloadIdentity", module)
        self.assertIn("model_call=not_performed", module)
        self.assertNotIn("/v1/responses", workflow)
        self.assertNotIn("/v1/responses", module)

    def test_pull_request_workflows_are_safe_for_public_window(self):
        workflow_dir = ROOT / ".github/workflows"
        workflows = {
            path.name: path.read_text()
            for path in workflow_dir.glob("*.yml")
        }
        for name, workflow in workflows.items():
            self.assertNotIn("pull_request_target:", workflow, name)

        for name in ("validate.yml", "console.yml"):
            workflow = workflows[name]
            self.assertIn("pull_request:", workflow, name)
            self.assertIn("permissions:\n  contents: read", workflow, name)
            self.assertNotIn("$" + "{{ secrets.", workflow, name)
            self.assertNotIn("id-token: write", workflow, name)

    def test_authenticated_visual_evidence_broker_is_source_controlled_and_fail_closed(self):
        broker = (ROOT / "supabase/functions/factory-visual-evidence-broker/index.ts").read_text()
        workflow = (ROOT / ".github/workflows/authenticated-visual-evidence.yml").read_text()

        for claim in (
            'audience: AUDIENCE',
            'repository: "leandrosilveiradepaula/ai-product-factory"',
            'repository_id: "1387883686"',
            'repository_owner_id: "256917842"',
            'ref: "refs/heads/main"',
            'environment: "openai-api"',
            'workflow_ref:',
        ):
            self.assertIn(claim, broker)

        self.assertIn('role: "operator"', broker)
        self.assertNotIn('role: "admin"', broker)
        self.assertIn('cleanupUser', broker)
        self.assertIn('source_commit_mismatch', broker)
        self.assertIn('factory-visual-evidence', workflow)
        self.assertIn('id-token: write', workflow)
        self.assertNotIn('SUPABASE_SERVICE_ROLE_KEY', workflow)
        self.assertNotIn('SUPABASE_SECRET_KEY', workflow)

    def test_authenticated_visual_capture_is_manual_and_exact_target_bounded(self):
        workflow = (ROOT / ".github/workflows/authenticated-visual-evidence.yml").read_text()
        script = (ROOT / "scripts/capture_authenticated_console.mjs").read_text()

        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("\n  push:", workflow)
        self.assertIn("target_url:", workflow)
        self.assertIn("target_commit:", workflow)
        self.assertIn('target.hostname.endsWith(".vercel.app")', workflow)
        self.assertIn('target.protocol !== "https:"', workflow)
        self.assertIn("github.rest.repos.getCommit", workflow)
        self.assertIn("FACTORY_VISUAL_TARGET_COMMIT", workflow)
        self.assertIn("FACTORY_VISUAL_TARGET_COMMIT", script)
        self.assertIn("targetCommit", script)
        self.assertIn("targetUrl:consoleUrl", script)
        self.assertIn("workflowSourceCommit", script)

    def test_crm_cross_repo_preflight_is_read_only_and_explicit(self):
        workflow = (ROOT / ".github/workflows/crm-cross-repo-preflight.yml").read_text()
        self.assertIn("FACTORY_GITHUB_TOKEN: ${{ secrets.FACTORY_GITHUB_TOKEN }}", workflow)
        self.assertIn("environment: openai-api", workflow)
        self.assertIn("blocked_missing_token", workflow)
        self.assertIn("leandrosilveiradepaula/crm-infodive", workflow)
        self.assertIn("/git/ref/heads/main", workflow)
        self.assertIn('"private":True', workflow)
        self.assertNotIn("curl -X POST", workflow)
        self.assertNotIn("curl -X PATCH", workflow)
        self.assertNotIn("curl -X PUT", workflow)
        self.assertNotIn("curl -X DELETE", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("issues: write", workflow)
        self.assertNotIn("pull-requests: write", workflow)

    def test_console_supabase_oauth_is_pkce_vaulted_admin_bounded_and_read_only(self):
        oauth=(ROOT/"apps/console/lib/supabase-oauth.ts").read_text()
        connect=(ROOT/"apps/console/app/api/integrations/supabase/connect/route.ts").read_text()
        callback=(ROOT/"apps/console/app/api/integrations/supabase/callback/route.ts").read_text()
        detail=(ROOT/"apps/console/app/projects/[key]/page.tsx").read_text()
        migration=(ROOT/"supabase/migrations/20260928204500_factory_project_database_oauth_vault.sql").read_text()
        env=(ROOT/"apps/console/.env.example").read_text()
        self.assertIn("code_challenge_method",oauth)
        self.assertIn('"S256"',oauth)
        self.assertIn("/database/query/read-only",oauth)
        self.assertNotIn('/database/query"',oauth)
        self.assertIn("state!==expected",callback)
        self.assertIn("requireConsoleAdmin()",connect)
        self.assertIn("requireConsoleAdmin()",callback)
        self.assertIn("database binding is not awaiting access",connect)
        self.assertIn("project_id=eq.",connect)
        self.assertIn("project_id=eq.",callback)
        self.assertIn("Conectar Supabase",detail)
        self.assertIn("factory_private.store_project_database_oauth",migration)
        self.assertIn("factory_private.get_project_database_oauth_tokens",migration)
        self.assertIn("factory_private.revoke_project_database_oauth",migration)
        self.assertIn("security invoker",migration)
        self.assertIn("revoke all on table public.factory_project_database_oauth from public,anon,authenticated",migration)
        self.assertIn("SUPABASE_OAUTH_CLIENT_ID=",env)
        self.assertIn("SUPABASE_OAUTH_CLIENT_SECRET=",env)
        self.assertNotIn("access_token",detail)
        self.assertNotIn("refresh_token",detail)

    def test_console_exposes_database_readiness_without_secret_references(self):
        detail=(ROOT/"apps/console/app/projects/[key]/page.tsx").read_text()
        control=(ROOT/"apps/console/lib/control-plane.ts").read_text()
        self.assertIn("getProjectDatabases",detail)
        self.assertIn("Aguardando conexão",detail)
        self.assertIn("Somente leitura",detail)
        self.assertIn("factory_project_databases",control)
        self.assertNotIn("credential_ref",control)
        self.assertNotIn("credentialRef",detail)

    def test_project_database_capability_is_scoped_and_cost_gated(self):
        migration=(ROOT/"supabase/migrations/20260928170000_factory_project_database_registry.sql").read_text()
        adapter=(ROOT/"src/ai_product_factory/supabase_management.py").read_text()
        docs=(ROOT/"docs/PROJECT_DATABASES.md").read_text()

        self.assertIn("factory_project_databases",migration)
        self.assertIn("credential_ref",migration)
        self.assertIn("never a credential value",migration)
        self.assertIn("enable row level security",migration)
        self.assertIn("revoke all on table public.factory_project_databases from public,anon,authenticated",migration)
        self.assertIn("/database/query/read-only",adapter)
        self.assertIn("explicit human cost approval",adapter)
        self.assertIn("project-scoped integration",docs)
        self.assertIn("pending_access",docs)
        self.assertNotIn("SUPABASE_ACCESS_TOKEN=",docs)

    def test_project_supabase_preflight_is_read_only_and_secret_bounded(self):
        workflow=(ROOT/".github/workflows/project-supabase-preflight.yml").read_text()
        script=(ROOT/"scripts/verify_project_supabase.py").read_text()
        migration=(ROOT/"supabase/migrations/20260928170600_factory_project_database_verification.sql").read_text()

        self.assertIn("environment: ${{ inputs.environment_name }}",workflow)
        self.assertIn("secrets.FACTORY_PROJECT_SUPABASE_ACCESS_TOKEN",workflow)
        self.assertIn("read_only_query",script)
        self.assertNotIn("write_query(",script)
        self.assertIn("project_ref_mismatch",script)
        self.assertIn("pending_access",migration)
        self.assertIn("factory_record_project_database_verification",migration)


    def test_control_plane_oidc_broker_is_fail_closed_and_secretless(self):
        workflow = (ROOT / ".github/workflows/autonomous-runner.yml").read_text()
        action = (ROOT / ".github/actions/control-plane-oidc/action.yml").read_text()
        broker = (ROOT / "supabase/functions/factory-runtime-control-plane/index.ts").read_text()
        preflight = (ROOT / ".github/workflows/control-plane-oidc-preflight.yml").read_text()

        self.assertNotIn("secrets.SUPABASE_URL", workflow)
        self.assertNotIn("secrets.SUPABASE_SECRET_KEY", workflow)
        self.assertNotIn("secrets.SUPABASE_SERVICE_ROLE_KEY", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("./.github/actions/control-plane-oidc", workflow)
        self.assertIn("factory-runtime-control-plane", action)
        self.assertIn("ACTIONS_ID_TOKEN_REQUEST_URL", action)
        self.assertIn("ACTIONS_ID_TOKEN_REQUEST_TOKEN", action)

        for claim in (
            'repository: "leandrosilveiradepaula/ai-product-factory"',
            'repository_id: "1387883686"',
            'repository_owner_id: "256917842"',
            'ref: "refs/heads/main"',
            'audience:AUDIENCE',
        ):
            self.assertIn(claim, broker)
        self.assertIn("ALLOWED_WORKFLOW_REFS", broker)
        self.assertIn('resource.startsWith("factory_")', broker)
        self.assertIn('resource.startsWith("rpc/factory_")', broker)
        self.assertNotIn("/auth/v1/", broker)
        self.assertIn("workflow_dispatch:", preflight)
        self.assertIn("factory_projects?select=project_key", preflight)

    def test_vercel_deployments_are_bounded_to_promoted_preview_candidates(self):
        vercel = (ROOT / "apps/console/vercel.json").read_text()
        workflow = (ROOT / ".github/workflows/console.yml").read_text()
        promote = (ROOT / ".github/workflows/promote-preview-candidate.yml").read_text()
        operations = (ROOT / "docs/OPERATIONS.md").read_text()

        self.assertIn('"**": false', vercel)
        self.assertIn('"main": true', vercel)
        self.assertIn('"preview/**": true', vercel)
        self.assertNotIn('"console/**": true', vercel)
        self.assertIn('"ignoreCommand"', vercel)
        self.assertIn('VERCEL_GIT_COMMIT_REF', vercel)
        self.assertIn('preview/*) exit 1', vercel)
        self.assertIn('git diff --quiet HEAD^ HEAD ./', vercel)
        self.assertIn('case "${GITHUB_HEAD_REF}" in', workflow)
        self.assertIn("console/*|ci/*|test/*|security/*|agents/*|intelligence/*|quality/*|policy/*|runtime/*|operations/*|observability/*|audit/*|release/*)", workflow)
        self.assertIn('"heads/preview/pr-"', promote)
        self.assertIn("candidate SHA is not the exact PR head", promote)
        self.assertIn('["test", "factory-acceptance", "validate"]', promote)
        self.assertIn("Vercel deployment budget policy", operations)
        self.assertIn("Active policy:", operations)

    def test_source_controlled_browser_evidence_target_is_exact_and_secret_free(self):
        workflow=(ROOT/".github/workflows/console-browser-evidence.yml").read_text()
        target=(ROOT/".github/preview-target.json").read_text()
        self.assertIn('".github/preview-target.json"',workflow)
        self.assertIn("candidate_sha",workflow)
        self.assertIn("^[0-9a-f]{40}$",workflow)
        self.assertIn("\\.vercel\\.app",workflow)
        self.assertIn("repos.getCommit",workflow)
        self.assertIn("FACTORY_VERCEL_TRUSTED_OIDC_TOKEN",workflow)
        self.assertIn("preview_url",target)
        self.assertIn("candidate_sha",target)
        for forbidden in ("VERCEL_TOKEN","SUPABASE_SECRET_KEY","SUPABASE_SERVICE_ROLE_KEY","OPENAI_API_KEY","FACTORY_GITHUB_TOKEN"):
            self.assertNotIn(forbidden,target)

    def test_agent_sql_benchmark_is_not_implicit_runtime_work(self):
        workflow = (ROOT / ".github/workflows/autonomous-runner.yml").read_text()
        codex = (ROOT / "src/ai_product_factory/codex_cli_producer.py").read_text()
        self.assertNotIn("63-question", workflow)
        self.assertIn("63-question benchmark", codex)



    def test_console_primary_ui_is_portuguese(self):
        files = [
            ROOT / "apps" / "console" / "app" / "page.tsx",
            ROOT / "apps" / "console" / "app" / "projects" / "page.tsx",
            ROOT / "apps" / "console" / "app" / "projects" / "[key]" / "page.tsx",
            ROOT / "apps" / "console" / "app" / "projects" / "new" / "page.tsx",
            ROOT / "apps" / "console" / "app" / "projects" / "new" / "review" / "page.tsx",
            ROOT / "apps" / "console" / "app" / "runs" / "page.tsx",
            ROOT / "apps" / "console" / "app" / "queue" / "page.tsx",
            ROOT / "apps" / "console" / "app" / "agents" / "page.tsx",
            ROOT / "apps" / "console" / "app" / "gates" / "page.tsx",
            ROOT / "apps" / "console" / "app" / "nav.tsx",
        ]
        text = "\n".join(path.read_text(encoding="utf-8") for path in files)
        forbidden = [
            "Start a product",
            "New Work",
            "Project Detail",
            "Operational timeline",
            "Work Queue",
            "Open tasks",
            "Known cost",
            "Review Intake",
            "New product",
            "Import repository",
            "Will be created later",
            "Known integrations",
            "Start Factory",
        ]
        for phrase in forbidden:
            self.assertNotIn(phrase, text)

class ExtendedFactoryAcceptanceTests(unittest.TestCase):
    def test_resource_limit_observability_is_fail_closed_and_secret_free(self):
        migration=(ROOT/"supabase/migrations/20260928202000_factory_resource_limit_snapshots.sql").read_text()
        model=(ROOT/"src/ai_product_factory/resource_limits.py").read_text()
        assert "factory_resource_limit_snapshots" in migration
        assert "enable row level security" in migration
        assert "revoke all on public.factory_resource_limit_snapshots from public,anon,authenticated" in migration
        assert "provider_blocked" in migration
        assert "v_ratio>=0.9" in migration
        assert "v_ratio>=0.7" in migration
        assert "secret-like metadata is forbidden" in migration
        assert "def percent" in model
        assert 'if p>=100:return "blocked"' in model
        assert 'if p>=90:return "critical"' in model
        assert 'if p>=70:return "attention"' in model

    def test_supabase_oauth_vault_backend_keeps_definers_private(self):
        migration=(ROOT/"supabase/migrations/20260928204500_factory_project_database_oauth_vault.sql").read_text()
        assert "create schema if not exists factory_private" in migration
        assert "security definer" in migration
        assert "factory_private.store_project_database_oauth" in migration
        assert "factory_private.get_project_database_oauth_tokens" in migration
        assert "factory_private.revoke_project_database_oauth" in migration
        assert "security invoker" in migration
        assert "last_verified_at=null" in migration
        assert re.search(r"(?<!last_)verified_at\\s*=\\s*null",migration,re.I) is None
        assert "revoke all on all functions in schema factory_private from public,anon,authenticated" in migration
        assert "grant execute on function public.factory_get_project_database_oauth_tokens(uuid) to service_role" in migration

    def test_console_exposes_resource_limit_percentages_without_inventing_unknowns(self):
        control=(ROOT/"apps/console/lib/control-plane.ts").read_text()
        usage=(ROOT/"apps/console/app/usage/page.tsx").read_text()
        self.assertIn("getResourceLimits",control)
        self.assertIn("factory_resource_limit_snapshots",control)
        self.assertIn("used==null||limit==null||limit<=0?null",control)
        self.assertIn("Limites e quotas operacionais",usage)
        self.assertIn('x.percent==null?"—":x.percent.toFixed(1)+"%"',usage)
        self.assertIn('x.used==null||x.limit==null?"Indisponível"',usage)
        self.assertIn("x.quality",usage)
        self.assertIn("x.resetsAt",usage)

    def test_console_agent_registry_is_server_side_and_operational(self):
        page=(ROOT/"apps/console/app/agents/page.tsx").read_text()
        control=(ROOT/"apps/console/lib/control-plane.ts").read_text()
        nav=(ROOT/"apps/console/app/nav.tsx").read_text()
        self.assertIn("getFactoryAgents",page)
        self.assertIn("Agentes da Factory",page)
        self.assertIn("slots",page)
        self.assertIn("Locks de escopo",page)
        self.assertIn("factory_agents",control)
        self.assertIn("factory_run_agent_assignments",control)
        self.assertIn("factory_agent_scope_locks",control)
        self.assertIn("requireConsoleOperator()",control)
        self.assertNotIn("credential",page.lower())
        self.assertIn('href:"/agents"',nav)

    def test_console_dependencies_are_locked_and_ci_is_deterministic(self):
        package=(ROOT/"apps/console/package.json").read_text()
        lock=(ROOT/"apps/console/package-lock.json").read_text()
        workflow=(ROOT/".github/workflows/console.yml").read_text()
        self.assertIn('"next": "15.5.26"',package)
        self.assertIn('"next": "15.5.26"',lock)
        self.assertIn('"lockfileVersion": 3',lock)
        self.assertIn("- run: npm ci",workflow)
        self.assertNotIn("- run: npm install",workflow)

    def test_agent_registry_is_configurable_scoped_and_fail_closed(self):
        migration=(ROOT/"supabase/migrations/20260928212700_factory_agent_registry.sql").read_text()
        scheduler=(ROOT/"src/ai_product_factory/agent_scheduler.py").read_text()
        runtime=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()
        planner=(ROOT/"src/ai_product_factory/product_stage_executor.py").read_text()
        assert "create table if not exists public.factory_agents" in migration
        assert "max_concurrency" in migration
        assert "factory_agent_scope_locks" in migration
        assert "scope conflict with run" in migration
        assert "factory_schedule_next_unassigned_run" in migration
        assert "factory_claim_next_agent_direct_run" in migration
        assert "factory_claim_next_agent_codex_run" in migration
        assert "factory_recover_expired_agent_slots" in migration
        assert "revoke all on public.factory_agents from public,anon,authenticated" in migration
        assert "grant execute on function public.factory_schedule_run_agent" in migration
        assert "idx_factory_run_agent_assignments_active_run" in migration
        assert "lease_expires_at > now()" in migration
        assert "starts_with(l.scope_key" in migration
        assert "or l.lease_expires_at <= now()" in migration
        assert "required_capabilities" in migration
        assert "scope_keys" in migration
        assert "Do not assume a fixed number of agents" in planner
        assert 'scheduler.release(item.run_id,"blocked")' in runtime
        assert "recover_expired" in scheduler

    def test_specialist_workers_fan_out_from_control_plane_matrix(self):
        workflow=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
        runtime=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()
        scheduler=(ROOT/"src/ai_product_factory/agent_scheduler.py").read_text()
        assert "direct_matrix:" in workflow
        assert "codex_matrix:" in workflow
        assert "strategy:" in workflow
        assert "matrix: ${{ fromJSON(needs.dispatch.outputs.direct_matrix) }}" in workflow
        assert "matrix: ${{ fromJSON(needs.dispatch.outputs.codex_matrix) }}" in workflow
        assert '--agent-key "${{ matrix.agent_key }}" --run-id "${{ matrix.run_id }}"' in workflow
        assert "inputs.run_codex == true" in workflow
        assert "if run_id is None:" in runtime
        assert 'raise ValueError("agent_key is required when run_id is explicit")' in runtime
        assert 'require_route_tools(agent_key,"direct")' in runtime
        assert 'require_route_tools(agent_key,"codex")' in runtime
        assert 'profile.require_tools("github_write","model_primary")' in scheduler
        assert 'profile.require_tools("github_write","codex")' in scheduler

    def test_execution_team_plan_is_deterministic_versioned_and_least_privilege(self):
        planner=(ROOT/"src/ai_product_factory/execution_team_planner.py").read_text()
        executor=(ROOT/"src/ai_product_factory/product_stage_executor.py").read_text()
        queue=(ROOT/"src/ai_product_factory/supabase_runtime_queue.py").read_text()
        scheduler=(ROOT/"src/ai_product_factory/agent_scheduler.py").read_text()
        migration=(ROOT/"supabase/migrations/20260929011251_factory_execution_team_plans.sql").read_text()
        assert "minimum-capability-cover-with-least-privilege" in planner
        assert "planned_worker_peak" in planner
        assert "waves" in planner
        assert "scope" in planner
        assert "specialist_review_recommended" in planner
        assert "no_single_agent_covers_task" in planner
        assert "build_execution_team_plan" in executor
        assert "team_profiles" in executor
        assert 'evidence.stage=="planning"' in queue
        assert "factory_record_execution_team_plan" in queue
        assert "def profiles" in scheduler
        assert "factory_execution_team_plans" in migration
        assert "enable row level security" in migration
        assert "revoke all on public.factory_execution_team_plans from public,anon,authenticated" in migration
        assert "team.plan.recorded" in migration
        assert "security invoker" in migration
        serialization=(ROOT/"supabase/migrations/20260929011724_factory_execution_team_plan_serialization.sql").read_text()
        assert "for update" in serialization
        assert "factory_projects" in serialization
        serialization_reapply=(ROOT/"supabase/migrations/20260929011745_factory_execution_team_plan_serialization.sql").read_text()
        assert "factory_record_execution_team_plan" in serialization_reapply
        assert "for update" in serialization_reapply
        assert "factory_projects" in serialization_reapply
        dispatch_gate=(ROOT/"supabase/migrations/20260929012059_factory_team_plan_dispatch_gate.sql").read_text()
        assert "factory_execution_team_plans" in dispatch_gate
        assert "v_team_status is distinct from 'ready'" in dispatch_gate
        assert "factory_dispatch_next_planned_task" in dispatch_gate

    def test_specialist_lanes_are_read_only_fail_closed_and_precede_preview(self):
        workflow=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
        runtime=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()
        migration=(ROOT/"supabase/migrations/20260929015617_factory_specialist_lanes.sql").read_text()
        evaluator=(ROOT/"src/ai_product_factory/specialist_lanes.py").read_text()

        for job in ("specialist-security","specialist-qa","specialist-operations"):
            self.assertIn("\n  "+job+":",workflow)
        self.assertIn("needs: [specialist-security, specialist-qa, specialist-operations]",workflow)
        specialist_region=workflow[workflow.index("\n  specialist-security:"):workflow.index("\n  release-followup:")]
        self.assertNotIn("contents: write",specialist_region)
        self.assertNotIn("pull-requests: write",specialist_region)
        self.assertIn("--mode specialist --specialist-role security",specialist_region)
        self.assertIn("--mode specialist --specialist-role qa",specialist_region)
        self.assertIn("--mode specialist --specialist-role operations",specialist_region)

        self.assertIn("factory_specialist_lane_jobs",migration)
        self.assertIn("factory_enqueue_specialist_lanes",migration)
        self.assertIn("factory_claim_specialist_lane",migration)
        self.assertIn("factory_complete_specialist_lane",migration)
        self.assertIn("factory_recover_specialist_lanes",migration)
        self.assertIn("enable row level security",migration)
        self.assertIn("security invoker",migration)
        self.assertIn("candidate_commit_mismatch",migration)
        self.assertIn("specialist_retry_exhausted",migration)
        self.assertIn("SupabaseSpecialistLaneQueue",runtime)
        self.assertIn("evaluate_specialist_lane",runtime)
        self.assertIn("model_call",evaluator)
        self.assertNotIn("merge_pull_request(",evaluator)

    def test_team_planner_has_offline_routing_eval_corpus(self):
        corpus=(ROOT/"evals/team_planner_cases.json").read_text()
        runner=(ROOT/"src/ai_product_factory/team_planner_eval.py").read_text()
        tests=(ROOT/"tests/test_team_planner_eval.py").read_text()
        self.assertIn('"ui-simple"',corpus)
        self.assertIn('"auth-feature"',corpus)
        self.assertIn('"full-stack"',corpus)
        self.assertIn('"incident-triage"',corpus)
        self.assertIn("overstaffed_worker_peak",runner)
        self.assertIn("forbidden_roles_selected",runner)
        self.assertIn("missing_required_roles",runner)
        self.assertIn("test_offline_corpus_passes_without_model_or_external_service",tests)
        self.assertNotIn("OpenAIResponsesProvider",runner)

    def test_adaptive_concurrency_is_auditable_and_fail_closed(self):
        policy=(ROOT/"src/ai_product_factory/adaptive_concurrency.py").read_text()
        controller=(ROOT/"src/ai_product_factory/adaptive_agent_scheduler.py").read_text()
        runtime=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()
        migration=(ROOT/"supabase/migrations/20260929032833_factory_adaptive_concurrency.sql").read_text()
        self.assertIn("unknown paid cost blocks execution",policy)
        self.assertIn('quota in {"blocked","critical"}',policy)
        self.assertIn("recent conflict rate",policy)
        self.assertIn("recent repair rate",policy)
        self.assertIn("first-pass yield",policy)
        self.assertIn("SupabaseAdaptiveConcurrencyController",runtime)
        self.assertIn("factory_agent_concurrency_decisions",migration)
        self.assertIn("factory_record_agent_concurrency_decision",migration)
        self.assertIn("enable row level security",migration)
        self.assertIn("security invoker",migration)
        self.assertNotIn("OPENAI_API_KEY",controller)

    def test_requirement_traceability_and_dod_are_factual_private_and_human_bounded(self):
        migration=(ROOT/"supabase/migrations/20260929034912_factory_requirement_traceability.sql").read_text()
        trace=(ROOT/"src/ai_product_factory/traceability.py").read_text()
        dod=(ROOT/"src/ai_product_factory/definition_of_done.py").read_text()
        runtime=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()
        planning=(ROOT/"src/ai_product_factory/product_stage_executor.py").read_text()

        for table in (
            "factory_requirements",
            "factory_requirement_task_links",
            "factory_requirement_evidence",
            "factory_definitions_of_done",
            "factory_definition_of_done_evidence",
        ):
            self.assertIn(table,migration)
        self.assertGreaterEqual(migration.count("enable row level security"),5)
        self.assertIn("factory_record_requirement_trace",migration)
        self.assertIn("factory_record_definition_of_done",migration)
        self.assertIn("factory_record_delivery_evidence",migration)
        self.assertIn("factory_get_definition_of_done_readiness",migration)
        self.assertIn("security invoker",migration)
        self.assertIn("secret-like evidence metadata is forbidden",migration)
        self.assertIn("REQ-",trace)
        self.assertIn("human_release",dod)
        self.assertIn("production merge is always a human gate",dod)
        self.assertIn("migration_validation",dod)
        self.assertIn("rollback_analysis",dod)
        self.assertIn("acceptance_criteria (non-empty array",planning)
        self.assertIn('evidence_type="github_ci"',runtime)
        self.assertIn('evidence_type="human_release"',runtime)
        self.assertNotIn("score",dod.lower())

    def test_release_policy_is_source_controlled_auditable_and_cannot_auto_merge(self):
        policy=(ROOT/"config/factory.release-policy.v1.json").read_text()
        engine=(ROOT/"src/ai_product_factory/release_policy_engine.py").read_text()
        intelligence=(ROOT/"src/ai_product_factory/release_intelligence.py").read_text()
        runtime=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()
        migration=(ROOT/"supabase/migrations/20260929035910_factory_release_policy.sql").read_text()

        self.assertIn('"auto_merge_allowed": false',policy)
        self.assertIn('"human_release_required": true',policy)
        self.assertIn("ready_for_human_release",engine)
        self.assertIn("unknown paid cost blocks release readiness",engine)
        self.assertIn("migration change requires verified rollback",engine)
        self.assertIn("missing_nonhuman_dod",intelligence)
        self.assertIn("release_policy_blocked",runtime)
        self.assertIn("SupabaseReleasePolicyStore().mark_released",runtime)
        self.assertIn("factory_policy_decisions",migration)
        self.assertIn("factory_release_reports",migration)
        self.assertIn("factory_get_release_facts",migration)
        self.assertIn("factory_record_policy_decision",migration)
        self.assertIn("factory_record_release_report",migration)
        self.assertIn("security invoker",migration)
        self.assertNotIn("merge_pull_request(",engine)
        self.assertNotIn("merge_pull_request(",intelligence)

    def test_work_units_use_secret_safe_context_packets_and_bounded_repair_loops(self):
        context=(ROOT/"src/ai_product_factory/work_unit_context.py").read_text()
        worker=(ROOT/"src/ai_product_factory/change_set_worker.py").read_text()
        producer=(ROOT/"src/ai_product_factory/implementation_producer.py").read_text()
        codex=(ROOT/"src/ai_product_factory/codex_cli_producer.py").read_text()
        lanes=(ROOT/"src/ai_product_factory/specialist_lane_queue.py").read_text()
        migration=(ROOT/"supabase/migrations/20260929044153_factory_sandbox_context_repair.sql").read_text()

        for marker in (
            "secret-bearing context field is forbidden",
            "write_scopes",
            "enforce_write_scopes",
            "exact_base_required",
            "secrets_in_context",
        ):
            assert marker in context
        assert "build_context_packet" in worker
        assert "record_context" in worker
        assert "enforce_write_scopes" in worker
        assert "Change Set implementation requires a durable context packet" in producer
        assert "bounded Context Packet" in codex
        assert "factory_enqueue_repair_from_specialist" in lanes
        assert '"p_max_cycles":3' in lanes
        assert "factory_close_repairs_after_specialist_pass" in lanes
        assert "factory_work_unit_context_packets" in migration
        assert "factory_repair_jobs" in migration
        assert "cycle between 1 and 3" in migration
        assert "repair max cycles must be between 1 and 3" in migration
        assert "role_not_auto_repairable" in migration
        assert "enable row level security" in migration
        assert "security invoker" in migration

    def test_incident_mode_and_portfolio_scheduler_preserve_safety_gates(self):
        migration=(ROOT/"supabase/migrations/20260929044647_factory_incident_portfolio.sql").read_text()
        portfolio=(ROOT/"src/ai_product_factory/portfolio_scheduler.py").read_text()
        dispatch=(ROOT/"src/ai_product_factory/supabase_backlog_dispatch.py").read_text()
        for marker in (
            "factory_project_scheduling",
            "factory_incidents",
            "factory_portfolio_decisions",
            "factory_open_incident",
            "factory_transition_incident",
            "factory_portfolio_candidates",
            "factory_record_portfolio_decision",
            "incident resolution requires full gates",
            "enable row level security",
            "security invoker",
        ):
            assert marker in migration
        assert "soft_preemption_active" in portfolio
        assert '"active_workers_cancelled":False' in portfolio
        assert '"production_gates_bypassed":False' in portfolio
        assert "SupabasePortfolioScheduler" in dispatch
        assert "portfolio.candidates" in dispatch
        assert "factory_tasks?select=project_id" not in dispatch

    def test_replay_shadow_and_improvement_are_zero_effect_and_source_controlled(self):
        module=(ROOT/"src/ai_product_factory/provenance_replay.py").read_text()
        migration=(ROOT/"supabase/migrations/20260929045025_factory_replay_shadow_provenance.sql").read_text()
        worker=(ROOT/"src/ai_product_factory/change_set_worker.py").read_text()
        for marker in (
            "factory_run_provenance",
            "factory_replay_requests",
            "factory_shadow_decisions",
            "factory_improvement_proposals",
            "effect text not null default 'none' check (effect='none')",
            "model_calls_allowed boolean not null default false",
            "requires_source_control boolean not null default true",
            "auto_apply boolean not null default false",
            "factory_create_replay_request",
            "factory_record_shadow_decision",
            "factory_propose_improvement",
            "enable row level security",
            "security invoker",
        ):
            assert marker in migration
        assert "build_run_provenance" in module
        assert "canonical_hash" in module
        assert 'RELEASE_POLICY_VERSION="v1"' in module
        assert "self.provenance.record" in worker

    def test_architecture_guardian_is_deterministic_and_security_lane_primary(self):
        guardian=(ROOT/"src/ai_product_factory/architecture_guardian.py").read_text()
        lanes=(ROOT/"src/ai_product_factory/specialist_lanes.py").read_text()
        for marker in (
            "architecture_guardian_v1",
            "openai_key",
            "supabase_secret",
            "github_token",
            "client_service_role",
            "pull_request_target",
            "write_all_permissions",
            "danger_full_access",
            "disable_rls",
            "permissive_public_grant",
            "database_lineage",
            "api_contracts",
            "dependency_surfaces",
            '"full_sast":False',
            '"sbom_generation":False',
            '"api_semantic_compatibility":False',
            '"model_call":False',
        ):
            assert marker in guardian
        assert "scan_pull_request_files" in lanes
        assert 'report.evidence["blocking_findings"]' in lanes
        assert "_FORBIDDEN_SECURITY_PATTERNS" not in lanes

    def test_unittest_collection_has_explicit_guard_against_function_style_tests(self):
        workflow=(ROOT/".github/workflows/validate.yml").read_text()
        guard=(ROOT/"scripts/check_test_collection.py").read_text()
        assert "python scripts/check_test_collection.py" in workflow
        assert "ast.parse" in guard
        assert "TOTAL_UNCOLLECTED" in guard
        assert "TEST_COLLECTION_GUARD_OK" in guard


if __name__ == "__main__":
    unittest.main()



class OrchestrationConsoleAcceptanceTests(unittest.TestCase):
    def test_console_orchestration_surface_is_observational_and_factual(self):
        page=(ROOT/"apps/console/app/orchestration/page.tsx").read_text()
        control=(ROOT/"apps/console/lib/control-plane.ts").read_text()
        nav=(ROOT/"apps/console/app/nav.tsx").read_text()
        self.assertIn("Orquestração",nav)
        self.assertIn("getOrchestrationOverview",control)
        for table in (
            "factory_project_scheduling",
            "factory_incidents",
            "factory_repair_jobs",
            "factory_replay_requests",
            "factory_improvement_proposals",
            "factory_release_reports",
        ):
            self.assertIn(table,control)
        self.assertIn("Prontidão de release",page)
        self.assertIn("fatos, não score subjetivo",page)
        self.assertIn("sempre zero-effect",page)
        self.assertIn("Aguardando merge humano de produção",page)
        self.assertNotIn("merge_pull_request",page)
        self.assertNotIn("SUPABASE_SECRET_KEY",page)
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY",page)



class RoutingV2AcceptanceTests(unittest.TestCase):
    def test_routing_v2_is_versioned_comparative_and_gate_independent(self):
        policy=(ROOT/"src/ai_product_factory/codex_policy.py").read_text()
        models=(ROOT/"src/ai_product_factory/models.py").read_text()
        backlog=(ROOT/"src/ai_product_factory/backlog_dispatcher.py").read_text()
        dispatch=(ROOT/"src/ai_product_factory/supabase_backlog_dispatch.py").read_text()
        provenance=(ROOT/"src/ai_product_factory/provenance_replay.py").read_text()
        migration=(ROOT/"supabase/migrations/20260929050701_factory_routing_policy_v2.sql").read_text()
        for marker in (
            "impacted_components",
            "impact_unknowns",
            "historical_repair_rate",
            "historical_direct_first_pass",
            "historical_codex_first_pass",
            "historical_codex_cost_ratio",
        ):
            self.assertIn(marker,models)
            self.assertIn(marker,backlog)
        self.assertIn('policy_version="v2"',policy)
        self.assertIn("Codex tem vantagem historica relevante de first-pass",policy)
        self.assertIn("Direct tem vantagem historica relevante de first-pass",policy)
        self.assertIn("custo historico do Codex e alto versus Direct",policy)
        self.assertIn("factory_record_dispatch_decision_v2",dispatch)
        self.assertIn("p_codex_reasons",dispatch)
        self.assertIn("p_gate_reasons",dispatch)
        self.assertIn('ROUTER_POLICY_VERSION="v2"',provenance)
        self.assertIn("routing_policy_version",migration)
        self.assertIn("codex_reasons",migration)
        self.assertIn("security invoker",migration)
        self.assertNotIn("merge_pull_request(",policy)



class CodeProvenanceAcceptanceTests(unittest.TestCase):
    def test_factory_commits_carry_only_safe_provenance_pointers(self):
        module=(ROOT/"src/ai_product_factory/commit_provenance.py").read_text()
        worker=(ROOT/"src/ai_product_factory/change_set_worker.py").read_text()
        integrator=(ROOT/"src/ai_product_factory/change_set_integrator.py").read_text()
        for marker in (
            "Factory-Run",
            "Factory-Change-Set",
            "Factory-Work-Unit",
            "Factory-Agent",
            "Factory-Context-SHA256",
        ):
            self.assertIn(marker,worker)
        self.assertIn("Factory-Change-Set",integrator)
        self.assertIn("Factory-Wave",integrator)
        self.assertIn("invalid provenance trailer value",module)
        self.assertIn("64-character lowercase hex hash",module)
        self.assertNotIn("context_packet",module)
        self.assertNotIn("authorization",worker.lower())
