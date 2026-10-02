from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GitHubAppGateVisibilityTests(unittest.TestCase):
    def test_registration_action_is_visible_without_persisted_gate(self):
        gates = (ROOT / "apps/console/app/gates/page.tsx").read_text()
        register = (ROOT / "apps/console/app/api/integrations/github-app/register/route.ts").read_text()
        callback = (ROOT / "apps/console/app/api/integrations/github-app/callback/route.ts").read_text()
        self.assertIn("getGitHubAppStatus", gates)
        self.assertIn("githubAppActionPending=!githubApp.configured", gates)
        self.assertIn("Registrar GitHub App da Factory", gates)
        self.assertIn("/api/integrations/github-app/register?return_to=gates", gates)
        self.assertIn("factory_github_app_return_to", register)
        self.assertIn('returnTo==="gates"', callback)


if __name__ == "__main__":
    unittest.main()
