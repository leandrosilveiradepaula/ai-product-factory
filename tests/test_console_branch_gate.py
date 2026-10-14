"""Exercise the actual read-only Console validation branch gate shell."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest

WORKFLOW = (Path(__file__).resolve().parents[1] / ".github/workflows/console.yml").read_text()


def gate_script() -> str:
    gate = WORKFLOW.split("      - name: Enforce Console branch convention\n", 1)[1]
    gate = gate.split("\n      - uses:", 1)[0]
    body = gate.split("        run: |\n", 1)[1]
    lines = body.splitlines()
    if not lines or any(line and not line.startswith("          ") for line in lines):
        raise AssertionError("malformed Console branch gate script")
    return "\n".join(line[10:] for line in lines)


class ConsoleBranchGateTests(unittest.TestCase):
    def run_gate(self, branch, *, author="human", repository="leandrosilveiradepaula/ai-product-factory"):
        env = dict(os.environ)
        env.update(GITHUB_HEAD_REF=branch, PR_AUTHOR_LOGIN=author, PR_HEAD_REPO=repository,
                   GITHUB_REPOSITORY="leandrosilveiradepaula/ai-product-factory")
        return subprocess.run(["bash", "-e", "-c", gate_script()], env=env,
                              capture_output=True, text=True)

    def test_real_same_repo_dependabot_allowed(self):
        result = self.run_gate("dependabot/github_actions/github-actions-2f4c4b3894",
                               author="dependabot[bot]")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fake_dependabot_branch_not_allowed(self):
        out = self.run_gate("dependabot/github_actions/fake", author="some-human")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("real Dependabot author", out.stdout)

    def test_dependabot_fork_not_allowed(self):
        out = self.run_gate("dependabot/github_actions/update",
                            author="dependabot[bot]", repository="other/fork")
        self.assertNotEqual(out.returncode, 0)

    def test_technical_branches_still_allowed(self):
        for branch in ("console/feature", "ci/feature", "security/fix", "release/update"):
            with self.subTest(branch=branch):
                self.assertEqual(self.run_gate(branch).returncode, 0)

    def test_preview_branch_reserved(self):
        for author in ("dependabot[bot]", "human"):
            with self.subTest(author=author):
                self.assertNotEqual(self.run_gate("preview/pr-811", author=author).returncode, 0)

    def test_unknown_branches_rejected(self):
        for branch in ("feature/test", "dependabot", "main"):
            with self.subTest(branch=branch):
                self.assertNotEqual(self.run_gate(branch).returncode, 0)

    def test_workflow_permissions_unchanged(self):
        self.assertIn("  contents: read", WORKFLOW)
        self.assertNotIn("  contents: write", WORKFLOW)
        self.assertNotIn("pull_request_target:", WORKFLOW)
        self.assertNotIn("workflow_dispatch:", WORKFLOW)
        self.assertIn("github.event.pull_request.user.login", WORKFLOW)
        self.assertIn("github.event.pull_request.head.repo.full_name", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
