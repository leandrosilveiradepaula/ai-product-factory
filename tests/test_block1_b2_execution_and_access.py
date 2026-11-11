"""B2 negative runtime admission and isolated SQL authorization contracts."""
from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from ai_product_factory import runtime_cli as cli
from ai_product_factory.runtime_auth import AuthKind, RuntimeAuthResolver

ROOT = Path(__file__).resolve().parents[1]


class RuntimeAdmissionBoundaries(unittest.TestCase):
    def test_all_three_entrypoints_block_before_external_clients(self):
        with patch.dict(os.environ, {
            "FACTORY_PRIMARY_MODEL_ENABLED": "false",
            "FACTORY_CODEX_ENABLED": "false",
            "OPENAI_API_KEY": "synthetic-not-for-network",
            "FACTORY_GITHUB_TOKEN": "synthetic-not-for-network",
        }, clear=True):
            with patch.object(cli, "SupabaseRuntimeQueue",
                              side_effect=AssertionError("queue contacted")), \
                 patch.object(cli, "SupabaseAgentScheduler",
                              side_effect=AssertionError("scheduler contacted")), \
                 patch.object(cli, "SupabaseCodexRunQueue",
                              side_effect=AssertionError("Codex queue contacted")), \
                 patch.object(cli, "OpenAIResponsesProvider",
                              side_effect=AssertionError("model contacted")):
                for lane in (cli.run_product_once, cli.run_direct_once, cli.run_codex_once):
                    with self.subTest(lane=lane.__name__):
                        result = lane("synthetic-worker")
                        self.assertEqual(result["status"], "blocked")
                        self.assertIs(result["claimed"], False)

    def test_unknown_paid_budget_denies_product_and_direct_before_claim(self):
        with patch.dict(os.environ, {
            "FACTORY_PRIMARY_MODEL_ENABLED": "true",
            "FACTORY_PRIMARY_AUTH_MODE": "api_key",
            "OPENAI_API_KEY": "synthetic-not-for-network",
        }, clear=True):
            with patch.object(cli, "require_paid_runtime_budget",
                              side_effect=PermissionError("b2_budget_unknown")), \
                 patch.object(cli, "SupabaseRuntimeQueue",
                              side_effect=AssertionError("queue contacted")), \
                 patch.object(cli, "SupabaseAgentScheduler",
                              side_effect=AssertionError("scheduler contacted")), \
                 patch.object(cli, "OpenAIResponsesProvider",
                              side_effect=AssertionError("model contacted")):
                for lane in (cli.run_product_once, cli.run_direct_once):
                    with self.subTest(lane=lane.__name__):
                        result = lane("synthetic-worker")
                        self.assertEqual(result["status"], "blocked")
                        self.assertIn("b2_budget_unknown", result["error"])
                        self.assertIs(result["claimed"], False)

    def test_codex_missing_cross_repo_token_or_partial_wif_denies_claim(self):
        for cfg in (
            {"FACTORY_CODEX_ENABLED": "true"},
            {"FACTORY_CODEX_ENABLED": "true",
             "FACTORY_GITHUB_TOKEN": "synthetic",
             "OPENAI_FEDERATION_RULE_ID": "synthetic",
             "CODEX_ACCESS_TOKEN": "synthetic"},
        ):
            with self.subTest(keys=tuple(cfg)), \
                 patch.dict(os.environ, cfg, clear=True), \
                 patch.object(cli, "SupabaseCodexRunQueue",
                              side_effect=AssertionError("Codex queue contacted")):
                result = cli.run_codex_once("synthetic-worker")
                self.assertEqual(result["status"], "blocked")
                self.assertIs(result["claimed"], False)

    def test_unofficial_chatgpt_token_never_grants_primary_or_codex(self):
        with patch.dict(os.environ, {
            "CHATGPT_ACCESS_TOKEN": "synthetic",
            "FACTORY_PRIMARY_MODEL_ENABLED": "true",
            "FACTORY_CODEX_ENABLED": "true",
            "FACTORY_GITHUB_TOKEN": "synthetic",
        }, clear=True):
            auth = RuntimeAuthResolver()
            self.assertEqual(auth.resolve_primary_api().kind, AuthKind.NONE)
            self.assertEqual(auth.resolve_codex().kind, AuthKind.NONE)


