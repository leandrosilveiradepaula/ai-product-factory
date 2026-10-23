import unittest
from unittest.mock import MagicMock

from ai_product_factory.greenfield_source_context import live_greenfield_source_context


class GreenfieldLiveSourceTests(unittest.TestCase):
    def setUp(self):
        self.project = {
            "project_kind": "greenfield", "repository": "owner/desk",
            "manifest": {
                "source": "factory-console", "onboarding_mode": "greenfield",
                "bootstrap_request_id": "7049a49e-1aaf-44e5-8048-a2c6452ddd5e",
                "continuation_request": {
                    "source": "github-owner", "summary": "Fix a real functional gap.",
                    "github": {"repository": "leandrosilveiradepaula/ai-product-factory",
                               "issue_number": 1055, "actor_id": 256917842},
                },
            },
        }
        self.github = MagicMock()
        self.github.repository = "owner/desk"
        self.github.get_branch_sha.return_value = "a"*40
        self.github.get_file_text.side_effect = lambda path,ref: {
            "README.md": "# Product",
            "package.json": '{"name":"desk"}',
        }[path]

    def test_pins_read_only_main_and_never_invents_candidate_pr(self):
        result=live_greenfield_source_context(
            project=self.project, context={"current_state_facts":{
                "github_access":{"status":"ready"}}},github=self.github,
        )
        live=result["current_state_facts"]["live_candidate"]
        self.assertEqual(live["sha"],"a"*40)
        self.assertIsNone(live["verified_open_pr"])
        self.assertEqual(live["branch"],"main")
        self.assertEqual(self.github.get_branch_sha.call_count,2)
        self.github.get_file_text.assert_any_call("README.md",ref="a"*40)
        self.github.get_file_text.assert_any_call("package.json",ref="a"*40)

    def test_forged_owner_or_bad_original_source_fail_before_read(self):
        for label in ("source","onboarding_mode"):
            project={**self.project,"manifest":{**self.project["manifest"],label:"forged"}}
            with self.subTest(label=label),self.assertRaises(PermissionError):
                live_greenfield_source_context(project=project,context={},github=self.github)
        project={**self.project,"manifest":{**self.project["manifest"],
            "continuation_request":{**self.project["manifest"]["continuation_request"],
                "github":{"repository":"evil/repo","issue_number":1055,"actor_id":256917842}}}}
        with self.assertRaises(PermissionError):
            live_greenfield_source_context(project=project,context={},github=self.github)
        self.github.get_file_text.assert_not_called()

    def test_missing_or_moving_source_fails_closed(self):
        self.github.get_branch_sha.side_effect=["a"*40,"b"*40]
        with self.assertRaisesRegex(PermissionError,"changed"):
            live_greenfield_source_context(project=self.project,context={},github=self.github)
        self.github.get_branch_sha.side_effect=None
        self.github.get_branch_sha.return_value="a"*40
        self.github.get_file_text.side_effect=lambda p,ref: ""
        with self.assertRaisesRegex(PermissionError,"missing"):
            live_greenfield_source_context(project=self.project,context={},github=self.github)
