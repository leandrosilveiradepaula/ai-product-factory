from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ConsoleSupabaseOAuthReadinessTests(unittest.TestCase):
    def test_oauth_readiness_is_explicit_and_fail_closed(self):
        oauth = (ROOT / "apps/console/lib/supabase-oauth.ts").read_text()
        connect = (ROOT / "apps/console/app/api/integrations/supabase/connect/route.ts").read_text()
        project = (ROOT / "apps/console/app/projects/[key]/page.tsx").read_text()

        self.assertIn("export function isSupabaseOAuthConfigured()", oauth)
        self.assertIn("SUPABASE_OAUTH_CLIENT_ID", oauth)
        self.assertIn("SUPABASE_OAUTH_CLIENT_SECRET", oauth)
        self.assertIn("isSupabaseOAuthConfigured", connect)
        self.assertIn('error:"supabase_oauth_not_configured"', connect)
        self.assertIn("status:503", connect)
        self.assertIn("const oauthReady=isSupabaseOAuthConfigured()", project)
        self.assertIn("OAuth do Supabase não configurado", project)
        self.assertIn("fail-closed", project)

    def test_oauth_readiness_never_exposes_secret_values(self):
        project = (ROOT / "apps/console/app/projects/[key]/page.tsx").read_text()
        self.assertNotIn("SUPABASE_OAUTH_CLIENT_SECRET", project)
        self.assertNotIn("process.env", project)

    def test_oauth_rpc_accepts_no_content_and_records_binding_mode(self):
        oauth = (ROOT / "apps/console/lib/supabase-oauth.ts").read_text()
        self.assertIn("if(r.status===204)return null;", oauth)
        self.assertIn("const text=await r.text();", oauth)
        self.assertIn('JSON.stringify({access_mode:"oauth",permission_mode:"read"})', oauth)
        self.assertIn('"Prefer":"return=minimal"', oauth)
        self.assertIn('factory_record_project_database_verification', oauth)


if __name__ == "__main__":
    unittest.main()
