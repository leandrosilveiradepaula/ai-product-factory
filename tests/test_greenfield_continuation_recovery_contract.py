"""Fail-closed SQL contract for one-time greenfield continuation recovery."""
from pathlib import Path
import unittest

SQL=(Path(__file__).resolve().parents[1]/
     "supabase/migrations/20261113190000_greenfield_continuation_scope_recovery.sql").read_text()

class GreenfieldContinuationRecoveryContract(unittest.TestCase):
    def test_no_automatic_requeue_at_install(self):
        self.assertIn("create or replace function public.factory_resume_greenfield_continuation_scope_once(",SQL.lower())
        self.assertNotIn("select public.factory_resume_greenfield_continuation_scope_once(",SQL.lower())
        self.assertNotIn("perform public.factory_resume_greenfield_continuation_scope_once(",SQL.lower())

    def test_exact_identity_and_blocker_guards(self):
        for marker in (
            "p_run_id uuid","p_change_set_id uuid","p_work_unit_id uuid",
            "p_expected_candidate_sha text","p_expected_generation bigint",
            "v_set.current_wave is distinct from 2",
            "v_unit.plan_task_key is distinct from 'access-governance'",
            "v_unit.base_commit is distinct from p_expected_candidate_sha",
            "v_run.attempt_count is distinct from 1",
            "v_run.last_error is distinct from v_error",
            "v_set.metadata->'blocker'->>'run_id'",
            "v_set.metadata->'blocker'->>'work_unit_id'",
            "later.status is distinct from 'pending'",
            "v_control.state is distinct from 'running'",
            "v_run.metadata->>'greenfield_continuation_scope_recovery'=v_key",
            "change_set.greenfield_continuation_requeued",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker,SQL)

    def test_privileges_and_release_are_fail_closed(self):
        self.assertIn("security invoker",SQL.lower())
        self.assertIn("set search_path=''",SQL.lower())
        self.assertIn("from public,anon,authenticated",SQL.lower())
        self.assertIn("to service_role",SQL.lower())
        self.assertIn("'release_authorized',false",SQL.lower())
        self.assertNotIn("security definer",SQL.lower())
        self.assertNotIn("merge_pull_request",SQL.lower())

if __name__=="__main__":
    unittest.main()
