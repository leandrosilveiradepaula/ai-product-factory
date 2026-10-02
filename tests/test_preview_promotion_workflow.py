from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PreviewPromotionWorkflowTests(unittest.TestCase):
    def test_budget_guard_is_invoked_as_module(self):
        workflow = (ROOT / ".github/workflows/promote-preview-candidate.yml").read_text()
        self.assertIn("python -m scripts.preview_budget_guard", workflow)

    def test_summary_does_not_use_shell_command_substitution(self):
        workflow = (ROOT / ".github/workflows/promote-preview-candidate.yml").read_text()
        self.assertIn("printf '%s\\n' \"- candidate: $CANDIDATE_SHA\"", workflow)
        self.assertIn("printf '%s\\n' \"- action: $action\"", workflow)
        self.assertNotIn('echo "- candidate: `$CANDIDATE_SHA`"', workflow)
        self.assertNotIn('echo "- action: `$action`"', workflow)

    def test_budget_guard_supports_direct_execution_imports(self):
        guard = (ROOT / "scripts/preview_budget_guard.py").read_text()
        self.assertIn("if __package__:", guard)
        self.assertIn("from collect_vercel_usage import list_team_deployments", guard)
        self.assertIn("from vercel_preview_guard import evaluate_quota", guard)


if __name__ == "__main__":
    unittest.main()
