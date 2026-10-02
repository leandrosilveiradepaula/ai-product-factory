from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase/migrations/20261002014000_factory_project_preview_policy.sql"


class PreviewPolicyMigrationTests(unittest.TestCase):
    def test_auto_policy_is_positive_only_and_service_role_bounded(self):
        sql=MIGRATION.read_text()
        self.assertIn("factory_record_project_preview_policy",sql)
        self.assertIn("security invoker",sql)
        self.assertIn("automatic preview onboarding cannot disable preview",sql)
        self.assertIn("github_vercel_integration",sql)
        self.assertIn("existing_policy_preserved",sql)
        self.assertIn("project.preview_policy.verified",sql)
        self.assertIn("revoke all on function public.factory_record_project_preview_policy(uuid,jsonb,jsonb)",sql)
        self.assertIn("grant execute on function public.factory_record_project_preview_policy(uuid,jsonb,jsonb)",sql)
        self.assertNotIn("grant execute on function public.factory_record_project_preview_policy(uuid,jsonb,jsonb)\n  to anon",sql)
        self.assertNotIn("grant execute on function public.factory_record_project_preview_policy(uuid,jsonb,jsonb)\n  to authenticated",sql)


if __name__=="__main__":
    unittest.main()
