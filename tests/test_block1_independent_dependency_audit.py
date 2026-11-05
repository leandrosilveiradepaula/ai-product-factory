"""Fail-closed contracts for independent dependency advisory evidence."""
from pathlib import Path
import re
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/block1-independent-dependency-audit.yml"

class IndependentDependencyAuditContracts(unittest.TestCase):
    def setUp(self):
        self.source = WORKFLOW.read_text(encoding="utf-8")

    def test_no_privileged_token_or_provider_side_effects(self):
        for forbidden in ("secrets.", "pull_request_target:", "contents: write",
                          "npm install", "npm ci", "pip install", "workflow_run:",
                          "deploy", "merge --", "FACTORY_PRIMARY_MODEL_ENABLED"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source)

    def test_candidate_sha_matches_checkout_and_report(self):
        self.assertIn("ref: ${{ github.event.pull_request.head.sha || github.sha }}", self.source)
        self.assertIn("CANDIDATE_SHA: ${{ github.event.pull_request.head.sha || github.sha }}", self.source)
        self.assertIn('"sha": os.environ["CANDIDATE_SHA"]', self.source)
        self.assertNotIn('"sha": os.environ["GITHUB_SHA"]', self.source)

    def test_fails_closed_and_keeps_raw_evidence(self):
        for marker in ("--package-lock-only --omit=dev --audit-level=high --json",
                       '"valid_report": valid', '"scanner_exit_code": code',
                       'code == 0', 'counts["high"] == 0',
                       'counts["critical"] == 0', 'sys.exit(1)',
                       "if: always()", "block1-npm-audit.json",
                       "block1-npm-audit-summary.json",
                       '"block1_certified": False'):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.source)

    def test_all_actions_are_pinned(self):
        actions = re.findall(r"uses:\s*([^\s#]+)", self.source)
        self.assertGreaterEqual(len(actions), 3)
        for action in actions:
            self.assertRegex(action, r"^[\w-]+/[\w-]+@[0-9a-f]{40}$")

if __name__ == "__main__":
    unittest.main()
