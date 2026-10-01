import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/"apps"/"console"/"lib"/"release-operator.ts"
PAGE=ROOT/"apps"/"console"/"app"/"gates"/"page.tsx"
POLICY=ROOT/"config"/"factory.release-policy.v1.json"
PREVIEW_WORKFLOW=ROOT/".github"/"workflows"/"exact-preview-browser-evidence.yml"


class ConsoleReleaseMergeTests(unittest.TestCase):
    def test_merge_path_is_console_admin_only_and_production_only(self):
        text=MODULE.read_text()
        self.assertIn("requireConsoleAdmin()",text)
        self.assertIn('process.env.VERCEL_ENV!=="production"',text)
        self.assertIn("FACTORY_RELEASE_GITHUB_TOKEN",text)
        self.assertIn("operator_allowed_repositories",POLICY.read_text())
        self.assertNotIn("GITHUB_TOKEN",text.replace("FACTORY_RELEASE_GITHUB_TOKEN",""))

    def test_merge_revalidates_durable_release_and_exact_pr_sha(self):
        text=MODULE.read_text()
        for marker in (
            "ready_for_human_release",
            "awaiting_release",
            "candidate!==expectedCandidate",
            'String(pr.state)!=="open"',
            "Boolean(pr.draft)",
            'String(pr.base?.ref)!=="main"',
            "String(pr.base?.repo?.full_name)!==repository",
            "String(pr.head?.repo?.full_name)!==repository",
            "String(pr.head?.sha)!==candidate",
            "pr.mergeable!==true",
            "sha:candidate",
        ):
            self.assertIn(marker,text)

    def test_merge_is_irreversible_only_after_pre_audit(self):
        text=MODULE.read_text()
        requested=text.index("human_release.console_merge_requested")
        merge_call=text.index("/merge")
        self.assertLess(requested,merge_call)
        self.assertIn("human_release.console_merge_succeeded",text)
        self.assertIn("human_release.console_merge_failed",text)

    def test_console_button_requires_explicit_confirmation(self):
        text=PAGE.read_text()
        self.assertIn("<form action={mergeRelease}",text)
        self.assertIn("Fazer merge em produção",text)
        self.assertIn("Esta ação altera main",text)
        self.assertIn("candidate_commit",text)
        self.assertNotIn('"use client"',text)

    def test_policy_keeps_auto_merge_disabled(self):
        text=POLICY.read_text()
        self.assertIn('"auto_merge_allowed": false',text)
        self.assertIn('"human_console_merge_allowed": true',text)
        self.assertIn('"operator_merge_method": "squash"',text)
        self.assertIn('"operator_allowed_repositories"',text)
        self.assertIn('"leandrosilveiradepaula/ai-product-factory"',text)

    def test_exact_preview_branch_runs_browser_evidence(self):
        text=PREVIEW_WORKFLOW.read_text()
        self.assertIn('"preview/**"',text)
        self.assertIn("checks.listForRef",text)
        self.assertIn("context.sha",text)
        self.assertIn("createWorkflowDispatch",text)
        self.assertIn("console-browser-evidence.yml",text)
        self.assertIn('ref: "main"',text)
        self.assertIn("CANDIDATE_SHA",text)
        self.assertNotIn("VERCEL_TOKEN",text)


if __name__=="__main__":
    unittest.main()
