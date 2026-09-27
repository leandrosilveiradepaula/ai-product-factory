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
            "preview",
            "alerts",
        ):
            self.assertIn(f"\n  {job}:", workflow)
        self.assertIn('cron: "17 * * * *"', workflow)
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
        }
        self.assertEqual(migration_names, expected_history)

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

        console_workflow = (ROOT / ".github/workflows/console.yml").read_text()
        self.assertIn("npm run typecheck", console_workflow)
        self.assertIn("npm run build", console_workflow)

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

    def test_agent_sql_benchmark_is_not_implicit_runtime_work(self):
        workflow = (ROOT / ".github/workflows/autonomous-runner.yml").read_text()
        codex = (ROOT / "src/ai_product_factory/codex_cli_producer.py").read_text()
        self.assertNotIn("63-question", workflow)
        self.assertIn("63-question benchmark", codex)


if __name__ == "__main__":
    unittest.main()
