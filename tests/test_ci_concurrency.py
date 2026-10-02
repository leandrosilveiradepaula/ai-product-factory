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


if __name__ == "__main__":
    unittest.main()
