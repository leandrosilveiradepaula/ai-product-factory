import unittest
from unittest.mock import MagicMock

from ai_product_factory.candidate_source_evidence import (
    _latest_scope, collect_candidate_source_evidence,
)


SHA = "a" * 40


class CandidateSourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tick = chr(96)
        self.doc = (
            "## Authorized task (2026-10-01): old work\n"
            + self.tick + "src/legacy.py" + self.tick + "\n"
            + "## Additional authorized task (2026-10-10): pipeline integrity\n"
            + "Only " + self.tick + "src/services/SettingsService.ts" + self.tick
            + ", " + self.tick + "src/services/SettingsService.stage-integrity.test.ts"
            + self.tick + " and " + self.tick + "src/missing.ts" + self.tick + ".\n"
            + "## External gate\n"
            + self.tick + "src/secret.py" + self.tick + "\n"
        )
        self.github = MagicMock()
        self.github.list_file_paths.return_value = (
            "src/legacy.py", "src/services/SettingsService.ts",
            "src/services/SettingsService.stage-integrity.test.ts",
        )
        self.github.get_file_text.side_effect = lambda path, ref: (
            "export function verified() { return true; }\n" if path.endswith(".ts")
            else "test('code', () => true)\n"
        )

    def test_select_only_latest_authorized_scope(self):
        heading, paths = _latest_scope(self.doc)
        self.assertIn("2026-10-10", heading)
        self.assertEqual(paths, [
            "src/services/SettingsService.ts",
            "src/services/SettingsService.stage-integrity.test.ts",
            "src/missing.ts",
        ])
        result = collect_candidate_source_evidence(self.doc, self.github, sha=SHA)
        self.assertEqual(result["assessed_commit"], SHA)
        self.assertEqual(result["missing_paths"], ["src/missing.ts"])
        self.assertEqual(len(result["inspected_files"]), 2)
        self.assertTrue(all(row["assessed_commit"] == SHA for row in result["inspected_files"]))
        self.github.list_file_paths.assert_called_once_with(ref=SHA)
        self.github.get_file_text.assert_any_call(
            "src/services/SettingsService.ts", ref=SHA
        )
        self.assertNotIn("src/legacy.py", [
            call.args[0] for call in self.github.get_file_text.call_args_list
        ])

    def test_refuses_path_traversal_and_sensitive_extensions(self):
        t = self.tick
        doc = ("## Authorized task (2026-10-10): guarded\n"
               + t + "src/../credentials.py" + t + " "
               + t + ".env" + t + " "
               + t + "src/app/actions.ts" + t)
        heading, paths = _latest_scope(doc)
        self.assertEqual(paths, ["src/app/actions.ts"])
        self.assertIn("guarded", heading)

    def test_no_source_scope_never_calls_github(self):
        result = collect_candidate_source_evidence(
            "# CURRENT_TASK\nNo code paths permitted.", self.github, sha=SHA
        )
        self.assertEqual(result["status"], "no_scoped_source_paths")
        self.github.list_file_paths.assert_not_called()
        self.github.get_file_text.assert_not_called()

    def test_truncation_is_truthful_and_bound(self):
        self.github.get_file_text.side_effect = lambda path, ref: "a" * 50000
        result = collect_candidate_source_evidence(self.doc, self.github, sha=SHA)
        self.assertFalse(result["inspected_files"][0]["complete"])
        self.assertLess(len(result["inspected_files"][0]["content"]), 14500)
        self.assertIn("OMITTED MIDDLE", result["inspected_files"][0]["content"])

    def test_sensitive_source_blocks_before_model_context(self):
        self.github.get_file_text.side_effect = lambda path, ref: (
            "sk-proj-abcdefghijklmnopqrstuv0123456"
        )
        with self.assertRaisesRegex(PermissionError, "secret material"):
            collect_candidate_source_evidence(self.doc, self.github, sha=SHA)

    def test_invalid_ref_fails_before_git_access(self):
        with self.assertRaises(PermissionError):
            collect_candidate_source_evidence(self.doc, self.github, sha="main")
        self.github.list_file_paths.assert_not_called()


if __name__ == "__main__":
    unittest.main()
