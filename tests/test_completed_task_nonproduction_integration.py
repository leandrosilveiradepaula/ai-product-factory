import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20261019130000_accept_completed_nonproduction_integration_task.sql"


class CompletedTaskNonproductionIntegrationTests(unittest.TestCase):
    def test_completed_task_allowed_only_with_all_existing_guards(self):
        sql = MIGRATION.read_text()
        self.assertIn("v_task.status not in ('integrated','completed')", sql)
        self.assertNotIn("v_task.status<>'integrated'", sql)
        for guard in (
            "v_run.status<>'awaiting_release'",
            "v_change.status<>'ci_pending'",
            "v_control.state is distinct from 'running'",
            "v_task.project_id is distinct from v_change.project_id",
            "v_report.status<>'ready_for_human_release'",
            "e.eval_type='github_ci'",
            "e.eval_type='quality_gate'",
            "e.eval_type='browser_e2e'",
            "s.evidence->>'candidate_commit'=p_merge_sha",
            "s.source_status->>'browser_visual_validation'='success'",
            "coalesce(v_task.risk->>'destructive_data_change','false')='true'",
            "coalesce(v_task.risk->>'expands_sensitive_access','false')='true'",
            "coalesce(v_task.risk->>'material_requirement_change','false')='true'",
            "coalesce(v_task.risk->>'new_paid_service','false')='true'",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard, sql)

    def test_no_production_release_or_auto_merge(self):
        sql = MIGRATION.read_text().lower()
        self.assertIn("security invoker", sql)
        self.assertIn("'production_release_completed',false", sql)
        self.assertIn("'release_completed',false", sql)
        self.assertIn("revoke all on function", sql)
        for forbidden in ("security definer", "status='released'", "status='merged'", "factory_finalize_console_human_release"):
            self.assertNotIn(forbidden, sql)
        self.assertTrue(sql.strip().endswith("commit;"))


if __name__ == "__main__":
    unittest.main()
