import pathlib
import unittest


ROOT=pathlib.Path(__file__).resolve().parents[1]
PATH=ROOT/"supabase/migrations/20261018213500_observe_preview_branch_integration.sql"


class NonproductionMergeMigrationContract(unittest.TestCase):
    def test_fail_closed_gates_and_exact_candidate(self):
        sql=PATH.read_text()
        for term in (
            "security invoker", "v_run.status<>'awaiting_release'",
            "v_change.status<>'ci_pending'", "v_report.status<>'ready_for_human_release'",
            "e.eval_type='github_ci'", "e.eval_type='quality_gate'",
            "j.required", "j.status<>'passed'", "e.eval_type='browser_e2e'",
            "d.environment='preview'", "d.status='success'",
            "p_verified_github->>'vercel_state' is distinct from 'success'",
            "p_verified_github->>'merged' is distinct from 'true'",
            "p_base_ref !~ '^preview/",
            "v_control.state is distinct from 'running'",
            "'release_state','nonproduction_integrated'",
            "'release_completed',false", "'production_release_completed',false",
            "status='integrated'", "status='completed'",
            "s.evidence->>'candidate_commit'=p_merge_sha",
            "s.evidence->'preview'->>'status'='browser_verified'",
            "s.source_status->>'browser_visual_validation'='success'",
            "s.constraints->>'production_merge_authorized'='false'",
            "p_verified_github->>'postmerge_browser_snapshot_id'",
            "factory_release_agent_scope_locks",
            "change_set.nonproduction_merge.observed",
            "revoke all on function", "from public,anon,authenticated", "to service_role",
        ):
            with self.subTest(term=term):self.assertIn(term,sql)

    def test_never_stamps_release_or_automerge(self):
        sql=PATH.read_text().lower()
        for forbidden in ("security definer", "status='released'", "status='merged'",
            "human_release','passed", "delete from public.factory_evaluations",
            "factory_finalize_console_human_release", "factory_mark_release_report_released"):
            with self.subTest(forbidden=forbidden):self.assertNotIn(forbidden,sql)


if __name__=="__main__":unittest.main()
