import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class CrossRepoPreviewBrowserWorkflowTests(unittest.TestCase):
    def test_workflow_is_manual_exact_sha_and_uses_cross_repo_auth_boundary(self):
        text = (ROOT / ".github/workflows/cross-repo-preview-browser-evidence.yml").read_text()

        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("\n  push:", text)
        self.assertIn("candidate_sha:", text)
        self.assertIn("target_repository:", text)
        self.assertIn(r"[0-9a-f]{40}", text)
        self.assertIn("./.github/actions/control-plane-oidc", text)
        self.assertIn("resolve_github_token(repository)", text)
        self.assertIn("token_persisted", text)
        self.assertNotIn("pull-requests: write", text)
        self.assertNotIn("contents: write", text)

    def test_workflow_reuses_trusted_browser_and_records_target_status(self):
        text = (ROOT / ".github/workflows/cross-repo-preview-browser-evidence.yml").read_text()

        self.assertIn('workflowId = "console-browser-evidence.yml"', text)
        self.assertIn('ref: "main"', text)
        self.assertIn("expected_text: process.env.EXPECTED_TEXT", text)
        self.assertIn("factory_project_state_snapshots", text)
        self.assertIn("browser_visual_validation", text)
        self.assertIn("product_ready_inferred", text)
        self.assertNotIn("/statuses/{sha}", text)
        self.assertIn("Vercel Preview did not reach READY", text)

    def test_browser_never_receives_cross_repo_github_token(self):
        text = (ROOT / ".github/workflows/cross-repo-preview-browser-evidence.yml").read_text()
        verifier = text.split("- name: Dispatch trusted Factory browser verifier and wait", 1)[1].split(
            "- name: Record exact browser evidence on target candidate", 1
        )[0]

        self.assertNotIn("FACTORY_GITHUB_TOKEN", verifier)
        self.assertNotIn("resolve_github_token", verifier)
        self.assertIn("PREVIEW_URL", verifier)
        self.assertIn("EXPECTED_TEXT", verifier)

    def test_control_plane_broker_explicitly_allows_only_the_trusted_main_workflow(self):
        source = (ROOT / "supabase/functions/factory-runtime-control-plane/index.ts").read_text()
        workflow_ref = (
            "leandrosilveiradepaula/ai-product-factory/.github/workflows/"
            "cross-repo-preview-browser-evidence.yml@refs/heads/main"
        )
        self.assertGreaterEqual(source.count(workflow_ref), 2)
        self.assertIn('statuses: "read"', source)
        self.assertNotIn('statuses: "write"', source)


if __name__ == "__main__":
    unittest.main()
