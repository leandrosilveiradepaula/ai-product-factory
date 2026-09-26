import unittest
from unittest.mock import patch

from ai_product_factory.integration_readiness import github_alerts_readiness, vercel_preview_readiness


class IntegrationReadinessTests(unittest.TestCase):
    def test_vercel_is_disabled_and_not_ready_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            state = vercel_preview_readiness()
        self.assertFalse(state.enabled)
        self.assertFalse(state.configured)
        self.assertFalse(state.ready)
        self.assertIn("VERCEL_TOKEN", state.missing)

    def test_vercel_requires_explicit_enable_even_when_configured(self):
        env = {
            "VERCEL_TOKEN": "x",
            "FACTORY_VERCEL_TEAM_ID": "team",
            "FACTORY_VERCEL_PROJECT_NAME": "project",
            "FACTORY_VERCEL_GITHUB_ORG": "owner",
            "FACTORY_VERCEL_GITHUB_REPO": "repo",
        }
        with patch.dict("os.environ", env, clear=True):
            state = vercel_preview_readiness()
        self.assertTrue(state.configured)
        self.assertFalse(state.enabled)
        self.assertFalse(state.ready)

    def test_vercel_ready_only_with_flag_and_complete_config(self):
        env = {
            "FACTORY_VERCEL_PREVIEW_ENABLED": "true",
            "VERCEL_TOKEN": "x",
            "FACTORY_VERCEL_TEAM_ID": "team",
            "FACTORY_VERCEL_PROJECT_NAME": "project",
            "FACTORY_VERCEL_GITHUB_ORG": "owner",
            "FACTORY_VERCEL_GITHUB_REPO": "repo",
        }
        with patch.dict("os.environ", env, clear=True):
            self.assertTrue(vercel_preview_readiness().ready)

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


if __name__ == "__main__":
    unittest.main()
