from __future__ import annotations

from pathlib import Path
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
            "getRuns",
            "getRunDetail",
            "getWorkQueue",
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

    def test_vercel_deployments_are_bounded_to_console_branches(self):
        vercel = (ROOT / "apps/console/vercel.json").read_text()
        workflow = (ROOT / ".github/workflows/console.yml").read_text()
        operations = (ROOT / "docs/OPERATIONS.md").read_text()

        self.assertIn('"**": false', vercel)
        self.assertIn('"main": true', vercel)
        self.assertIn('"console/**": true', vercel)
        self.assertIn('"ignoreCommand"', vercel)
        self.assertIn('case "${GITHUB_HEAD_REF}" in', workflow)
        self.assertIn("console/*)", workflow)
        self.assertIn("Vercel deployment budget policy", operations)

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

if __name__ == "__main__":
    unittest.main()


def test_resource_limit_observability_is_fail_closed_and_secret_free():
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


def test_supabase_oauth_vault_backend_keeps_definers_private():
    migration=(ROOT/"supabase/migrations/20260928204500_factory_project_database_oauth_vault.sql").read_text()
    assert "create schema if not exists factory_private" in migration
    assert "security definer" in migration
    assert "factory_private.store_project_database_oauth" in migration
    assert "factory_private.get_project_database_oauth_tokens" in migration
    assert "factory_private.revoke_project_database_oauth" in migration
    assert "security invoker" in migration
    assert "last_verified_at=null" in migration
    assert "verified_at=null" not in migration
    assert "revoke all on all functions in schema factory_private from public,anon,authenticated" in migration
    assert "grant execute on function public.factory_get_project_database_oauth_tokens(uuid) to service_role" in migration
