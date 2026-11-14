"""Fail-closed wave-seven greenfield UI recovery contract."""
from pathlib import Path
import unittest
SQL=(Path(__file__).resolve().parents[1]/"supabase/migrations/20261114110000_greenfield_ui_scope_recovery.sql").read_text()
class GreenfieldUIRecoveryContract(unittest.TestCase):
    def test_inert_and_privileged(self):
        self.assertIn("create or replace function public.factory_resume_greenfield_ui_scope_once(",SQL.lower())
        self.assertNotIn("select public.factory_resume_greenfield_ui_scope_once(",SQL.lower())
        for value in ("security invoker","set search_path=''","from public,anon,authenticated","to service_role","'release_authorized',false"):
            self.assertIn(value,SQL.lower())
    def test_exact_scope_and_lineage(self):
        for value in ("v_set.current_wave is distinct from 7","v_unit.wave is distinct from 7",
          "v_unit.plan_task_key is distinct from 'workspace-authoring-ui'",
          "src/components/ProjectWorkspace.test.tsx","prior.wave=6",
          "later.wave>7","v_run.attempt_count is distinct from 1",
          "v_run.last_error is distinct from v_error",
          "v_unit.base_commit is distinct from p_expected_candidate_sha",
          "v_control.generation is distinct from p_expected_generation",
          "v_run.metadata->>'greenfield_ui_scope_recovery'=v_key"):
            with self.subTest(value=value):self.assertIn(value,SQL)
if __name__=="__main__":unittest.main()
