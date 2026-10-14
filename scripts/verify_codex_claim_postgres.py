#!/usr/bin/env python3
"""Real PostgreSQL integration tests for Codex mode/claim isolation.

Only works on a dedicated local test database. Production/Supabase connections
are intentionally rejected. Loads the exact SQL function definitions committed
in the Factory migrations, while using a small explicit schema fixture.
The generic agent-slot allocator is a fixture, NOT the production allocator.
"""
from __future__ import annotations

import os
import re
import time
import unittest
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb


ROOT = Path(__file__).resolve().parents[1]
MODE = ROOT / "supabase/migrations/20261014015500_codex_atomic_mode_isolation.sql"
HARDEN = ROOT / "supabase/migrations/20261014032600_codex_claim_agent_hardening.sql"
DSN = os.getenv("FACTORY_CODEX_PG_TEST_DSN", "")

# No remote database may ever receive fixture writes, even accidentally.
def require_isolated_test_db() -> None:
    if os.getenv("FACTORY_CODEX_PG_TEST_ISOLATED") != "true":
        raise RuntimeError("isolated PostgreSQL test opt-in required")
    config = conninfo_to_dict(DSN)
    if config.get("host") not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("PostgreSQL claim test refuses non-local host")
    if config.get("dbname") != "factory_codex_claim_test":
        raise RuntimeError("PostgreSQL claim test refuses non-dedicated database")


def function_definition(file: Path, name: str) -> str:
    sql = file.read_text()
    pattern = (
        r"CREATE OR REPLACE FUNCTION public\."
        + re.escape(name)
        + r"\([^\n]+\).*?\$function\$;"
    )
    match = re.search(pattern, sql, flags=re.DOTALL | re.IGNORECASE)
    if match is None:
        raise AssertionError(f"versioned function not found: {name}")
    return match.group(0)


SETUP = """
CREATE TABLE public.factory_projects (
  id uuid PRIMARY KEY, project_key text NOT NULL,
  repository text NOT NULL, is_active boolean NOT NULL
);
CREATE TABLE public.factory_tasks (
  id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES public.factory_projects,
  status text NOT NULL, title text NOT NULL, description text,
  agent_role text, required_capabilities jsonb NOT NULL DEFAULT '[]',
  scope_keys jsonb NOT NULL DEFAULT '[]', updated_at timestamptz
);
CREATE TABLE public.factory_runs (
  id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES public.factory_tasks,
  status text NOT NULL, execution_route text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz, lease_owner text, lease_expires_at timestamptz,
  attempt_count integer NOT NULL DEFAULT 0, last_error text
);
CREATE TABLE public.factory_agents (
  id uuid PRIMARY KEY, agent_key text NOT NULL, role text NOT NULL,
  is_active boolean NOT NULL, allowed_tools jsonb NOT NULL,
  capabilities jsonb NOT NULL, max_concurrency integer NOT NULL DEFAULT 1,
  model_policy jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE public.factory_run_agent_assignments (
  id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES public.factory_runs,
  agent_id uuid NOT NULL REFERENCES public.factory_agents,
  status text NOT NULL, assigned_at timestamptz NOT NULL DEFAULT now(),
  claimed_at timestamptz
);
CREATE TABLE public.factory_change_set_work_units (
  id uuid PRIMARY KEY, run_id uuid REFERENCES public.factory_runs,
  status text NOT NULL, change_set_id uuid NOT NULL,
  plan_task_key text NOT NULL, wave integer NOT NULL DEFAULT 1
);
CREATE TABLE public.factory_audit_events (
  project_id uuid, task_id uuid, run_id uuid,
  actor_type text, actor_ref text, event_type text, payload jsonb
);
"""

