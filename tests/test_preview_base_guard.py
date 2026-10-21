import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from ai_product_factory.preview_base_guard import (
    _ordered_line_subset, verify_preview_base_compatibility,
)


OLD = "a"*40
NEW = "b"*40
HEAD = "c"*40
PATH = ".github/workflows/crm-validation.yml"
ORIGINAL = "name: CRM validation\non:\n  pull_request:\n    branches:\n      - main\n"
CURRENT = "name: CRM validation\non:\n  pull_request:\n    branches:\n      - main\n      - 'preview/**'\n"
CANDIDATE = "name: CRM validation\non:\n  push:\n    branches:\n      - 'factory/change-set-*'\n  pull_request:\n    branches:\n      - main\n      - 'preview/**'\n"


def github_for(base_ref="preview/hardening-release-candidate"):
    github = MagicMock()
    github.get_branch_sha.return_value = NEW
    github.compare_commits.return_value = {
        "status": "ahead", "ahead_by": 1, "behind_by": 0,
        "files": [PATH],
    }
    texts = {OLD: ORIGINAL, NEW: CURRENT, HEAD: CANDIDATE}
    github.get_file_text.side_effect = lambda path, ref: texts[ref]
    pr = SimpleNamespace(base_ref=base_ref, base_sha=OLD, head_sha=HEAD)
    return github, pr


class PreviewBaseGuardTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        self._control=patch("ai_product_factory.runtime_cli._assert_project_followup",return_value=1)
        self._control.start()
        self.addCleanup(self._control.stop)
        self._preview_cursor=patch("ai_product_factory.runtime_cli.SupabaseFollowupFairCursor")
        mock_cursor=self._preview_cursor.start()
        mock_cursor.return_value.read_offset.return_value=0
        self.addCleanup(self._preview_cursor.stop)

    def test_exact_base_requires_no_comparison_or_content_reads(self):
        github, pr = github_for()
        github.get_branch_sha.return_value = OLD
        self.assertEqual(verify_preview_base_compatibility(github, pr), {})
        github.compare_commits.assert_not_called()
        github.get_file_text.assert_not_called()

    def test_additive_workflow_change_already_in_candidate_is_compatible(self):
        github, pr = github_for()
        receipt = verify_preview_base_compatibility(github, pr)
        self.assertEqual(receipt["verification_mode"], "preview_base_additive_workflow_subsequence")
        self.assertEqual(receipt["candidate_commit"], HEAD)
        self.assertEqual(receipt["current_base_sha"], NEW)
        self.assertEqual(receipt["changed_files"], [PATH])
        self.assertEqual(receipt["added_lines"], 1)
        self.assertEqual(github.get_branch_sha.call_count, 2)
        self.assertEqual(github.get_file_text.call_count, 3)

    def test_preview_probe_handles_benign_workflow_base_advance(self):
        from unittest.mock import patch
        from ai_product_factory.runtime_cli import run_preview_probe_once
        github, pr = github_for()
        pr.state = "open"
        pr.merged = False
        github.get_pull_request.return_value = pr
        github.get_pull_request_files.return_value = ("src/services/SettingsService.ts",)
        queue = MagicMock()
        queue.next_pending.return_value = SimpleNamespace(
            run_id="crm-run", repository="owner/crm", pr_number=180,
            candidate_commit=HEAD,
            manifest={"preview":{"required":False,"reason":"backend-only"}},
        )
        with patch("ai_product_factory.runtime_cli.SupabasePreviewFollowupQueue",
                   return_value=queue), patch(
                   "ai_product_factory.runtime_cli.GitHubRestAdapter",
                   return_value=github):
            result = run_preview_probe_once()
        self.assertEqual(result["status"],"ready")
        self.assertFalse(result["preview_required"])
        github.get_pull_request_files.assert_called_once_with(180)

    def test_non_preview_base_remains_fail_closed(self):
        github, pr = github_for("main")
        with self.assertRaisesRegex(RuntimeError, "PR base is stale"):
            verify_preview_base_compatibility(github, pr)
        github.compare_commits.assert_not_called()

    def test_moved_source_or_diverged_base_is_rejected(self):
        for bad_comparison in (
            {"status":"diverged","behind_by":1,"ahead_by":1,"files":[PATH]},
            {"status":"ahead","behind_by":0,"ahead_by":2,"files":[PATH]},
            {"status":"ahead","behind_by":0,"ahead_by":1,"files":["src/SettingsService.ts"]},
            {"status":"ahead","behind_by":0,"ahead_by":1,"files":[]},
            {"status":"ahead","behind_by":0,"ahead_by":1,"files":[PATH]*4},
        ):
            with self.subTest(change=bad_comparison):
                github, pr = github_for()
                github.compare_commits.return_value=bad_comparison
                with self.assertRaisesRegex(RuntimeError,"PR base is stale"):
                    verify_preview_base_compatibility(github,pr)

    def test_base_change_not_present_in_head_is_rejected(self):
        github, pr = github_for()
        github.get_file_text.side_effect=lambda path,ref: {
            OLD:ORIGINAL,NEW:CURRENT,HEAD:ORIGINAL
        }[ref]
        with self.assertRaisesRegex(RuntimeError,"PR base is stale"):
            verify_preview_base_compatibility(github,pr)

    def test_replace_or_remove_workflow_line_is_rejected(self):
        github, pr = github_for()
        github.get_file_text.side_effect=lambda path,ref: {
            OLD:ORIGINAL,
            NEW:CURRENT.replace("      - main\n","      - release\n"),
            HEAD:CANDIDATE,
        }[ref]
        with self.assertRaisesRegex(RuntimeError,"PR base is stale"):
            verify_preview_base_compatibility(github,pr)

    def test_second_base_read_detects_concurrent_movement(self):
        github, pr = github_for()
        github.get_branch_sha.side_effect=[NEW, "d"*40]
        with self.assertRaisesRegex(RuntimeError,"PR base is stale"):
            verify_preview_base_compatibility(github,pr)

    def test_workflow_line_subsequence_preserves_order_and_whitespace(self):
        self.assertTrue(_ordered_line_subset(ORIGINAL,CURRENT))
        self.assertTrue(_ordered_line_subset(CURRENT,CANDIDATE))
        self.assertFalse(_ordered_line_subset(CURRENT,ORIGINAL))
        self.assertFalse(_ordered_line_subset("a\nb\n","b\na\n"))
        self.assertFalse(_ordered_line_subset("  x\n"," x\n"))


if __name__ == "__main__":
    unittest.main()
