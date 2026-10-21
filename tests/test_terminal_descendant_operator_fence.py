"""Terminal descendant recovery must respect operator control and project identity."""
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase/migrations/20261021014000_fence_terminal_descendant_recovery_manual_control.sql"
SCRIPT=ROOT/"scripts/verify_recovery_manual_project_control_postgres.py"
WORKFLOW=ROOT/".github/workflows/manual-project-control-postgres.yml"


class TerminalRecoveryFenceContract(unittest.TestCase):
    def test_one_existing_security_invoker_function_without_permissions_growth(self):
        sql=MIGRATION.read_text()
        self.assertEqual(re.findall(r"CREATE OR REPLACE FUNCTION public\.([a-z_]+)\(",sql),[
            "factory_reconcile_terminal_task_descendants"])
        self.assertEqual(sql.count("$function$"),2)
        self.assertEqual(sql.count("for share of c,p skip locked"),2)
        self.assertTrue(sql.strip().endswith("COMMIT;"))
        self.assertIn("SET search_path TO ''",sql)
        for forbidden in ("SECURITY DEFINER","GRANT EXECUTE","CREATE POLICY",
                          "ALTER TABLE","DROP TABLE","DELETE FROM","merge_pull_request"):
            self.assertNotIn(forbidden,sql)

    def test_running_active_generation_and_lock_before_each_mutation(self):
        sql=MIGRATION.read_text().lower()
        self.assertEqual(sql.count("c.state='running' and c.generation>0"),2)
        self.assertEqual(sql.count("p.is_active=true"),2)
        self.assertEqual(sql.count("for share of c,p skip locked"),2)
        self.assertIn("parent.project_id=child.project_id",sql)
        self.assertIn("root.project_id=s.project_id",sql)
        first=sql.index("for update of child skip locked")
        second=sql.index("for update of s skip locked")
        self.assertLess(first,sql.index("update public.factory_tasks",first))
        self.assertLess(second,sql.index("update public.factory_change_sets",second))
        self.assertIn("child.status not in ('completed','cancelled')",sql)
        self.assertIn("s.status not in ('completed','superseded')",sql)

    def test_isolated_postgres_repro_covers_pause_stop_resume_identity_races(self):
        scenario=SCRIPT.read_text()
        for marker in ("REFUSING_NON_ISOLATED_RECOVERY_TEST_DATABASE",
                       "factory_recovery_control_test","127.0.0.1",
                       "terminal_migration","terminal-pausing","terminal-independent",
                       "terminal-share-lock","cross_project_child","before_runs",
                       "lock_timeout='200ms'","RECOVERY_MANUAL_CONTROL_POSTGRES_PASS=1"):
            self.assertIn(marker,scenario)
        workflow=WORKFLOW.read_text()
        self.assertIn("supabase/migrations/*fence_terminal_descendant_recovery_manual_control.sql",workflow)
        self.assertIn("python scripts/verify_recovery_manual_project_control_postgres.py",workflow)


if __name__=="__main__":
    unittest.main()
