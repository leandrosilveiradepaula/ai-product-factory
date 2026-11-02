"""Adversarial, no-model V2 pre-provider lease recovery in isolated PostgreSQL.

This never opens any network connection to a Supabase project or GitHub.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg.types.json import Jsonb

dsn = os.environ.get("FACTORY_PREPROVIDER_TEST_DSN", "")
parsed = urlsplit(dsn)
if (parsed.scheme != "postgresql" or parsed.hostname not in ("localhost", "127.0.0.1")
        or parsed.port != 5432 or parsed.path != "/preprovider_recovery_test"
        or parsed.query or parsed.fragment):
    raise SystemExit("REFUSING_NON_ISOLATED_PREPROVIDER_DATABASE")

migration = (
    Path(__file__).resolve().parents[1]
    / "supabase/migrations/20261102190000_v2_preprovider_auth_lease_recovery.sql"
).read_text()

project = "2d30e00a-ff72-4044-b838-011c263ed672"
journey = "bb14e150-2c7e-423b-8e5d-e211dab6225c"
run_id = "b11daad8-dfc2-4a42-ba4a-a98e0d529238"
task = "11111111-1111-4111-8111-111111111111"
change_set = "3f09952e-0384-46ee-97aa-a46c89346678"
unit = "179b34b0-e8f2-4055-bd28-7c7a89de3fc0"
gate = "edbee01d-1d23-4e6b-a7a0-0b5a562183d4"
source_sha = "b1935c8f6e61ae246eb8958673b2a9e18c3da81f"
factory_sha = "1683787407ed82483288b759d70d413e99fb6d35"
claim_time = "2026-11-02T17:13:25.266829+00:00"
binding = {"source_commit": source_sha, "execution_generation": 19, "journey_id": journey}


def recover(db, uid=run_id, workflow=41488749263, sha=factory_sha):
    with db.cursor() as cur:
        cur.execute(
            "select public.factory_recover_v2_preprovider_auth_once(%s,%s,%s)",
            (uid, workflow, sha),
        )
        return cur.fetchone()[0]


def rejects(db, attempt):
    try:
        with db.transaction():
            attempt()
    except psycopg.Error:
        return
    raise AssertionError("unauthorized pre-provider recovery accepted")


with psycopg.connect(dsn, autocommit=True) as db:
    with db.cursor() as cur:
        cur.execute("drop schema public cascade; create schema public;")
        cur.execute("""
          do $$ begin
            if not exists (select 1 from pg_roles where rolname='service_role') then create role service_role; end if;
            if not exists (select 1 from pg_roles where rolname='anon') then create role anon; end if;
            if not exists (select 1 from pg_roles where rolname='authenticated') then create role authenticated; end if;
          end $$;
          create table public.factory_projects(id uuid primary key,is_active boolean);
          create table public.factory_project_execution_controls(project_id uuid,state text,generation bigint);
          create table public.factory_journeys(
            id uuid primary key,project_id uuid,state text,execution_generation bigint,
            source_commit text,binding jsonb,candidate_commit text,
            work_unit_output_commit text,preview_merge_sha text,production_release_sha text);
          create table public.factory_tasks(
            id uuid primary key,project_id uuid,status text,updated_at timestamptz);
          create table public.factory_runs(
            id uuid primary key,task_id uuid,journey_id uuid,status text,
            execution_route text,source_commit text,attempt_count integer,
            lease_owner text,lease_expires_at timestamptz,last_error text,
            finished_at timestamptz,metadata jsonb);
          create table public.factory_change_sets(
            id uuid primary key,project_id uuid,journey_id uuid,status text,
            metadata jsonb,source_commit text,candidate_commit text,
            release_run_id uuid,lease_owner text,lease_expires_at timestamptz,
            updated_at timestamptz);
          create table public.factory_change_set_work_units(
            id uuid primary key,change_set_id uuid,task_id uuid,status text,
            base_commit text,output_commit text,changed_files jsonb,
            updated_at timestamptz);
          create table public.factory_human_gates(
            id uuid primary key,run_id uuid,status text,resolved_at timestamptz);
          create table public.factory_tool_usage(
            id bigint generated always as identity,run_id uuid,
            created_at timestamptz,tool_family text,operation text);
          create table public.factory_run_agent_assignments(
            run_id uuid,status text);
          create table public.factory_agent_scope_locks(
            run_id uuid,released_at timestamptz,lease_expires_at timestamptz);
          create table public.factory_audit_events(
            id bigint generated always as identity,project_id uuid,task_id uuid,
            run_id uuid,actor_type text,actor_ref text,event_type text,
            payload jsonb,created_at timestamptz default now());
        """)
        cur.execute(migration)
        cur.execute("insert into public.factory_projects values (%s,true)", (project,))
        cur.execute("insert into public.factory_project_execution_controls values(%s,'running',19)", (project,))
        cur.execute("""insert into public.factory_journeys values
          (%s,%s,'executing',19,%s,%s,null,null,null,null)""",
          (journey, project, source_sha, Jsonb(binding)))
        cur.execute("insert into public.factory_tasks values(%s,%s,'failed',now())", (task, project))
        cur.execute("""insert into public.factory_runs values
          (%s,%s,%s,'failed','direct',%s,3,null,null,
          'lease expired after maximum attempts',now(),%s)""",
          (run_id, task, journey, source_sha, Jsonb({
              "journey_binding_v2": binding, "execution_generation": 19,
              "decision_gate_resolution": "approved",
              "execution_worker_id": "gha-direct-41488749263-0",
          })))
        cur.execute("""insert into public.factory_change_sets values
          (%s,%s,%s,'blocked',%s,%s,%s,null,null,null,now())""",
          (change_set, project, journey, Jsonb({"blocker": "builder_retry_exhausted"}),
           source_sha, source_sha))
        cur.execute("""insert into public.factory_change_set_work_units values
          (%s,%s,%s,'failed',%s,null,'[]'::jsonb,now())""",
          (unit, change_set, task, source_sha))
        cur.execute("insert into public.factory_human_gates values(%s,%s,'approved',%s)",
                    (gate, run_id, "2026-11-02T17:11:14.709061+00:00"))
        cur.execute("""insert into public.factory_audit_events
          (project_id,task_id,run_id,actor_type,actor_ref,event_type,payload,created_at)
          values(%s,%s,%s,'agent','development','execution.direct.claimed',%s,%s)""",
          (project, task, run_id, Jsonb({"worker_id": "gha-direct-41488749263-0"}), claim_time))
        cur.execute("""insert into public.factory_audit_events
          (project_id,task_id,run_id,actor_type,actor_ref,event_type,payload,created_at)
          values(%s,%s,%s,'system','lease-recovery','run.lease_recovered','{}'::jsonb,
          '2026-11-02T18:27:31.797586+00:00')""", (project, task, run_id))
        # Older model usage is historical evidence and must stay intact.
        cur.execute("""insert into public.factory_tool_usage
          (run_id,created_at,tool_family,operation) values
          (%s,'2026-11-02T14:56:03.845606+00:00','openai','model_call')""", (run_id,))

    rejects(db, lambda: recover(db, uid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))
    rejects(db, lambda: recover(db, workflow=41488749264))
    rejects(db, lambda: recover(db, sha="0" * 40))
    with db.cursor() as cur:
        cur.execute("update public.factory_project_execution_controls set state='paused'")
    rejects(db, lambda: recover(db))
    with db.cursor() as cur:
        cur.execute("update public.factory_project_execution_controls set state='running'")
        cur.execute("update public.factory_journeys set source_commit=%s", ("c" * 40,))
    rejects(db, lambda: recover(db))
    with db.cursor() as cur:
        cur.execute("update public.factory_journeys set source_commit=%s", (source_sha,))
        cur.execute("insert into public.factory_tool_usage(run_id,created_at,tool_family,operation) values(%s,'2026-11-02T17:14:00+00:00','openai','model_call')", (run_id,))
    rejects(db, lambda: recover(db))
    with db.cursor() as cur:
        cur.execute("delete from public.factory_tool_usage where created_at>'2026-11-02T17:13:26+00:00'")
        cur.execute("update public.factory_change_set_work_units set output_commit=%s", ("a" * 40,))
    rejects(db, lambda: recover(db))
    with db.cursor() as cur:
        cur.execute("update public.factory_change_set_work_units set output_commit=null")
        cur.execute("insert into public.factory_run_agent_assignments values(%s,'claimed')", (run_id,))
    rejects(db, lambda: recover(db))
    with db.cursor() as cur:
        cur.execute("delete from public.factory_run_agent_assignments")
        cur.execute("update public.factory_human_gates set status='pending'")
    rejects(db, lambda: recover(db))
    with db.cursor() as cur:
        cur.execute("update public.factory_human_gates set status='approved'")
        cur.execute("select prosecdef from pg_proc where oid='public.factory_recover_v2_preprovider_auth_once(uuid,bigint,text)'::regprocedure")
        assert cur.fetchone()[0] is False
        for role, can_execute in [("anon", False), ("authenticated", False), ("service_role", True)]:
            cur.execute("select has_function_privilege(%s,'public.factory_recover_v2_preprovider_auth_once(uuid,bigint,text)','EXECUTE')", (role,))
            assert cur.fetchone()[0] is can_execute, role

    receipt = recover(db)
    assert receipt["requeued"] is True and receipt["attempt_count"] == 3
    assert receipt["release_authorized"] is False and receipt["run_id"] == run_id
    replay = recover(db)
    assert replay["requeued"] is False and replay["status"] == "queued"
    with db.cursor() as cur:
        cur.execute("select status,attempt_count,lease_owner,metadata from public.factory_runs where id=%s", (run_id,))
        status, attempts, owner, metadata = cur.fetchone()
        assert status == "queued" and attempts == 3 and owner is None
        assert metadata["preprovider_auth_recovery_once"] == "factory-v2-preprovider-github-broker-403-v1"
        cur.execute("select status from public.factory_tasks where id=%s", (task,))
        assert cur.fetchone()[0] == "queued_execution"
        cur.execute("select status from public.factory_change_set_work_units where id=%s", (unit,))
        assert cur.fetchone()[0] == "queued"
        cur.execute("select status from public.factory_change_sets where id=%s", (change_set,))
        assert cur.fetchone()[0] == "building"
        cur.execute("select count(*) from public.factory_audit_events where event_type='journey.v2.preprovider_auth_lease_requeued'")
        assert cur.fetchone()[0] == 1
        cur.execute("select count(*) from public.factory_tool_usage where run_id=%s", (run_id,))
        assert cur.fetchone()[0] == 1

print("V2_PREPROVIDER_AUTH_RECOVERY_POSTGRES_PASS")
