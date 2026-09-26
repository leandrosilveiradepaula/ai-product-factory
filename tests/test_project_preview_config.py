import unittest
from unittest.mock import patch

from ai_product_factory.project_preview_config import resolve_project_vercel_preview_config


class Tests(unittest.TestCase):
    def test_manifest_config_wins_and_repository_drives_source(self):
        manifest={"preview":{"provider":"vercel","team_id":"team_1","project_name":"console"}}
        with patch.dict("os.environ",{},clear=True):
            cfg=resolve_project_vercel_preview_config(repository="owner/repo",manifest=manifest)
        self.assertEqual(cfg.team_id,"team_1")
        self.assertEqual(cfg.project_name,"console")
        self.assertEqual((cfg.github_org,cfg.github_repo),("owner","repo"))

    def test_env_fallback_is_supported_without_hardcoding_repository(self):
        env={"FACTORY_VERCEL_TEAM_ID":"team_env","FACTORY_VERCEL_PROJECT_NAME":"project_env"}
        with patch.dict("os.environ",env,clear=True):
            cfg=resolve_project_vercel_preview_config(repository="acme/web",manifest={})
        self.assertEqual(cfg.team_id,"team_env")
        self.assertEqual(cfg.project_name,"project_env")
        self.assertEqual((cfg.github_org,cfg.github_repo),("acme","web"))

    def test_missing_project_config_fails_closed(self):
        with patch.dict("os.environ",{},clear=True):
            with self.assertRaises(ValueError):
                resolve_project_vercel_preview_config(repository="owner/repo",manifest={})

    def test_unsupported_provider_fails_closed(self):
        manifest={"preview":{"provider":"other","team_id":"x","project_name":"y"}}
        with self.assertRaises(ValueError):
            resolve_project_vercel_preview_config(repository="owner/repo",manifest=manifest)


if __name__=="__main__": unittest.main()
