from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CiConcurrencyTests(unittest.TestCase):
    def test_validate_and_console_cancel_obsolete_runs_per_pr_or_ref(self):
        for path in (
            ".github/workflows/validate.yml",
            ".github/workflows/console.yml",
        ):
            workflow = (ROOT / path).read_text()
            self.assertIn("concurrency:", workflow)
            self.assertIn("github.event.pull_request.number || github.ref", workflow)
            self.assertIn("cancel-in-progress: true", workflow)

    def test_preview_promoter_cancels_stale_source_branch_runs(self):
        workflow = (ROOT / ".github/workflows/promote-preview-candidate.yml").read_text()
        self.assertIn("github.event.workflow_run.head_branch", workflow)
        self.assertIn("cancel-in-progress: true", workflow)

    def test_console_validation_uses_dependency_cache(self):
        workflow = (ROOT / ".github/workflows/console.yml").read_text()
        self.assertIn('cache: "npm"', workflow)
        self.assertIn('cache-dependency-path: "apps/console/package-lock.json"', workflow)

    def test_preview_promoter_skips_superseded_candidates_without_failure(self):
        workflow = (ROOT / ".github/workflows/promote-preview-candidate.yml").read_text()
        self.assertIn('promotion_action", "stale"', workflow)
        self.assertIn("skipping obsolete Preview work", workflow)
        self.assertIn("steps.verify.outputs.promotion_action != 'stale'", workflow)

    def test_validate_does_not_double_run_on_ci_branch_pushes(self):
        workflow = (ROOT / ".github/workflows/validate.yml").read_text()
        self.assertIn("branches: [main, 'release/**']", workflow)
        self.assertNotIn("'ci/**'", workflow)


if __name__ == "__main__":
    unittest.main()
