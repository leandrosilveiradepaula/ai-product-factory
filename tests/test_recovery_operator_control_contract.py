"""Recovery must never materialize new work on operator-paused projects."""
import re
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261020194500_fence_recovery_manual_project_control.sql").read_text()
SCENARIO=(ROOT/"scripts/verify_recovery_manual_project_control_postgres.py").read_text()
FUNCTIONS=(
    "factory_assert_project_running",
    "factory_recover_expired_runs",
    "factory_recover_change_sets",
    "factory_recover_specialist_lanes",
    "factory_resume_resolved_decisions",
    "factory_retry_failed_run",
)

def body(fn):
    fragment=SQL.split("CREATE OR REPLACE FUNCTION public."+fn+"(",1)[1]
    return fragment.split("CREATE OR REPLACE FUNCTION",1)[0]

class RecoveryHumanControlTests(unittest.TestCase):
    def test_only_existing_security_invoker_rpcs_are_replaced(self):
        self.assertEqual(tuple(re.findall(r"CREATE OR REPLACE FUNCTION public\.(factory_\w+)\(",SQL)),FUNCTIONS)
        self.assertEqual(SQL.count("$function$;"),6)
        self.assertIn("BEGIN;",SQL)
        self.assertTrue(SQL.strip().endswith("COMMIT;"))
        for token in ("SECURITY DEFINER","GRANT EXECUTE","DROP FUNCTION","CREATE POLICY",
                      "OPENAI_API_KEY","merge_pull_request","factory_primary_model"):
            self.assertNotIn(token,SQL)
    def test_operator_guard_also_requires_positive_generation_and_active_project(self):
        assertbody=body("factory_assert_project_running")
        self.assertIn("c.generation>0 and p.is_active=true",assertbody)
        self.assertIn("for share of c,p",assertbody)
        self.assertIn("errcode='PT409'",assertbody)
    def test_expired_run_recovery_is_fenced_before_requeue_or_failure(self):
        script=body("factory_recover_expired_runs")
        self.assertIn("c.state='running' and c.generation>0",script)
        self.assertIn("c.project_id=rec.project_id",script)
        self.assertIn("for share of c,p",script)
        self.assertLess(script.index("if not found then continue; end if;"),script.index("set status='queued'"))
    def test_every_change_set_mutation_requires_running_project(self):
        script=body("factory_recover_change_sets")
        self.assertIn("for share of c,p",script)
        self.assertGreaterEqual(script.count("c.state='running' and c.generation>0"),7)
        self.assertIn("join public.factory_project_execution_controls c on c.project_id=p.id",script)
        self.assertIn("where u.run_id=r.id",script)
        self.assertIn("where s.status='integrating'",script)
    def test_specialist_recovery_never_resumes_paused_lanes(self):
        script=body("factory_recover_specialist_lanes")
        self.assertIn("for share of c,p",script)
        self.assertGreaterEqual(script.count("c.state='running' and c.generation>0"),4)
        self.assertIn("where p.id=public.factory_specialist_lane_jobs.project_id",script)
    def test_approved_decisions_are_materialized_only_while_running(self):
        script=body("factory_resume_resolved_decisions")
        self.assertIn("c.state='running' and c.generation>0",script)
        self.assertIn("c.project_id=v_run.project_id",script)
        self.assertIn("for share of c,p",script)
        self.assertLess(script.index("if not found then continue; end if;"),script.index("insert into public.factory_tasks"))
    def test_explicit_retry_must_check_operator_authorization(self):
        script=body("factory_retry_failed_run")
        self.assertIn("perform public.factory_assert_project_running(v_project_id);",script)
        self.assertLess(script.index("perform public.factory_assert_project_running(v_project_id);"),script.index("insert into public.factory_runs"))
    def test_isolated_postgres_uses_real_recovery_contracts_and_no_production(self):
        self.assertIn("REFUSING_NON_ISOLATED_RECOVERY_TEST_DATABASE",SCENARIO)
        self.assertIn('factory_recovery_control_test',SCENARIO)
        self.assertIn('127.0.0.1',SCENARIO)
        for fn in FUNCTIONS:
            self.assertIn("factory_"+fn.split("factory_",1)[1],SQL)
        for fragment in ("public.factory_recover_expired_runs","public.factory_recover_change_sets",
                         "public.factory_recover_specialist_lanes","public.factory_resume_resolved_decisions",
                         "public.factory_retry_failed_run"):
            self.assertIn(fragment,SCENARIO)
if __name__=="__main__":
    unittest.main()
