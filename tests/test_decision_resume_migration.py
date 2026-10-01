import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase"/"migrations"/"20261001152200_factory_resume_after_human_decision.sql"


class DecisionResumeMigrationTests(unittest.TestCase):
    def test_resume_requires_explicit_approved_decision_plan(self):
        text=MIGRATION.read_text()
        self.assertIn("decision_only",text)
        self.assertIn("decision_outcome",text)
        self.assertIn("resume_plan",text)
        self.assertIn("= 'approved'",text)

    def test_invalid_plan_fails_closed_without_creating_task(self):
        text=MIGRATION.read_text()
        invalid=text.split("if v_external_key is null",1)[1].split("select id into v_task_id",1)[0]
        self.assertIn("blocked_invalid",invalid)
        self.assertIn("decision.resume.blocked",invalid)
        self.assertNotIn("insert into public.factory_tasks",invalid)

    def test_materialization_is_idempotent_and_serialized(self):
        text=MIGRATION.read_text()
        self.assertIn("pg_advisory_xact_lock",text)
        self.assertIn("where project_id = v_run.project_id",text)
        self.assertIn("and external_key = v_external_key",text)
        self.assertIn("resume_plan_status','materialized'",text)

    def test_created_task_uses_only_explicit_resume_plan(self):
        text=MIGRATION.read_text()
        self.assertIn("v_plan->>'external_key'",text)
        self.assertIn("v_plan->>'title'",text)
        self.assertIn("v_plan->'risk'",text)
        self.assertIn("v_plan->'acceptance_criteria'",text)
        self.assertIn("'queued'",text)


if __name__=="__main__":
    unittest.main()
