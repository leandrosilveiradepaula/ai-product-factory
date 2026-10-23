import unittest
from pathlib import Path
SQL=(Path(__file__).resolve().parents[1]/"supabase/migrations/20261023151218_preserve_runtime_stage_evidence.sql").read_text()
class StageEvidenceSQLContractTests(unittest.TestCase):
    def test_parent_initialized_and_siblings_preserved(self):
        self.assertIn("coalesce(r.metadata->'stage_evidence','{}'::jsonb)",SQL)
        self.assertIn("v_parent || jsonb_build_object",SQL)
        self.assertIn("for update of r",SQL)
        self.assertNotIn("'{stage_evidence,planning}'",SQL)
    def test_function_stays_service_only(self):
        self.assertIn("security invoker",SQL)
        self.assertIn("set search_path=''",SQL)
        self.assertIn("from public,anon,authenticated",SQL)
        self.assertIn("to service_role",SQL)
        self.assertNotIn("security definer",SQL)
    def test_no_backfill_or_cross_project_mutation(self):
        self.assertNotIn("delete from",SQL.lower())
        self.assertNotIn("update public.factory_projects",SQL.lower())
        self.assertIn("runtime stage evidence parent malformed",SQL)
if __name__=="__main__":
    unittest.main()
