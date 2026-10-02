from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PreviewPromotionWorkflowTests(unittest.TestCase):
    def test_budget_guard_is_invoked_as_module(self):
        workflow = (ROOT / ".github/workflows/promote-preview-candidate.yml").read_text()
        self.assertIn("python -m scripts.preview_budget_guard", workflow)

    def test_summary_does_not_use_shell_command_substitution(self):
        workflow = (ROOT / ".github/workflows/promote-preview-candidate.yml").read_text()
        self.assertIn("printf '%s\\n' \"- candidate: ${CANDIDATE_SHA:-n/a}\"", workflow)
        self.assertIn("printf '%s\\n' \"- action: $action\"", workflow)
        self.assertNotIn('echo "- candidate: `$CANDIDATE_SHA`"', workflow)
        self.assertNotIn('echo "- action: `$action`"', workflow)

    def test_budget_guard_supports_direct_execution_imports(self):
        guard = (ROOT / "scripts/preview_budget_guard.py").read_text()
        self.assertIn("if __package__:", guard)
        self.assertIn("from collect_vercel_usage import list_team_deployments", guard)
        self.assertIn("from vercel_preview_guard import evaluate_quota", guard)

    def test_console_validation_can_auto_promote_only_console_changes(self):
        workflow = (ROOT / ".github/workflows/promote-preview-candidate.yml").read_text()
        self.assertIn('workflow_run:', workflow)
        self.assertIn('workflows: ["Console validation"]', workflow)
        self.assertIn('github.event.workflow_run.event == \'pull_request\'', workflow)
        self.assertIn('startsWith("apps/console/")', workflow)
        self.assertIn('promotion_action", "not_applicable"', workflow)
        self.assertIn('github.event_name == \'workflow_dispatch\'', workflow)

    def test_token_driven_promotion_dispatches_exact_browser_evidence(self):
        promote = (ROOT / ".github/workflows/promote-preview-candidate.yml").read_text()
        exact = (ROOT / ".github/workflows/exact-preview-browser-evidence.yml").read_text()
        self.assertIn("actions: write", promote)
        self.assertIn('workflow_id: "exact-preview-browser-evidence.yml"', promote)
        self.assertIn("Factory Preview browser evidence", promote)
        self.assertIn("createWorkflowDispatch", promote)
        self.assertIn("workflow_dispatch:", exact)
        self.assertIn('"evidence/preview/**"', exact)
        self.assertIn("Factory Preview browser evidence", exact)
        self.assertIn("statuses: write", exact)


if __name__ == "__main__":
    unittest.main()
