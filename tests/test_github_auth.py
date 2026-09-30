import unittest
from unittest.mock import patch

from ai_product_factory.github_auth import resolve_github_token


class GitHubAuthTests(unittest.TestCase):
    def test_explicit_token_wins(self):
        with patch.dict("os.environ",{"FACTORY_GITHUB_TOKEN":"factory","GITHUB_TOKEN":"native"},clear=True):
            self.assertEqual(resolve_github_token("owner/repo",explicit_token="explicit"),"explicit")

    def test_factory_token_is_valid_for_cross_repo_actions(self):
        env={
            "GITHUB_ACTIONS":"true",
            "GITHUB_REPOSITORY":"owner/factory",
            "GITHUB_TOKEN":"native",
            "FACTORY_GITHUB_TOKEN":"factory",
        }
        with patch.dict("os.environ",env,clear=True):
            self.assertEqual(resolve_github_token("owner/target"),"factory")

    def test_native_actions_token_is_valid_for_current_repo(self):
        env={"GITHUB_ACTIONS":"true","GITHUB_REPOSITORY":"owner/repo","GITHUB_TOKEN":"native"}
        with patch.dict("os.environ",env,clear=True):
            self.assertEqual(resolve_github_token("owner/repo"),"native")


    def test_same_repo_actions_prefers_native_over_cross_repo_factory_token(self):
        env={
            "GITHUB_ACTIONS":"true",
            "GITHUB_REPOSITORY":"owner/factory",
            "GITHUB_TOKEN":"native-write",
            "FACTORY_GITHUB_TOKEN":"cross-repo-readonly",
        }
        with patch.dict("os.environ",env,clear=True):
            self.assertEqual(resolve_github_token("owner/factory"),"native-write")

    def test_same_repo_actions_fails_closed_without_native_even_if_factory_token_exists(self):
        env={
            "GITHUB_ACTIONS":"true",
            "GITHUB_REPOSITORY":"owner/factory",
            "FACTORY_GITHUB_TOKEN":"cross-repo-readonly",
        }
        with patch.dict("os.environ",env,clear=True):
            with self.assertRaises(ValueError):
                resolve_github_token("owner/factory")

    def test_native_actions_token_rejects_cross_repo(self):
        env={"GITHUB_ACTIONS":"true","GITHUB_REPOSITORY":"owner/factory","GITHUB_TOKEN":"native"}
        with patch.dict("os.environ",env,clear=True):
            with self.assertRaises(PermissionError):
                resolve_github_token("owner/target")

    def test_native_token_outside_actions_can_be_user_managed_token(self):
        with patch.dict("os.environ",{"GITHUB_TOKEN":"managed"},clear=True):
            self.assertEqual(resolve_github_token("owner/target"),"managed")

    def test_missing_token_fails_closed(self):
        with patch.dict("os.environ",{},clear=True):
            with self.assertRaises(ValueError):
                resolve_github_token("owner/repo")


if __name__=="__main__":
    unittest.main()
