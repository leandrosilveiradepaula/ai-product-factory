from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SQL=ROOT/"supabase/migrations/20261001231500_factory_project_github_access.sql"

class Tests(unittest.TestCase):
    def test_github_access_table_is_fail_closed_and_audited(self):
        sql=SQL.read_text()
        self.assertIn("create table if not exists public.factory_project_github_access",sql)
        self.assertIn("enable row level security",sql)
        self.assertIn("revoke all on table public.factory_project_github_access from anon, authenticated",sql)
        self.assertIn("factory_record_project_github_access",sql)
        self.assertIn("project.github_access.verified",sql)
        self.assertIn("trg_factory_seed_project_github_access",sql)

    def test_no_secret_columns_are_persisted(self):
        sql=SQL.read_text().lower()
        for forbidden in ("access_token text","private_key text","client_secret text","pat text","token text"):
            self.assertNotIn(forbidden,sql)

    def test_plpgsql_function_bodies_use_valid_dollar_quotes(self):
        lines=[line.strip() for line in SQL.read_text().splitlines()]
        self.assertNotIn("as $",lines)
        self.assertNotIn("$;",lines)
        self.assertEqual(lines.count("as $"),2)
        self.assertEqual(lines.count("$;"),2)

if __name__=="__main__":
    unittest.main()
