import unittest
from unittest.mock import patch

from ai_product_factory.product_stage_executor import ProductStageExecutor
from ai_product_factory.runtime_auth import AuthKind
from ai_product_factory.runtime_cli import build_handler, require_paid_runtime_budget, run_alerts_once, run_ci_once, run_health_once


class RuntimeCliTests(unittest.TestCase):
    def test_runtime_builds_primary_handler_for_api_key(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}, clear=True):
            handler = build_handler()
        self.assertIsInstance(handler, ProductStageExecutor)

    def test_runtime_fails_before_claim_when_auth_is_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                build_handler()
        self.assertIn(AuthKind.NONE.value, str(ctx.exception))

    def test_unofficial_chatgpt_token_is_ignored_by_primary_runtime(self):
        with patch.dict("os.environ", {"CHATGPT_ACCESS_TOKEN": "x"}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                build_handler()
        self.assertIn(AuthKind.NONE.value, str(ctx.exception))

    def test_paid_runtime_budget_is_fail_closed_when_unconfigured(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(PermissionError):
                require_paid_runtime_budget()

    def test_paid_runtime_budget_accepts_explicit_bounded_reservation(self):
        env={"FACTORY_MODEL_BUDGET_USD":"5","FACTORY_MODEL_RESERVE_USD":"0.25","FACTORY_MODEL_KNOWN_SPEND_USD":"1"}
        with patch.dict("os.environ", env, clear=True):
            require_paid_runtime_budget()

    def test_health_is_side_effect_free_configuration_report(self):
        with patch.dict("os.environ", {"SUPABASE_URL":"https://example.supabase.co","SUPABASE_SERVICE_ROLE_KEY":"secret"}, clear=True):
            out=run_health_once()
        self.assertEqual(out["status"],"healthy")
        self.assertTrue(out["control_plane_configured"])
        self.assertFalse(out["primary_enabled"])
        self.assertFalse(out["budget_configured"])
        self.assertFalse(out["vercel_preview"]["ready"])
        self.assertFalse(out["github_alerts"]["ready"])

    def test_ci_followup_empty_queue_has_no_github_side_effect(self):
        queue=unittest.mock.MagicMock()
        queue.next_pending.return_value=None
        with patch("ai_product_factory.runtime_cli.SupabaseCIFollowupQueue",return_value=queue), patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github:
            out=run_ci_once()
        self.assertEqual(out,{"claimed":False,"status":"empty"})
        github.assert_not_called()
    def test_alert_mode_is_blocked_without_explicit_enable_and_config(self):
        with patch.dict("os.environ", {}, clear=True):
            out=run_alerts_once()
        self.assertEqual(out["status"],"blocked")
        self.assertEqual(out["published"],0)
        self.assertIn("GITHUB_TOKEN",out["missing"])
    def test_health_recognizes_modern_supabase_secret_key(self):
        env={"SUPABASE_URL":"https://example.supabase.co","SUPABASE_SECRET_KEY":"sb_secret_modern"}
        with patch.dict("os.environ", env, clear=True):
            out=run_health_once()
        self.assertTrue(out["control_plane_configured"])

if __name__ == "__main__":
    unittest.main()