# The production scheduler delegates to an allocator that needs many other
# tables. This deliberately minimal allocator tests scheduler handoff and
# exact-agent rejection, NOT its separate capacity/scope-lock implementation.
ALLOCATOR_FIXTURE = """
CREATE OR REPLACE FUNCTION public.factory_schedule_run_agent(
  p_run_id uuid, p_preferred_role text DEFAULT NULL,
  p_required_capabilities jsonb DEFAULT '[]'::jsonb,
  p_scope_keys jsonb DEFAULT '[]'::jsonb,
  p_lease_seconds integer DEFAULT 900
) RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE v_agent public.factory_agents%rowtype; v_assignment_id uuid;
BEGIN
  SELECT a.* INTO v_agent
  FROM public.factory_agents a
  WHERE a.is_active
    AND (p_preferred_role IS NULL OR a.agent_key=p_preferred_role OR a.role=p_preferred_role)
    AND NOT EXISTS (
      SELECT 1 FROM jsonb_array_elements_text(p_required_capabilities) cap(value)
      WHERE NOT (a.capabilities ? cap.value)
    )
  ORDER BY CASE WHEN a.agent_key=p_preferred_role THEN 0 ELSE 1 END, a.agent_key
  FOR UPDATE OF a SKIP LOCKED LIMIT 1;
  IF v_agent.id IS NULL THEN RETURN NULL; END IF;
  v_assignment_id:=gen_random_uuid();
  INSERT INTO public.factory_run_agent_assignments(id,run_id,agent_id,status)
  VALUES(v_assignment_id,p_run_id,v_agent.id,'assigned');
  RETURN jsonb_build_object(
    'assignment_id',v_assignment_id,'agent_id',v_agent.id,
    'agent_key',v_agent.agent_key,'role',v_agent.role,
    'max_concurrency',v_agent.max_concurrency,
    'model_policy',v_agent.model_policy,
    'allowed_tools',v_agent.allowed_tools
  );
END; $$;
"""

PROJECT = "00000000-0000-0000-0000-000000000001"
AGENT = "00000000-0000-0000-0000-000000000002"
BAD_AGENT = "00000000-0000-0000-0000-000000000003"
CHANGE_SET = "00000000-0000-0000-0000-000000000004"


def uuid_for(num: int) -> str:
    return f"00000000-0000-0000-0000-{num:012d}"


def connection(*, autocommit: bool = False):
    return psycopg.connect(DSN, autocommit=autocommit, connect_timeout=5)


