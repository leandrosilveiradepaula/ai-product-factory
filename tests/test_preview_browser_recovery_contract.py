import pathlib
import unittest


ROOT=pathlib.Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase/migrations/20261018211000_resume_preview_browser_infrastructure_failure.sql"


class PreviewBrowserInfrastructureRecoveryContract(unittest.TestCase):
    def test_recovery_requires_original_failure_and_all_exact_evidence(self):
        sql=MIGRATION.read_text()
        for marker in (
            "v_run.status<>'failed'",
            "v_task.status<>'failed'",
            "v_set.status<>'ci_pending'",
            "v_set.candidate_commit is distinct from p_candidate_commit",
            "v_control.state is distinct from 'running'",
            "and (j.status<>'passed'",
            "e.eval_type='quality_gate'",
            "e.baseline_ref=p_candidate_commit",
            "e.eval_type='browser_e2e'",
            "e.status='success'",
            "chromium_headless_shell",
            "d.environment='preview'",
            "d.metadata->>'candidate_commit'=p_candidate_commit",
            "p_verified_github->>'vercel_state' is distinct from 'success'",
            "p_verified_github->>'pr_state' is distinct from 'open'",
            "status='preview_ready'",
            "original_browser_failure_preserved",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker,sql)

    def test_rpc_remains_privileged_and_never_erases_historical_evidence(self):
        sql=MIGRATION.read_text()
        self.assertIn("security invoker",sql)
        self.assertIn("revoke all on function",sql)
        self.assertIn("from public,anon,authenticated",sql)
        self.assertIn("to service_role",sql)
        self.assertNotIn("delete from public.factory_evaluations",sql.lower())
        self.assertNotIn("delete from public.factory_deployments",sql.lower())
        self.assertNotIn("security definer",sql.lower())


if __name__=="__main__":
    unittest.main()
