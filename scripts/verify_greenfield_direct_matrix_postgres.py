#!/usr/bin/env python3
"""Exercise the real agent-matrix SQL in disposable PostgreSQL 16.

This is a narrow J3 regression harness.  It deliberately proves the database
boundary that can hide a newly assigned Direct run behind an older global
matrix window; the Python adaptive controller then consumes the exact atomic
scheduling receipt and remains responsible for applying concurrency and cost
limits.  It never contacts Supabase, GitHub, or a model provider.
"""
from __future__ import annotations

import os
from pathlib import Path
import re

import psycopg
from psycopg.conninfo import conninfo_to_dict


cfg = conninfo_to_dict(os.environ.get("FACTORY_GREENFIELD_PG_TEST_DSN", ""))
if (
    os.environ.get("FACTORY_GREENFIELD_PG_TEST_ISOLATED") != "true"
    or cfg.get("host") not in ("127.0.0.1", "localhost")
    or cfg.get("dbname") != "factory_greenfield_test"
):
    raise SystemExit("refusing non-isolated database")

root = Path(__file__).resolve().parents[1]
source = (root / "supabase/migrations/20261014032600_codex_claim_agent_hardening.sql").read_text(
    encoding="utf-8"
)
function_match = re.search(
    r"CREATE OR REPLACE FUNCTION public\.factory_agent_work_matrix\(p_limit integer DEFAULT 12\).*?"
    r"\$function\$;",
    source,
    flags=re.DOTALL,
)
acl_match = re.search(
    r"revoke all on function public\.factory_agent_work_matrix\(integer\) from public,anon,authenticated;\s*"
    r"grant execute on function public\.factory_agent_work_matrix\(integer\) to service_role;",
    source,
    flags=re.DOTALL,
)
if function_match is None or acl_match is None:
    raise SystemExit("current migration no longer contains the expected agent matrix")

schema = """
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='service_role')
 THEN CREATE ROLE service_role NOLOGIN; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon')
 THEN CREATE ROLE anon NOLOGIN; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated')
 THEN CREATE ROLE authenticated NOLOGIN; END IF;
END $$;
create table public.factory_agents(
  id uuid primary key default gen_random_uuid(), agent_key text not null,
  role text not null, is_active boolean not null default true,
  allowed_tools jsonb not null default '[]'::jsonb,
  capabilities jsonb not null default '[]'::jsonb
);
create table public.factory_tasks(
  id uuid primary key default gen_random_uuid(), status text not null,
  required_capabilities jsonb not null default '[]'::jsonb
);
create table public.factory_runs(
  id uuid primary key default gen_random_uuid(), task_id uuid not null,
  execution_route text not null, status text not null,
  metadata jsonb not null default '{}'::jsonb
);
create table public.factory_run_agent_assignments(
  run_id uuid not null, agent_id uuid not null, status text not null,
  assigned_at timestamptz not null default now()
);
"""

with psycopg.connect(os.environ["FACTORY_GREENFIELD_PG_TEST_DSN"], autocommit=True) as conn:
    conn.execute(schema)
    conn.execute(function_match.group(0))
    conn.execute(acl_match.group(0))
    acl = conn.execute(
        """select has_function_privilege('service_role',
             'public.factory_agent_work_matrix(integer)','EXECUTE'),
             has_function_privilege('anon',
             'public.factory_agent_work_matrix(integer)','EXECUTE'),
             has_function_privilege('authenticated',
             'public.factory_agent_work_matrix(integer)','EXECUTE')"""
    ).fetchone()
    assert acl == (True, False, False), acl

    agent = conn.execute(
        """insert into public.factory_agents(agent_key,role,allowed_tools,capabilities)
           values ('development','development','[\"github_write\",\"model_primary\"]','[]')
           returning id"""
    ).fetchone()[0]

    def assign(*, fresh: bool) -> str:
        task = conn.execute(
            "insert into public.factory_tasks(status) values ('queued_execution') returning id"
        ).fetchone()[0]
        run = conn.execute(
            """insert into public.factory_runs(task_id,execution_route,status)
               values (%s,'direct','queued') returning id""",
            (task,),
        ).fetchone()[0]
        conn.execute(
            """insert into public.factory_run_agent_assignments(run_id,agent_id,status,assigned_at)
               values (%s,%s,'assigned',now() + (%s * interval '1 second'))""",
            (run, agent, 1000 if fresh else 0),
        )
        return str(run)

    older = [assign(fresh=False) for _ in range(6)]
    fresh = assign(fresh=True)
    matrix = conn.execute("select public.factory_agent_work_matrix(6)").fetchone()[0]
    direct = matrix["direct"]
    assert len(direct) == 6
    assert {row["run_id"] for row in direct} == set(older)
    assert fresh not in {row["run_id"] for row in direct}

    # The matrix itself must continue to exclude a stale non-executable row.
    stale_task = conn.execute(
        "insert into public.factory_tasks(status) values ('implementing') returning id"
    ).fetchone()[0]
    stale_run = conn.execute(
        """insert into public.factory_runs(task_id,execution_route,status)
           values (%s,'direct','queued') returning id""",
        (stale_task,),
    ).fetchone()[0]
    conn.execute(
        """insert into public.factory_run_agent_assignments(run_id,agent_id,status)
           values (%s,%s,'assigned')""",
        (stale_run, agent),
    )
    matrix = conn.execute("select public.factory_agent_work_matrix(32)").fetchone()[0]
    assert str(stale_run) not in {row["run_id"] for row in matrix["direct"]}

    # Leave the shared disposable database ready for the other independent
    # greenfield scripts.  This runs only after the isolation assertion above.
    conn.execute("drop function public.factory_agent_work_matrix(integer)")
    for table in (
        "factory_run_agent_assignments", "factory_runs", "factory_tasks",
        "factory_agents",
    ):
        conn.execute(f"drop table public.{table}")

print("GREENFIELD_DIRECT_MATRIX_POSTGRES_PASS=1")