class CodexPostgresClaims(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_isolated_test_db()
        with connection(autocommit=True) as conn:
            if conn.execute("select current_database()").fetchone()[0] != "factory_codex_claim_test":
                raise RuntimeError("database name unexpectedly changed")
            for name in ("anon", "authenticated", "service_role"):
                conn.execute(f"CREATE ROLE {name} NOLOGIN")
            conn.execute(SETUP)
            conn.execute(ALLOCATOR_FIXTURE)
            for file, name in (
                (MODE, "factory_claim_next_manual_codex_handoff"),
                (HARDEN, "factory_claim_next_agent_codex_run"),
                (HARDEN, "factory_schedule_eligible_codex_run"),
                (HARDEN, "factory_agent_work_matrix"),
            ):
                conn.execute(function_definition(file, name))
            for signature in (
                "public.factory_claim_next_manual_codex_handoff(text)",
                "public.factory_claim_next_agent_codex_run(text,text,uuid)",
                "public.factory_schedule_eligible_codex_run(uuid,text)",
                "public.factory_agent_work_matrix(integer)",
            ):
                conn.execute(f"REVOKE ALL ON FUNCTION {signature} FROM public,anon,authenticated")
                conn.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO service_role")

    def setUp(self):
        with connection(autocommit=True) as conn:
            conn.execute("TRUNCATE public.factory_audit_events, public.factory_run_agent_assignments, "
                         "public.factory_change_set_work_units, public.factory_runs, public.factory_tasks, "
                         "public.factory_agents, public.factory_projects CASCADE")
            conn.execute(
                "INSERT INTO public.factory_projects(id,project_key,repository,is_active) "
                "VALUES (%s,'test-project','owner/test-repo',true)", (PROJECT,))
            self.agent(conn, AGENT, "codex-dev", ["codex", "github_write"], ["build"])

    def agent(self, conn, agent_id, key, tools, capabilities, *, active=True):
        conn.execute(
            "INSERT INTO public.factory_agents(id,agent_key,role,is_active,allowed_tools,capabilities) "
            "VALUES (%s,%s,'development',%s,%s,%s)",
            (agent_id, key, active, Jsonb(tools), Jsonb(capabilities)))

    def seed(self, n: int, mode: str | None, *, route="codex", assigned=True,
             requirements=None, active_unit=True):
        run_id, task_id = uuid_for(1000 + n), uuid_for(2000 + n)
        with connection(autocommit=True) as conn:
            conn.execute(
                "INSERT INTO public.factory_tasks(id,project_id,status,title,description,agent_role,"
                "required_capabilities,scope_keys) VALUES (%s,%s,'queued_execution',%s,'test','development',%s,'[]')",
                (task_id, PROJECT, "Task " + str(n), Jsonb(requirements or [])))
            metadata = {} if mode is None else {"codex_execution_mode": mode}
            conn.execute(
                "INSERT INTO public.factory_runs(id,task_id,status,execution_route,metadata) "
                "VALUES (%s,%s,'queued',%s,%s)",
                (run_id, task_id, route, Jsonb(metadata)))
            if assigned:
                conn.execute(
                    "INSERT INTO public.factory_run_agent_assignments(id,run_id,agent_id,status) "
                    "VALUES (%s,%s,%s,'assigned')", (uuid_for(3000 + n), run_id, AGENT))
            if active_unit:
                conn.execute(
                    "INSERT INTO public.factory_change_set_work_units(id,run_id,status,change_set_id,plan_task_key,wave) "
                    "VALUES (%s,%s,'queued',%s,'task',1)", (uuid_for(4000 + n), run_id, CHANGE_SET))
        return run_id

    def manual(self, conn):
        return conn.execute(
            "SELECT public.factory_claim_next_manual_codex_handoff('manual-test')"
        ).fetchone()[0]

    def automatic(self, conn, run_id=None, agent="codex-dev"):
        return conn.execute(
            "SELECT public.factory_claim_next_agent_codex_run(%s,%s,%s)",
            ("auto-test", agent, run_id)
        ).fetchone()[0]

    def status(self, run_id):
        with connection(autocommit=True) as conn:
            return conn.execute("SELECT status,attempt_count FROM public.factory_runs WHERE id=%s",
                                (run_id,)).fetchone()

    def audit_count(self, run_id):
        with connection(autocommit=True) as conn:
            return conn.execute("SELECT count(*) FROM public.factory_audit_events WHERE run_id=%s",
                                (run_id,)).fetchone()[0]

    def test_two_automatic_transactions_cannot_claim_same_run(self):
        run = self.seed(1, "automatic")
        with connection() as a, connection() as b:
            first = self.automatic(a, run)
            self.assertEqual(first["run_id"], run)
            # Transaction A still holds the row lock. B must SKIP LOCKED.
            started = time.monotonic()
            second = self.automatic(b, run)
            self.assertIsNone(second)
            self.assertLess(time.monotonic() - started, 2.0)
            a.commit()
            b.commit()
        self.assertEqual(self.status(run), ("implementing", 1))
        self.assertEqual(self.audit_count(run), 1)

    def test_two_manual_transactions_cannot_claim_same_run(self):
        run = self.seed(2, "manual", assigned=False, active_unit=False)
        with connection() as a, connection() as b:
            self.assertEqual(self.manual(a)["run_id"], run)
            self.assertIsNone(self.manual(b))
            a.commit()
            b.commit()
        self.assertEqual(self.status(run), ("preparing_codex_manual", 1))
        self.assertEqual(self.audit_count(run), 1)

    def test_competing_modes_claim_distinct_runs(self):
        auto = self.seed(3, "automatic")
        manual = self.seed(4, "manual", assigned=False, active_unit=False)
        with connection() as a, connection() as b:
            self.assertEqual(self.manual(a)["run_id"], manual)
            self.assertEqual(self.automatic(b, auto)["run_id"], auto)
            a.commit()
            b.commit()
        self.assertEqual(self.status(auto), ("implementing", 1))
        self.assertEqual(self.status(manual), ("preparing_codex_manual", 1))

    def test_untagged_and_direct_are_rejected_by_both_claimers(self):
        legacy = self.seed(5, None)
        direct = self.seed(6, "automatic", route="direct")
        with connection(autocommit=True) as conn:
            self.assertIsNone(self.manual(conn))
            self.assertIsNone(self.automatic(conn))
        for run in (legacy, direct):
            self.assertEqual(self.status(run), ("queued", 0))
            self.assertEqual(self.audit_count(run), 0)

    def test_wrong_agent_key_is_not_claimed(self):
        run = self.seed(7, "automatic")
        with connection(autocommit=True) as conn:
            self.assertIsNone(self.automatic(conn, run, agent="other-agent"))
        self.assertEqual(self.status(run), ("queued", 0))

    def test_incompatible_agent_capabilities_and_tools_fail_closed(self):
        run = self.seed(8, "automatic", requirements=["build", "ops"])
        with connection(autocommit=True) as conn:
            self.assertIsNone(self.automatic(conn, run))
            conn.execute(
                "UPDATE public.factory_agents SET capabilities=%s WHERE id=%s",
                (Jsonb(["build", "ops"]), AGENT))
            conn.execute(
                "UPDATE public.factory_agents SET allowed_tools=%s WHERE id=%s",
                (Jsonb(["codex"]), AGENT))
            self.assertIsNone(self.automatic(conn, run))
        self.assertEqual(self.status(run), ("queued", 0))

    def test_inactive_project_or_missing_unit_fail_closed(self):
        run = self.seed(9, "automatic")
        with connection(autocommit=True) as conn:
            conn.execute("UPDATE public.factory_projects SET is_active=false WHERE id=%s", (PROJECT,))
            self.assertIsNone(self.automatic(conn, run))
            conn.execute("UPDATE public.factory_projects SET is_active=true WHERE id=%s", (PROJECT,))
            conn.execute(
                "UPDATE public.factory_change_set_work_units SET status='pending' WHERE run_id=%s",
                (run,))
            with self.assertRaisesRegex(psycopg.Error, "queued change-set work unit"):
                self.automatic(conn, run)
        self.assertEqual(self.status(run), ("queued", 0))

    def test_matrix_hides_legacy_and_incompatible_assignments(self):
        self.seed(10, None)
        self.seed(11, "automatic", requirements=["missing"])
        valid = self.seed(12, "automatic")
        with connection(autocommit=True) as conn:
            matrix = conn.execute("SELECT public.factory_agent_work_matrix(20)").fetchone()[0]
        self.assertEqual([v["run_id"] for v in matrix["codex"]], [valid])
        self.assertEqual(matrix["direct"], [])

    def test_scheduler_exact_mode_and_incompatible_agent(self):
        run = self.seed(13, "automatic", assigned=False)
        manual = self.seed(14, "manual", assigned=False, active_unit=False)
        with connection(autocommit=True) as conn:
            self.assertIsNone(conn.execute(
                "SELECT public.factory_schedule_eligible_codex_run(%s,%s)",
                (manual, "test-project")).fetchone()[0])
            result = conn.execute(
                "SELECT public.factory_schedule_eligible_codex_run(%s,%s)",
                (run, "test-project")).fetchone()[0]
            self.assertEqual(result["run_id"], run)
            self.assertEqual(result["agent_key"], "codex-dev")
            self.assertIsNone(conn.execute(
                "SELECT public.factory_schedule_eligible_codex_run(%s,%s)",
                (run, "test-project")).fetchone()[0])

    def test_functions_private_to_service_role(self):
        signatures = (
            "public.factory_claim_next_manual_codex_handoff(text)",
            "public.factory_claim_next_agent_codex_run(text,text,uuid)",
            "public.factory_schedule_eligible_codex_run(uuid,text)",
            "public.factory_agent_work_matrix(integer)",
        )
        with connection(autocommit=True) as conn:
            for signature in signatures:
                values = conn.execute(
                    "SELECT has_function_privilege('service_role',%s,'EXECUTE'),"
                    "has_function_privilege('anon',%s,'EXECUTE'),"
                    "has_function_privilege('authenticated',%s,'EXECUTE')",
                    (signature, signature, signature)).fetchone()
                self.assertEqual(values, (True, False, False), signature)


if __name__ == "__main__":
    require_isolated_test_db()
    unittest.main(verbosity=2)
