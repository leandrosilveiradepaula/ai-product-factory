"""Offline safety contract for owner-scoped private-pilot QA workflow.

This workflow is NOT a replacement for native product CI, PostgreSQL RLS,
Preview evidence, or a production release gate.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/service-desk-cross-repo-qa.yml").read_text(encoding="utf8")


class CrossRepoQAContractTests(unittest.TestCase):
    def test_owner_only_and_fixed_repository(self):
        for invariant in (
            "github.event.issue.number == 841",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.event.comment.author_association == 'OWNER'",
            "re.fullmatch(r\"/service-desk-qa",
            "repository = \"leandrosilveiradepaula/infodive-service-desk\"",
            "(head.get(\"repo\") or {}).get(\"full_name\") != repository",
            "head.get(\"sha\") != sha",
            "base.get(\"ref\") != \"main\"",
            "pr.get(\"state\") != \"open\"",
        ):
            with self.subTest(invariant=invariant):
                self.assertIn(invariant, WORKFLOW)

    def test_no_ambient_github_credential_or_automatic_release(self):
        for forbidden in (
            "id-token: write", "pull_request_target:", "secrets.SUPABASE_SECRET_KEY",
            "secrets.SUPABASE_SERVICE_ROLE_KEY", "merge_pull_request", "enable_auto_merge",
            "actions: write", "https://api.openai.com/v1/responses", "OPENAI_API_KEY", "workflow_dispatch:",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, WORKFLOW)
        self.assertIn("permissions:\n  contents: read", WORKFLOW)
        self.assertIn("token: ${{ secrets.FACTORY_GITHUB_TOKEN }}", WORKFLOW)
        self.assertIn("persist-credentials: false", WORKFLOW)
        self.assertIn("submodules: false", WORKFLOW)
        self.assertIn("Explicit cross-repo credential absent; no GITHUB_TOKEN fallback", WORKFLOW)
        self.assertEqual(WORKFLOW.count("secrets.FACTORY_GITHUB_TOKEN"), 2)

    def test_pinned_candidate_and_fail_closed_reproducible_dependencies(self):
        for invariant in (
            "test \"$(git rev-parse HEAD)\" = \"$EXPECTED_SHA\"",
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1",
            "actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f",
            "if [ ! -f package-lock.json ]; then",
            "npm install --package-lock-only --ignore-scripts --no-audit --no-fund",
            "cp package-lock.json .qa-evidence/package-lock.json",
            "exit 1",
            "npm ci --ignore-scripts --no-audit --no-fund",
            "npm run ci",
            '"npm_ci_tsx_tests_passed": os.environ["VERIFY_RESULT"] == "success"',
        ):
            with self.subTest(invariant=invariant):
                self.assertIn(invariant, WORKFLOW)
        # The privileged checkout is scoped to an immutable SHA, never a user-
        # supplied repository, branch name, or event payload.
        self.assertIn("ref: ${{ steps.candidate.outputs.sha }}", WORKFLOW)
        self.assertIn("repository: leandrosilveiradepaula/infodive-service-desk", WORKFLOW)
        self.assertNotRegex(WORKFLOW, r"repository:\s*\$\{\{\s*(?:inputs|github\.event)\.")

    def test_quality_signals_are_explicitly_non_authorizing(self):
        for invariant in (
            '"postgres_rls_isolation_passed": False',
            '"preview_verified": False',
            '"release_authorized": False',
            '"cross_repo_status_posted": False',
            '"paid_model_calls_performed": False',
        ):
            with self.subTest(invariant=invariant):
                self.assertIn(invariant, WORKFLOW)


if __name__ == "__main__":
    unittest.main()
