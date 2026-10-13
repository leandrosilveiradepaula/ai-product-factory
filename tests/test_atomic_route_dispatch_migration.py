import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"supabase/migrations/20261013220500_route_aware_atomic_dispatch.sql"
RUNTIME=ROOT/"src/ai_product_factory/runtime_cli.py"
WORKFLOW=ROOT/".github/workflows/autonomous-runner.yml"

class AtomicRouteDispatchMigrationTests(unittest.TestCase):
    def setUp(self):
        self.sql=MIGRATION.read_text()

    def test_plpgsql_bodies_are_well_bounded_with_no_orphan_sql(self):
        # #750 used substring presence checks that allowed an unterminated
        # regex string and a duplicated, orphaned SQL tail to pass CI.
        pieces=self.sql.split("as $$")
        self.assertEqual(len(pieces),3)
        self.assertEqual(self.sql.count("create or replace function"),2)
        self.assertEqual(self.sql.count("$$;"),2)
        for piece in pieces[1:]:
            body,delimiter,*tail=piece.partition("$$;")
            self.assertEqual(delimiter,"$$;")
            self.assertEqual(body.count("\\nbegin\\n"),1)
            self.assertEqual(body.count("\\nend;\\n"),1)
            self.assertEqual(body.count("'") % 2,0)
        # The last function terminator must be followed ONLY by its ACL.
        last_tail=self.sql.rsplit("$$;",1)[1]
        self.assertIn("revoke all on function public.factory_dispatch_preapproved_planned_task",last_tail)
        self.assertNotIn("select id into v_project_id",last_tail)
        self.assertNotIn("insert into public.factory_runs",last_tail)
        self.assertNotIn("raise exception",last_tail)

    def test_exact_fingerprint_regex_and_route_guard_precede_all_writes(self):
        claim=self.sql.split(
            "create or replace function public.factory_dispatch_preapproved_planned_task",1
        )[1].split("$$;",1)[0]
        self.assertIn("p_fingerprint !~ '^[0-9a-f]{32}$' then",claim)
        self.assertIn("p_route not in ('direct','codex')",claim)
        self.assertLess(claim.index("p_fingerprint !~"),claim.index("select id into v_project_id"))
        self.assertLess(claim.index("p_route not in"),claim.index("select id into v_project_id"))
        self.assertEqual(claim.count("insert into public.factory_runs"),1)
        self.assertEqual(claim.count("perform public.factory_record_dispatch_decision_v2"),1)

    def test_preflight_is_read_only(self):
        peek=self.sql.split("create or replace function public.factory_peek_planned_work",1)[1].split(
            "create or replace function public.factory_dispatch_preapproved_planned_task",1)[0]
        self.assertIn("status='pending'",peek)
        self.assertIn("cs.team_plan_id=v_team_id",peek)
        self.assertIn("p_limit<1 or p_limit>100",peek)
        for prohibited in ("insert into public.", "update public.", "delete from public."):
            self.assertNotIn(prohibited,peek.lower())

    def test_claim_uses_exact_unit_and_fingerprint_under_lock(self):
        claim=self.sql.split("create or replace function public.factory_dispatch_preapproved_planned_task",1)[1]
        for marker in (
            "u.id=p_work_unit_id",
            "for update of u skip locked limit 1",
            "select * into v_task from public.factory_tasks where id=v_unit.task_id for update",
            "v_actual_fingerprint is distinct from p_fingerprint",
            "candidate changed between route preflight and claim",
            "v_task.status<>'queued'",
            "cs.status in ('planned','building')",
        ):
            # The prior claim's status clause names alias s; do not weaken it.
            if marker=="cs.status in ('planned','building')":
                self.assertIn("s.status in ('planned','building')",claim)
            else:
                self.assertIn(marker,claim)

    def test_claim_and_routing_decision_are_in_one_pg_transaction(self):
        claim=self.sql.split("create or replace function public.factory_dispatch_preapproved_planned_task",1)[1]
        self.assertIn("insert into public.factory_runs",claim)
        self.assertIn("perform public.factory_record_dispatch_decision_v2",claim)
        self.assertLess(claim.index("insert into public.factory_runs"),claim.index("perform public.factory_record_dispatch_decision_v2"))
        self.assertNotIn("commit;",claim.lower())

    def test_old_blind_claim_is_inaccessible_from_runtime(self):
        self.assertIn("revoke execute on function public.factory_dispatch_next_planned_task(text) from service_role",self.sql)
        for func,args in (
            ("factory_peek_planned_work","text,integer"),
            ("factory_dispatch_preapproved_planned_task","text,uuid,text,text,integer,boolean,jsonb,text,boolean,jsonb"),
        ):
            self.assertIn("revoke all on function public."+func+"("+args+")",self.sql)
            self.assertIn("grant execute on function public."+func+"("+args+")",self.sql)
        self.assertEqual(self.sql.count("security invoker"),2)

    def test_model_and_manual_codex_routes_are_independent(self):
        code=RUNTIME.read_text()
        self.assertIn("def allowed_dispatch_routes()",code)
        self.assertIn("FACTORY_DISPATCH_MANUAL_CODEX_READY",code)
        self.assertIn("FACTORY_CODEX_MANUAL_FALLBACK_ENABLED",code)
        self.assertIn('enabled.append("codex")',code)
        self.assertIn('enabled.append("direct")',code)
        self.assertIn("allowed_routes=allowed_routes",code)
        self.assertNotIn("auto_merge",code)
        workflow=WORKFLOW.read_text()
        dispatch=workflow.split("\n  dispatch:\n",1)[1].split("\n  direct:\n",1)[0]
        self.assertIn("FACTORY_DISPATCH_MANUAL_CODEX_READY",dispatch)
        self.assertNotIn("OPENAI_API_KEY:",dispatch)
        self.assertNotIn("CODEX_ACCESS_TOKEN:",dispatch)
        self.assertNotIn("OPENAI_FEDERATION_RULE_ID:",dispatch)

if __name__=="__main__":
    unittest.main()
