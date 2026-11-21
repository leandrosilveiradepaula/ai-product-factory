"""Native Product Stage GitHub App read-auth, isolated from worker token env."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue


class ProductStageJitTests(unittest.TestCase):
    def setUp(self):
        self.project={"id":"11111111-1111-1111-1111-111111111111",
                      "project_key":"dark-channel-studio",
                      "repository":"leandrosilveiradepaula/dark-channel-studio",
                      "project_kind":"greenfield",
                      "manifest":{"source":"factory-console",
                                  "onboarding_mode":"greenfield"}}

    def test_native_jit_scopes_to_project_repo_and_hides_token(self):
        from ai_product_factory import supabase_runtime_queue as q
        settings={
            "GITHUB_ACTIONS":"false",
            "FACTORY_PRIMARY_MODEL_PROVIDER":"infodive_ibm_cloud",
            "FACTORY_INFODIVE_VPS_WORKER_ENABLED":"true",
        }
        with patch.dict(os.environ,settings,clear=True), \
             patch("ai_product_factory.vps_github_app.mint_vps_github_app_token",
                   return_value="opaque-test-installation-token") as mint, \
             patch.object(q,"GitHubRestAdapter") as adapter:
            result=SupabaseRuntimeQueue._github_for_project(self.project)
        mint.assert_called_once_with(self.project["repository"],
                                     self.project["project_key"])
        adapter.assert_called_once_with(
            repository=self.project["repository"],token="opaque-test-installation-token"
        )
        self.assertIs(result,adapter.return_value)
        self.assertNotIn("opaque-test-installation-token",os.environ.values())

    def test_wrong_repo_or_project_blocks_before_credential_mint(self):
        from ai_product_factory import supabase_runtime_queue as q
        env={"GITHUB_ACTIONS":"false",
             "FACTORY_PRIMARY_MODEL_PROVIDER":"infodive_ibm_cloud",
             "FACTORY_INFODIVE_VPS_WORKER_ENABLED":"true"}
        with patch.dict(os.environ,env,clear=True), \
             patch("ai_product_factory.vps_github_app.mint_vps_github_app_token") as mint:
            for project in ({**self.project,"project_key":""},
                            {**self.project,"repository":""},
                            {**self.project,"id":None}):
                with self.subTest(project=project):
                    with self.assertRaises(PermissionError):
                        SupabaseRuntimeQueue._github_for_project(project)
            mint.assert_not_called()

    def test_sanitized_auth_error_never_exposes_credential(self):
        from ai_product_factory.vps_github_app import VpsGitHubAppUnavailable
        env={"GITHUB_ACTIONS":"false",
             "FACTORY_PRIMARY_MODEL_PROVIDER":"infodive_ibm_cloud",
             "FACTORY_INFODIVE_VPS_WORKER_ENABLED":"true"}
        with patch.dict(os.environ,env,clear=True), \
             patch("ai_product_factory.vps_github_app.mint_vps_github_app_token",
                   side_effect=VpsGitHubAppUnavailable("control plane refused")):
            with self.assertRaisesRegex(
                    PermissionError,"native Product Stage GitHub App unavailable") as cm:
                SupabaseRuntimeQueue._github_for_project(self.project)
            self.assertNotIn("control plane refused",str(cm.exception))

    def test_actions_preserves_original_git_hub_auth_path(self):
        from ai_product_factory import supabase_runtime_queue as q
        with patch.dict(os.environ,{"GITHUB_ACTIONS":"true"},clear=True), \
             patch("ai_product_factory.vps_github_app.mint_vps_github_app_token") as mint, \
             patch.object(q,"GitHubRestAdapter") as adapter:
            SupabaseRuntimeQueue._github_for_project(self.project)
        mint.assert_not_called()
        adapter.assert_called_once_with(repository=self.project["repository"])


if __name__=="__main__":
    unittest.main()
