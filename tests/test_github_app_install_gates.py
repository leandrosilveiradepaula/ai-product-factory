from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GitHubAppInstallGateTests(unittest.TestCase):
    def test_gates_surface_cross_repo_installation_actions(self):
        gates = (ROOT / "apps/console/app/gates/page.tsx").read_text()
        control = (ROOT / "apps/console/lib/control-plane.ts").read_text()
        self.assertIn("getGitHubAppInstallActions", gates)
        self.assertIn("Instalar GitHub App em", gates)
        self.assertIn("Instalar no GitHub", gates)
        self.assertIn("Verificar instalação", gates)
        self.assertIn('project.project_key==="ai-product-factory"', control)
        self.assertIn("status=neq.ready", control)
        self.assertIn("github_app/ready", (ROOT / "docs/OPERATIONS.md").read_text() if (ROOT / "docs/OPERATIONS.md").exists() else "")


if __name__ == "__main__":
    unittest.main()
