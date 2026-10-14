"""Ensure merged SQL includes function statement terminators before apply."""
from pathlib import Path
import re
import unittest
SQL=(Path(__file__).resolve().parents[1]/"supabase/migrations/20261014015500_codex_atomic_mode_isolation.sql").read_text()
class MigrationSyntaxContract(unittest.TestCase):
 def test_all_sql_function_statements_are_terminated(self):
  self.assertEqual(SQL.count("CREATE OR REPLACE FUNCTION"),6)
  self.assertEqual(SQL.count("$function$;"),6)
  self.assertEqual(SQL.count("$function$"),12)
  self.assertNotRegex(SQL,r"\$function\$\s*CREATE OR REPLACE FUNCTION")
 def test_mode_guards_and_grants_remain(self):
  self.assertIn("jsonb_build_object('codex_execution_mode',p_codex_mode)",SQL)
  self.assertIn("revoke execute on function public.factory_dispatch_preapproved_planned_task(",SQL)
  self.assertIn("a.allowed_tools ? 'codex'",SQL)
if __name__=="__main__":unittest.main()