class IsolatedRoleEvidenceContract(unittest.TestCase):
    def test_b2_sql_runner_checks_loopback_before_connecting(self):
        src = (ROOT / "scripts/verify_block1_console_auth_rls_postgres.py").read_text()
        self.assertIn("def scoped_dsn()", src)
        self.assertIn("factory_project_control_test", src)
        self.assertIn("127.0.0.1", src)
        self.assertLess(src.index("dsn = scoped_dsn()"), src.index("psycopg.connect(dsn"))
        self.assertIn("isolated_sql_role_policy_not_production_jwt_or_full_tenant_auth", src)
        self.assertIn("policy_sql()", src)
        self.assertIn("def expect_denied(", src)
        self.assertIn('"42501"', src)
        self.assertIn("factory_upsert_console_operator", src)
        self.assertIn("b2_cross_operator_read_leaked", src)
        self.assertIn("for role in (\"anon\", \"authenticated\")", src)
        self.assertIn("production_writes", src)
        self.assertIn("all_authn_authz_certified", src)

    def test_b2_scripts_and_migrations_are_covered_by_pg_qa(self):
        workflow = (ROOT / ".github/workflows/manual-project-control-postgres.yml").read_text()
        self.assertIn("python scripts/verify_block1_console_auth_rls_postgres.py", workflow)
        self.assertIn("scripts/verify_block1_console_auth_rls_postgres.py", workflow)
        self.assertIn("tests/test_block1_b2_execution_and_access.py", workflow)
        self.assertIn("20260925232713_factory_console_auth_and_gate_resolution.sql", workflow)
        self.assertIn("20260925234331_factory_console_operator_admin.sql", workflow)
        self.assertIn('FACTORY_CONTROL_TEST_ISOLATED: "true"', workflow)


class DirectIssueBoundaryEvidence(unittest.TestCase):
    """Execute real Direct worker with sentinels; no network, models or GitHub writes."""

    def test_blocked_and_decision_outputs_never_create_issue_or_pr(self):
        from ai_product_factory.execution_worker import (
            DirectExecutionItem, DirectExecutionWorker, ImplementationArtifact,
            ImplementationBlocked,
        )

        class Producer:
            def __init__(self, artifact):
                self.artifact = artifact

            def produce(self, item):
                return self.artifact

        class Materializer:
            def __init__(self):
                self.calls = 0

            def ensure_issue(self, item):
                self.calls += 1
                raise AssertionError("blocked work created an issue")

        class Delivery:
            def start_issue(self, **kwargs):
                raise AssertionError("blocked work reached delivery")

        item = DirectExecutionItem(
            run_id="synthetic-run", task_id="synthetic-task",
            project_key="synthetic", repository="owner/repo",
            issue_number=None, title="Synthetic", description="No work",
            branch="synthetic/blocked",
        )
        for reason, decision in (
            ("blocked", None),
            ("demo", None),
            ("", None),
            (None, {"decision_kind": "material_requirement_change"}),
        ):
            with self.subTest(reason=reason, decision=decision):
                artifact = ImplementationArtifact(
                    "# Plan", {"app.py": "content"}, "feat: x", "PR", "body",
                    blocked_reason=reason, decision_needed=decision,
                )
                materializer = Materializer()
                worker = DirectExecutionWorker(
                    loop=Delivery(), producer=Producer(artifact),
                    issue_materializer=materializer,
                )
                with self.assertRaises(ImplementationBlocked):
                    worker.execute(item)
                self.assertEqual(materializer.calls, 0)


