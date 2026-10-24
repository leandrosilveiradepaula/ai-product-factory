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
                    "source": "github-owner",
                    "summary": "Fix a real functional gap in src/domain/ticket.ts and tests/ticket/ticket-domain.test.ts.",
                    "github": {"repository": "leandrosilveiradepaula/ai-product-factory",
                               "issue_number": 1055, "actor_id": 256917842},
                },
            },
        }
        self.github = MagicMock()
        self.github.repository = "owner/desk"
        self.github.get_branch_sha.return_value = "a"*40
        self.github.list_file_paths.return_value = (
            "README.md", "package.json", "src/domain/ticket.ts",
            "tests/ticket/ticket-domain.test.ts",
        )
        self.github.get_file_text.side_effect = lambda path,ref: {
            "README.md": "# Product",
            "package.json": '{"name":"desk"}',
            "src/domain/ticket.ts": "export const validTransition = true;",
            "tests/ticket/ticket-domain.test.ts": "import test from 'node:test';",
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
        self.assertEqual(live["source_evidence"]["status"],"bounded_source_inspected")
        self.assertEqual(live["source_evidence"]["assessed_commit"],"a"*40)
        self.assertEqual(len(live["source_evidence"]["inspected_files"]),2)
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

    def test_request_without_explicit_source_does_not_spend_on_blind_reconciliation(self):
        manifest={**self.project["manifest"],
                  "continuation_request": {
                      **self.project["manifest"]["continuation_request"],
                      "summary":"Find any missing functionality in the product.",
                  }}
        with self.assertRaisesRegex(PermissionError,"explicit current source paths"):
            live_greenfield_source_context(
                project={**self.project,"manifest":manifest},
                context={},github=self.github,
            )
        self.github.list_file_paths.assert_not_called()

    def test_secret_in_requested_source_fails_closed(self):
        orig=self.github.get_file_text.side_effect
        self.github.get_file_text.side_effect=lambda path,ref: (
            "sk-proj-THISISNOTAREALTOKEN123456789abcdefghi"
            if path=="src/domain/ticket.ts" else orig(path,ref)
        )
        with self.assertRaisesRegex(PermissionError,"potential secret"):
            live_greenfield_source_context(project=self.project,context={},github=self.github)

    def test_requested_code_missing_is_not_a_scope_grant(self):
        self.github.list_file_paths.return_value=("README.md","package.json")
        with self.assertRaisesRegex(PermissionError,"explicit current source paths"):
            live_greenfield_source_context(project=self.project,context={},github=self.github)

