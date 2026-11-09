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


if __name__ == "__main__":
    unittest.main()
