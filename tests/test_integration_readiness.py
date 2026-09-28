import unittest
from unittest.mock import patch

from ai_product_factory.integration_readiness import browser_evidence_readiness, github_alerts_readiness, github_vercel_preview_readiness, verified_preview_readiness, vercel_preview_readiness, supabase_project_readiness, supabase_project_write_readiness, supabase_provision_readiness


class IntegrationReadinessTests(unittest.TestCase):
    def test_vercel_is_disabled_and_not_ready_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            state = vercel_preview_readiness()
        self.assertFalse(state.enabled)
        self.assertFalse(state.configured)
        self.assertFalse(state.ready)
        self.assertIn("VERCEL_TOKEN", state.missing)

    def test_vercel_requires_explicit_enable_even_when_configured(self):
        env = {"VERCEL_TOKEN": "x"}
        with patch.dict("os.environ", env, clear=True):
            state = vercel_preview_readiness()
        self.assertTrue(state.configured)
        self.assertFalse(state.enabled)
        self.assertFalse(state.ready)

    def test_vercel_ready_only_with_flag_and_complete_config(self):
        env = {
            "FACTORY_VERCEL_PREVIEW_ENABLED": "true",
            "VERCEL_TOKEN": "x",
        }
        with patch.dict("os.environ", env, clear=True):
            self.assertTrue(vercel_preview_readiness().ready)


    def test_github_vercel_ready_with_github_token_and_enable(self):
        env={
            "FACTORY_VERCEL_PREVIEW_ENABLED":"true",
            "GITHUB_TOKEN":"x",
        }
        with patch.dict("os.environ",env,clear=True):
            self.assertTrue(github_vercel_preview_readiness().ready)

    def test_verified_preview_github_mode_needs_no_vercel_token(self):
        env={
            "FACTORY_VERCEL_PREVIEW_ENABLED":"true",
            "GITHUB_TOKEN":"x",
            "FACTORY_BROWSER_EVIDENCE_ENABLED":"true",
            "FACTORY_BROWSER_EVIDENCE_COMMAND_JSON":'["node","verify.mjs"]',
        }
        with patch.dict("os.environ",env,clear=True):
            state=verified_preview_readiness("github")
        self.assertTrue(state.ready)
        self.assertNotIn("VERCEL_TOKEN",state.missing)

    def test_github_alerts_ready_only_with_flag_and_config(self):
        env = {
            "FACTORY_GITHUB_ALERTS_ENABLED": "true",
            "GITHUB_TOKEN": "x",
            "FACTORY_ALERTS_GITHUB_REPOSITORY": "owner/repo",
        }
        with patch.dict("os.environ", env, clear=True):
            state = github_alerts_readiness()
        self.assertTrue(state.ready)
        self.assertEqual(state.missing, ())

    def test_browser_evidence_requires_explicit_enable_and_command(self):
        with patch.dict("os.environ", {"FACTORY_BROWSER_EVIDENCE_COMMAND_JSON":'["node","verify.mjs"]'}, clear=True):
            state=browser_evidence_readiness()
        self.assertTrue(state.configured)
        self.assertFalse(state.ready)

    def test_verified_preview_requires_both_adapters(self):
        env={
            "FACTORY_VERCEL_PREVIEW_ENABLED":"true",
            "VERCEL_TOKEN":"x",
            "FACTORY_BROWSER_EVIDENCE_ENABLED":"true",
            "FACTORY_BROWSER_EVIDENCE_COMMAND_JSON":'["node","verify.mjs"]',
        }
        with patch.dict("os.environ",env,clear=True):
            self.assertTrue(verified_preview_readiness().ready)

    def test_project_supabase_readiness_is_explicit_and_read_first(self):
        env={"FACTORY_PROJECT_SUPABASE_ENABLED":"true","FACTORY_PROJECT_SUPABASE_ACCESS_TOKEN":"x","FACTORY_PROJECT_SUPABASE_REF":"ref"}
        with patch.dict("os.environ",env,clear=True):
            self.assertTrue(supabase_project_readiness().ready)
            self.assertFalse(supabase_project_write_readiness().ready)

    def test_project_supabase_write_requires_separate_enable(self):
        env={"FACTORY_PROJECT_SUPABASE_ENABLED":"true","FACTORY_PROJECT_SUPABASE_WRITE_ENABLED":"true","FACTORY_PROJECT_SUPABASE_ACCESS_TOKEN":"x","FACTORY_PROJECT_SUPABASE_REF":"ref"}
        with patch.dict("os.environ",env,clear=True):
            self.assertTrue(supabase_project_write_readiness().ready)

    def test_supabase_provisioning_is_disabled_by_default(self):
        with patch.dict("os.environ",{},clear=True):
            self.assertFalse(supabase_provision_readiness().ready)

if __name__ == "__main__":
    unittest.main()
