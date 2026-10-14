"""Draft -> Ready must use unprivileged CI, never a new trusted token trigger."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = (ROOT / ".github/workflows/console.yml").read_text()
PROMOTER = (ROOT / ".github/workflows/promote-preview-candidate.yml").read_text()
VALIDATE = (ROOT / ".github/workflows/validate.yml").read_text()

class ReadyForReviewBridgeTests(unittest.TestCase):
    def test_existing_pr_activity_is_preserved_with_ready_transition(self):
        event = CONSOLE.split("\non:\n", 1)[1].split("\npermissions:\n", 1)[0]
        self.assertIn("types: [opened, synchronize, reopened, ready_for_review]", event)
        self.assertIn("branches: [main]", event)
        self.assertIn('"apps/console/**"', event)
        self.assertIn('".github/workflows/console.yml"', event)

    def test_no_expansion_of_console_ci_permissions(self):
        self.assertIn("  contents: read", CONSOLE)
        for forbidden in ("contents: write", "actions: write", "id-token: write",
                          "pull-requests: write", "pull_request_target:",
                          "workflow_dispatch:", "issue_comment:", "secrets.",
                          "gh pr merge", "git push"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, CONSOLE)
        self.assertIn("Enforce Console branch convention", CONSOLE)

    def test_privileged_promoter_still_runs_only_from_trusted_event(self):
        event = PROMOTER.split("\non:\n", 1)[1].split("\npermissions:\n", 1)[0]
        self.assertIn("workflow_run:", event)
        self.assertIn('workflows: ["Console validation"]', event)
        self.assertIn("workflow_dispatch:", event)
        self.assertNotIn("pull_request_target:", event)
        self.assertNotIn("pull_request:", event)
        self.assertNotIn("ready_for_review", event)
        self.assertIn("github.event.workflow_run.event == 'pull_request'", PROMOTER)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", PROMOTER)

    def test_pr_sha_and_quota_are_still_revalidated_before_preview(self):
        for guard in ("fresh.draft !== false", "fresh.head?.sha !== sha",
                      "pr.draft !== false", "pr.head?.sha !== sha",
                      'pr.base?.ref !== "main"',
                      'pr.head?.repo?.full_name !== fullRepo',
                      "github.rest.pulls.listFiles", 'startsWith("apps/console/")',
                      "c.head_sha === sha", "previewRef.object.sha !== sha",
                      "python -m scripts.preview_provider_cooldown",
                      "python -m scripts.preview_budget_guard"):
            with self.subTest(guard=guard):
                self.assertIn(guard, PROMOTER)

    def test_no_ci_bypass_or_second_branch_push_workflow(self):
        self.assertIn("cancel-in-progress: true", CONSOLE)
        self.assertIn("github.event.pull_request.number || github.ref", CONSOLE)
        self.assertIn("npm ci", CONSOLE)
        self.assertIn("npm run typecheck", CONSOLE)
        self.assertIn("npm run build", CONSOLE)
        self.assertIn("branches: [main, 'release/**']", VALIDATE)
        self.assertNotIn("'ci/**'", VALIDATE)

if __name__ == "__main__":
    unittest.main()
