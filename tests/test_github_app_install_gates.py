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

    def test_install_flow_requires_explicit_same_origin_post_after_setup_redirect(self):
        gates = (ROOT / "apps/console/app/gates/page.tsx").read_text()
        install = (ROOT / "apps/console/app/api/integrations/github-app/install/route.ts").read_text()
        projects = (ROOT / "apps/console/app/projects/page.tsx").read_text()
        verify = (ROOT / "apps/console/app/api/integrations/github-app/verify/route.ts").read_text()
        self.assertIn("/api/integrations/github-app/install?project=", gates)
        self.assertIn("factory_github_app_install_project", install)
        self.assertIn("getProjectDetail(projectKey)", install)
        self.assertIn('project.key==="ai-product-factory"', install)
        self.assertIn('query.github_app==="installed"', projects)
        self.assertIn('query.setup_action==="install"', projects)
        self.assertIn('query.setup_action==="update"', projects)
        self.assertIn("factory_github_app_install_project", projects)
        self.assertIn('name="return_to" value="gates"', projects)
        self.assertIn('method="POST" action="/api/integrations/github-app/verify"', projects)
        self.assertNotIn('redirect("/api/integrations/github-app/verify', projects)
        self.assertNotIn("installation_id", projects)
        detail = (ROOT / "apps/console/app/projects/[key]/page.tsx").read_text()
        self.assertIn('query.setup_action==="install"', detail)
        self.assertIn('installProject===key', detail)
        self.assertIn('factory_github_app_install_project', detail)
        self.assertIn('method="POST" action="/api/integrations/github-app/verify"', detail)
        self.assertNotIn('redirect("/api/integrations/github-app/verify', detail)
        self.assertIn('method="POST" action="/api/integrations/github-app/verify"', gates)
        self.assertIn("export function GET()", verify)
        self.assertIn('status:405', verify)
        self.assertIn("export async function POST(request:Request)", verify)
        self.assertIn('origin!==url.origin', verify)
        self.assertIn('startsWith("application/x-www-form-urlencoded")', verify)
        self.assertIn("verifyProjectGitHubApp(project)", verify)
        self.assertIn('returnTo==="gates"', verify)
        self.assertIn('jar.delete("factory_github_app_install_project")', verify)

    def test_gates_confirm_installation_verification_outcome(self):
        gates = (ROOT / "apps/console/app/gates/page.tsx").read_text()
        self.assertIn("githubAppNotices", gates)
        self.assertIn("GitHub App verificada para o projeto", gates)
        self.assertIn("verification_failed", gates)
        self.assertIn("!githubAppActionPending&&installActions.length===0", gates)


if __name__ == "__main__":
    unittest.main()
