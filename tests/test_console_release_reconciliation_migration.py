from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase/migrations/20261001191500_factory_finalize_console_human_release.sql"
CI_PENDING_MIGRATION=ROOT/"supabase/migrations/20261002004600_factory_finalize_console_human_release_ci_pending.sql"


class Tests(unittest.TestCase):
    def test_console_release_finalization_is_bounded_and_service_role_only(self):
        sql=MIGRATION.read_text()
        self.assertIn("factory_finalize_console_human_release",sql)
        self.assertIn("security invoker",sql)
        self.assertIn("release report is not released",sql)
        self.assertIn("release report candidate mismatch",sql)
        self.assertIn("release report merge sha mismatch",sql)
        self.assertIn("run is not awaiting release",sql)
        self.assertIn("release task has incompatible status",sql)
        self.assertIn("set status='merged'",sql)
        self.assertIn("set status='completed'",sql)
        self.assertIn("'release.human_merge_observed'",sql)
        self.assertIn("revoke all on function public.factory_finalize_console_human_release(uuid,text,text) from public,anon,authenticated",sql)
        self.assertIn("grant execute on function public.factory_finalize_console_human_release(uuid,text,text) to service_role",sql)


    def test_console_release_finalization_accepts_reconciled_ci_pending_task(self):
        sql=CI_PENDING_MIGRATION.read_text()
        self.assertIn("('ci_pending','awaiting_human','awaiting_release')",sql)
        self.assertIn("if v_run.status<>'awaiting_release'",sql)
        self.assertIn("release report candidate mismatch",sql)
        self.assertIn("release report merge sha mismatch",sql)
        self.assertIn("set status='merged'",sql)
        self.assertIn("set status='completed'",sql)
        self.assertIn("security invoker",sql)
        self.assertIn("grant execute on function public.factory_finalize_console_human_release(uuid,text,text) to service_role",sql)

    def test_console_release_finalization_has_idempotent_terminal_path(self):
        sql=MIGRATION.read_text()
        self.assertIn("if v_run.status='merged' then",sql)
        self.assertIn("if v_task.status<>'completed'",sql)
        self.assertIn("v_idempotent:=true",sql)


if __name__=="__main__": unittest.main()
