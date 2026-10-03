from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GitHubAppBrokerBindingTests(unittest.TestCase):
    def test_edge_broker_revalidates_exact_repository_before_returning_token(self):
        edge = (ROOT / "supabase/functions/factory-runtime-control-plane/index.ts").read_text()
        self.assertIn('"https://api.github.com/repositories/"+repositoryId', edge)
        self.assertIn("github_app_repository_binding_mismatch", edge)
        self.assertIn("repositoryBody?.full_name", edge)
        self.assertIn("repository_ids:[repositoryId]", edge)
        self.assertIn("token_persisted:false", edge)

    def test_python_runtime_rejects_broker_binding_or_persistence_drift(self):
        runtime = (ROOT / "src/ai_product_factory/github_app_runtime.py").read_text()
        self.assertIn("broker returned a different installation", runtime)
        self.assertIn("broker returned a different repository", runtime)
        self.assertIn("token persistence contract was not proven", runtime)

    def test_token_mint_is_restricted_to_autonomous_runner_identity(self):
        edge = (ROOT / "supabase/functions/factory-runtime-control-plane/index.ts").read_text()
        self.assertIn("github_app_token_workflow_not_allowed", edge)
        self.assertIn("github_app_token_event_not_allowed", edge)
        self.assertIn(".github/workflows/autonomous-runner.yml@refs/heads/main", edge)
        self.assertIn('["schedule","workflow_dispatch","issue_comment","push"]', edge)
        self.assertIn(".github/workflows/crm-cross-repo-preflight.yml@refs/heads/main", edge)

    def test_crm_preflight_uses_oidc_and_ephemeral_app_token_not_pat(self):
        workflow = (ROOT / ".github/workflows/crm-cross-repo-preflight.yml").read_text()
        self.assertIn("id-token: write", workflow)
        self.assertIn("./.github/actions/control-plane-oidc", workflow)
        self.assertIn("resolve_github_token(repository)", workflow)
        self.assertIn('"auth":"github_app_ephemeral"', workflow)
        self.assertNotIn("FACTORY_GITHUB_TOKEN", workflow)


if __name__ == "__main__":
    unittest.main()