class ReleaseObserverCannotAutoMerge(unittest.TestCase):
    """Execute the real release entrypoint with fail-fast fake boundaries.

    Neither a pending human gate nor a changed PR candidate may reach any
    GitHub mutation, privileged Control Plane write, or production release.
    This is bounded executable B2 evidence, not live end-to-end certification.
    """

    def test_candidate_drift_denied_before_reconciliation_or_mutation(self):
        from types import SimpleNamespace
        candidate = "a" * 40
        observed = "b" * 40
        item = SimpleNamespace(
            repository="leandrosilveiradepaula/crm-infodive",
            run_id="synthetic-release-run", pr_number=123,
            candidate_commit=candidate, project_id="synthetic-project",
        )
        pr = SimpleNamespace(head_sha=observed)
        queue = type("Queue", (), {"next_pending": lambda self: item})
        github = type("Github", (), {"get_pull_request": lambda self, number: pr})
        with patch.object(cli, "SupabaseReleaseFollowupQueue", queue), \
             patch.object(cli, "_assert_project_followup"), \
             patch.object(cli, "GitHubRestAdapter", return_value=github()), \
             patch.object(cli, "SupabaseProjectReleaseReconciler",
                          side_effect=AssertionError("reconciler contacted")), \
             patch.object(cli, "SupabaseDeliveryStore",
                          side_effect=AssertionError("delivery store contacted")), \
             patch.object(cli, "SupabaseTraceabilityStore",
                          side_effect=AssertionError("traceability write")), \
             patch.object(cli, "SupabaseReleasePolicyStore",
                          side_effect=AssertionError("release write")):
            result = cli.run_release_once()
        self.assertEqual(result["status"], "candidate_drift_blocked")
        self.assertEqual(result["recorded_candidate_commit"], candidate)
        self.assertEqual(result["observed_pr_head"], observed)

    def test_unmerged_preview_never_observed_as_release(self):
        from types import SimpleNamespace
        sha = "c" * 40
        item = SimpleNamespace(
            repository="leandrosilveiradepaula/crm-infodive",
            run_id="synthetic-release-run", pr_number=123,
            candidate_commit=sha, merge_sha=None,
            release_source="delivery",
        )
        pr = SimpleNamespace(
            head_sha=sha, base_ref="preview/candidate",
            merged=False,
        )
        queue = type("Queue", (), {"next_pending": lambda self: item})
        github = type("Github", (), {"get_pull_request": lambda self, number: pr})
        with patch.object(cli, "SupabaseReleaseFollowupQueue", queue), \
             patch.object(cli, "_assert_project_followup"), \
             patch.object(cli, "GitHubRestAdapter", return_value=github()), \
             patch.object(cli, "SupabaseProjectReleaseReconciler",
                          side_effect=AssertionError("reconciler contacted")), \
             patch.object(cli, "SupabaseDeliveryStore",
                          side_effect=AssertionError("delivery store contacted")), \
             patch.object(cli, "SupabaseTraceabilityStore",
                          side_effect=AssertionError("traceability write")):
            result = cli.run_release_once()
        self.assertEqual(result["status"], "awaiting_nonproduction_merge")
        self.assertNotIn("merge_sha", result)

    def test_unmerged_production_pr_requires_manual_merge(self):
        from types import SimpleNamespace
        sha = "d" * 40
        item = SimpleNamespace(
            repository="leandrosilveiradepaula/crm-infodive",
            run_id="synthetic-release-run", pr_number=123,
            candidate_commit=sha, merge_sha=None,
            release_source="delivery", issue_number=123,
            branch="factory/probe", project_id="synthetic-project",
        )
        pr = SimpleNamespace(
            head_sha=sha, base_ref="main", merged=False,
            number=123,
        )
        issue = SimpleNamespace(number=123)
        class Github:
            def get_pull_request(self, number):
                return pr
            def get_issue(self, number):
                return issue
            def close_issue(self, number):
                raise AssertionError("issue closed before manual merge")
            def merge_pull_request(self, *args, **kwargs):
                raise AssertionError("automatic production merge")
        class Reconciler:
            def require_atomic_capability(self):
                return None
        class Store:
            def update_run_status(self, run_id, status, **kwargs):
                self.status = status
                if status != "awaiting_release":
                    raise AssertionError("false release status")
            def record_tool_usage(self, **kwargs):
                raise AssertionError("premature GitHub usage")
            def record_audit_event(self, **kwargs):
                raise AssertionError("premature release audit")
        store = Store()
        queue = type("Queue", (), {"next_pending": lambda self: item})
        with patch.object(cli, "SupabaseReleaseFollowupQueue", queue), \
             patch.object(cli, "_assert_project_followup"), \
             patch.object(cli, "GitHubRestAdapter", return_value=Github()), \
             patch.object(cli, "SupabaseProjectReleaseReconciler", Reconciler), \
             patch.object(cli, "SupabaseDeliveryStore", return_value=store), \
             patch.object(cli, "SupabaseTraceabilityStore",
                          side_effect=AssertionError("traceability write")), \
             patch.object(cli, "SupabaseReleasePolicyStore",
                          side_effect=AssertionError("released without merge")):
            result = cli.run_release_once()
        self.assertEqual(result["status"], "awaiting_release")
        self.assertEqual(store.status, "awaiting_release")
        self.assertNotIn("merge_sha", result)


if __name__ == "__main__":
    unittest.main()
