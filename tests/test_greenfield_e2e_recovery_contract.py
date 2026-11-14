"""Wave-nine exact E2E recovery is inert, scoped and privileged."""
from pathlib import Path
import unittest
SQL=(Path(__file__).resolve().parents[1]/"supabase/migrations/20261114150000_greenfield_e2e_scope_recovery.sql").read_text()
class GreenfieldE2ERecoveryContract(unittest.TestCase):
    def test_fail_closed(self):
        for value in ("security invoker","set search_path=''","from public,anon,authenticated",
                      "to service_role","'release_authorized',false",
                      "v_set.current_wave is distinct from 9","v_unit.wave is distinct from 9",
                      "v_unit.plan_task_key is distinct from 'end-to-end-product-flow'",
                      "src/e2e/project-production-flow.test.ts","prior.wave=8",
                      "v_run.attempt_count is distinct from 1",
                      "v_run.last_error is distinct from v_error"):
            with self.subTest(value=value):self.assertIn(value,SQL)
        self.assertNotIn("select public.factory_resume_greenfield_e2e_scope_once(",SQL.lower())
if __name__=="__main__":unittest.main()
