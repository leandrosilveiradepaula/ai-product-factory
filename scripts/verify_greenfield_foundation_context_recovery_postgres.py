#!/usr/bin/env python3
"""Execute greenfield foundation recovery contract on disposable PG16 only."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict

dsn = os.getenv("FACTORY_GREENFIELD_RECOVERY_TEST_DSN", "")
config = conninfo_to_dict(dsn)
if (
    os.getenv("FACTORY_GREENFIELD_RECOVERY_TEST_ISOLATED") != "true"
    or config.get("host") not in ("127.0.0.1", "localhost")
    or config.get("dbname") != "factory_greenfield_recovery_test"
    or config.get("user") != "factory_ci"
):
    raise SystemExit("REFUSING_NON_ISOLATED_GREENFIELD_RECOVERY_DATABASE")

root = Path(__file__).resolve().parents[1]
migration = (
    root / "supabase/migrations/"
    "20261113173000_greenfield_first_wave_context_recovery.sql"
).read_text(encoding="utf-8")
schema = """
create role anon nologin;
create role authenticated nologin;
create role service_role nologin;
create table public.factory_projects (
 id uuid primary key, project_key text, repository text, project_kind text,
 is_active boolean, manifest jsonb
);
create table public.factory_project_execution_controls (
 project_id uuid primary key, state text, generation bigint
);
create table public.factory_tasks (
 id uuid primary key, project_id uuid, title text, status text,
 scope_keys jsonb, updated_at timestamptz
);
create table public.factory_runs (
 id uuid primary key, task_id uuid, status text, execution_route text,
 source_commit text, candidate_commit text, attempt_count integer,
 lease_owner text, lease_expires_at timestamptz, last_error text,
 metadata jsonb
);
create table public.factory_change_sets (
 id uuid primary key, project_id uuid, status text, current_wave integer,
 source_commit text, candidate_commit text, release_run_id uuid,
 journey_id uuid, lease_owner text, lease_expires_at timestamptz,
 metadata jsonb, updated_at timestamptz
);
create table public.factory_change_set_work_units (
 id uuid primary key, change_set_id uuid, task_id uuid, run_id uuid,
 status text, wave integer, plan_task_key text, base_commit text,
 output_commit text, updated_at timestamptz
);
create table public.factory_audit_events (
 id bigint generated always as identity primary key,
 project_id uuid, task_id uuid, run_id uuid, actor_type text,
 actor_ref text, event_type text, payload jsonb
);
"""
project, task, run, change_set, unit = (uuid4() for _ in range(5))
sha = "1b32f948a6dfac4da1cf922901d8047b66e43ac8"
bad = (
    "RuntimeError: repository context discovery found no relevant files; "
    "replan with explicit context_paths"
)
name = "public.factory_resume_greenfield_foundation_context_once"
call = (
    f"select {name}(%s::uuid,%s::uuid,%s::uuid,%s::text,%s::bigint,%s::text)"
)
args = (run, change_set, unit, sha, 1, "Factory PR #1417 merged; exact source and scope verified")
with psycopg.connect(dsn, autocommit=True) as conn:
    conn.execute(schema)
    conn.execute(migration)
    with conn.cursor() as cursor:
        cursor.execute(
            "select has_function_privilege('anon',%s,'EXECUTE'),"
            "has_function_privilege('authenticated',%s,'EXECUTE'),"
            "has_function_privilege('service_role',%s,'EXECUTE')",
            (name + "(uuid,uuid,uuid,text,bigint,text)",) * 3,
        )
        assert cursor.fetchone() == (False, False, True), "EXECUTE ACL not closed"

    conn.execute(
        "insert into public.factory_projects values (%s,%s,%s,%s,%s,%s)",
        (project, "example-greenfield", "example/product", "greenfield", True,
         psycopg.types.json.Jsonb({"source": "factory-console"})),
    )
    conn.execute(
        "insert into public.factory_project_execution_controls values (%s,%s,%s)",
        (project, "running", 1),
    )
    conn.execute(
        "insert into public.factory_tasks (id,project_id,title,status,scope_keys)"
        " values (%s,%s,%s,%s,%s)",
        (task, project, "app-foundation", "blocked",
         psycopg.types.json.Jsonb([
            "application-foundation", "domain-contracts", "test-harness"
         ])),
    )
    conn.execute(
        "insert into public.factory_runs "
        "(id,task_id,status,execution_route,source_commit,candidate_commit,"
        "attempt_count,last_error,metadata) values "
        "(%s,%s,'blocked','direct',null,null,1,%s,%s)",
        (run, task, bad,
         psycopg.types.json.Jsonb({"execution_generation": 1})),
    )
    conn.execute(
        "insert into public.factory_change_sets "
        "(id,project_id,status,current_wave,source_commit,candidate_commit,metadata)"
        " values (%s,%s,'blocked',1,%s,%s,%s)",
        (change_set, project, sha, sha,
         psycopg.types.json.Jsonb({"blocker": {
            "type": "implementation_preflight_error", "reason": bad,
            "run_id": str(run), "work_unit_id": str(unit),
         }})),
    )
    conn.execute(
        "insert into public.factory_change_set_work_units "
        "(id,change_set_id,task_id,run_id,status,wave,plan_task_key,base_commit)"
        " values (%s,%s,%s,%s,'blocked',1,'app-foundation',%s)",
        (unit, change_set, task, run, sha),
    )

    # Adversarial changes are rolled back individually, preserving a clean
    # first-wave source; rejection must not generate an audit event.
    mutations = [
        ("update public.factory_projects set project_kind='existing' where id=%s", (project,)),
        ("update public.factory_project_execution_controls set state='paused' where project_id=%s", (project,)),
        ("update public.factory_tasks set scope_keys='[\"unknown-root\"]'::jsonb where id=%s", (task,)),
        ("update public.factory_change_sets set candidate_commit=%s where id=%s", ("f" * 40, change_set)),
        ("update public.factory_change_sets set current_wave=2 where id=%s", (change_set,)),
        ("update public.factory_runs set attempt_count=5 where id=%s", (run,)),
        ("update public.factory_runs set lease_owner='other-worker' where id=%s", (run,)),
        ("update public.factory_change_sets set metadata='{}'::jsonb where id=%s", (change_set,)),
        ("update public.factory_change_set_work_units set output_commit=%s where id=%s", ("e" * 40,unit)),
    ]
    for statement, params in mutations:
        conn.execute("begin")
        try:
            conn.execute(statement, params)
            try:
                conn.execute(call, args)
            except psycopg.Error:
                pass
            else:
                raise AssertionError("unsafe greenfield recovery accepted: " + statement)
        finally:
            conn.execute("rollback")

    for invalid_args in (
        (run, change_set, unit, "0" * 40, 1, "source drift"),
        (run, change_set, unit, sha, 2, "generation drift"),
        (run, change_set, uuid4(), sha, 1, "unit substitution"),
    ):
        try:
            conn.execute(call, invalid_args)
        except psycopg.Error:
            pass
        else:
            raise AssertionError("incorrect recovery identity accepted")

    receipt = conn.execute(call, args).fetchone()[0]
    assert receipt["requeued"] is True and receipt["release_authorized"] is False
    result = conn.execute(
        "select r.status,t.status,u.status,s.status "
        "from public.factory_runs r,public.factory_tasks t,"
        "public.factory_change_set_work_units u,public.factory_change_sets s "
        "where r.id=%s and t.id=%s and u.id=%s and s.id=%s",
        (run, task, unit, change_set),
    ).fetchone()
    assert result == ("queued", "queued_execution", "queued", "building"), result
    repeat = conn.execute(call, args).fetchone()[0]
    assert repeat["requeued"] is False
    assert conn.execute(
        "select count(*) from public.factory_audit_events "
        "where event_type='change_set.greenfield_foundation_requeued'"
    ).fetchone()[0] == 1
print("GREENFIELD_FOUNDATION_RECOVERY_POSTGRES=PASS")
