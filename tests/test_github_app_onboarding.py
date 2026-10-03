from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GitHubAppOnboardingTests(unittest.TestCase):
    def test_github_app_credentials_are_vaulted_and_service_role_only(self):
        migration = (ROOT / "supabase/migrations/20261002191500_factory_github_app_config.sql").read_text()
        self.assertIn("factory_github_app_config", migration)
        self.assertIn("vault.create_secret", migration)
        self.assertIn("vault.decrypted_secrets", migration)
        self.assertIn("enable row level security", migration)
        self.assertIn("revoke all on table public.factory_github_app_config from public,anon,authenticated", migration)
        self.assertIn("factory_store_github_app_config", migration)
        self.assertIn("factory_get_github_app_credentials", migration)
        self.assertIn("grant execute", migration)
        self.assertIn("to service_role", migration)
        self.assertNotIn("grant select on table public.factory_github_app_config to authenticated", migration)

    def test_manifest_flow_and_verification_are_admin_only(self):
        register = (ROOT / "apps/console/app/api/integrations/github-app/register/route.ts").read_text()
        callback = (ROOT / "apps/console/app/api/integrations/github-app/callback/route.ts").read_text()
        verify = (ROOT / "apps/console/app/api/integrations/github-app/verify/route.ts").read_text()
        lib = (ROOT / "apps/console/lib/github-app.ts").read_text()

        for route in (register, callback, verify):
            self.assertIn("requireConsoleAdmin()", route)
        self.assertIn("factory_github_app_manifest_state", register)
        self.assertIn("factory_github_app_manifest_state", callback)
        self.assertIn("app-manifests/", lib)
        self.assertIn("/conversions", lib)
        self.assertIn("createSign", lib)
        self.assertIn("/installation", lib)
        self.assertIn("/access_tokens", lib)
        self.assertIn("repositories:[name]", lib)
        self.assertIn("installation_token_persisted:false", lib)

    def test_browser_surface_never_receives_github_app_secrets(self):
        page = (ROOT / "apps/console/app/projects/[key]/page.tsx").read_text()
        lib = (ROOT / "apps/console/lib/github-app.ts").read_text()
        self.assertIn("Registrar GitHub App da Factory", page)
        self.assertIn("Verificar GitHub App neste projeto", page)
        self.assertIn("Instalar GitHub App neste projeto", page)
        self.assertNotIn("private_key", page)
        self.assertNotIn("client_secret", page)
        self.assertNotIn("webhook_secret", page)
        self.assertNotIn("installation token", page.lower())
        self.assertIn('/api/integrations/github-app/install?project=', page)
        self.assertIn('githubAccess.authMode!=="github_app"', page)
        self.assertIn('githubAccess.status!=="ready"', page)
        self.assertIn('Fallback: token fine-grained', page)
        self.assertIn("private_key", lib)

    def test_manifest_requests_only_delivery_permissions(self):
        lib = (ROOT / "apps/console/lib/github-app.ts").read_text()
        for marker in (
            'actions:"read"',
            'checks:"read"',
            'contents:"write"',
            'issues:"write"',
            'pull_requests:"write"',
            'statuses:"read"',
        ):
            self.assertIn(marker, lib)
        for forbidden in ('administration:"write"', 'members:"write"', 'secrets:"write"', 'workflows:"write"'):
            self.assertNotIn(forbidden, lib)


if __name__ == "__main__":
    unittest.main()
