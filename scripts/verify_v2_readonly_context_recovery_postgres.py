"""No-network adversarial QA for exact V2 read-only context recovery.

Only the disposable PostgreSQL service on localhost:5432 is accepted.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg.types.json import Jsonb

DSN = os.environ.get("FACTORY_READONLY_CONTEXT_QA_DSN", "")
parsed = urlsplit(DSN)
if (parsed.scheme != "postgresql" or parsed.hostname not in ("127.0.0.1", "localhost")
        or parsed.port != 5432 or parsed.path != "/readonly_context_qa"
        or parsed.query or parsed.fragment):
    raise SystemExit("REFUSING_NON_ISOLATED_DATABASE")

sql = (
    Path(__file__).resolve().parents[1]
    / "supabase/migrations/20261102211000_v2_readonly_context_recovery.sql"
).read_text()
project = "2d30e00a-ff72-4044-b838-011c263ed672"
journey = "bb14e150-2c7e-423b-8e5d-e211dab6225c"
run_id = "b11daad8-dfc2-4a42-ba4a-a98e0d529238"
task = "11111111-1111-4111-8111-111111111111"
cs = "3f09952e-0384-46ee-97aa-a46c89346678"
unit = "179b34b0-e8f2-4055-bd28-7c7a89de3fc0"
gate = "edbee01d-1d23-4e6b-a7a0-0b5a562183d4"
source_sha = "b1935c8f6e61ae246eb8958673b2a9e18c3da81f"
factory_sha = "81de8b1d5c0fd41948fae657b2d9ce31ed42d11e"
binding = {"source_commit": source_sha, "execution_generation": 19, "journey_id": journey}
incident = "v2-readonly-source-context-41523358424-v1"


def call(db, uid=run_id, workflow=41523358424, sha=factory_sha, branch=source_sha):
    with db.cursor() as cur:
        cur.execute(
            "select public.factory_recover_v2_readonly_context_once(%s,%s,%s,%s)",
            (uid, workflow, sha, branch),
        )
        return cur.fetchone()[0]


def refuses(db, fn):
    try:
        with db.transaction():
            fn()
    except psycopg.Error:
        return
    raise AssertionError("unsafe recovery did not fail closed")


with psycopg.connect(DSN, autocommit=True) as db:
    with db.cursor() as cur:
        cur.execute("drop schema public cascade; create schema public;")
        cur.execute("""
          do $$ begin
            if not exists(select 1 from pg_roles where rolname='service_role') then create role service_role; end if;
            if not exists(select 1 from pg_roles where rolname='anon') then create role anon; end if;
            if not exists(select 1 from pg_roles where rolname='authenticated') then create role authenticated; end if;
          end $$;
          create table public.factory_projects(id uuid primary key,is_active boolean,repository text);
          create table public.factory_project_execution_controls(project_id uuid,state text,generation bigint);
          create table public.factory_journeys(
            id uuid primary key,project_id uuid,state text,execution_generation bigint,
            source_commit text,binding jsonb,candidate_commit text,
            work_unit_output_commit text,preview_merge_sha text,production_release_sha text);
          create table public.factory_tasks(id uuid primary key,project_id uuid,status text,updated_at timestamptz);
          create table public.factory_runs(
            id uuid primary key,task_id uuid,journey_id uuid,status text,
            execution_route text,source_commit text,attempt_count int,
            lease_owner text,lease_expires_at timestamptz,last_error text,
            finished_at timestamptz,metadata jsonb);
          create table public.factory_change_sets(
            id uuid primary key,project_id uuid,journey_id uuid,status text,
            metadata jsonb,source_commit text,candidate_commit text,release_run_id uuid,
            lease_owner text,lease_expires_at timestamptz,updated_at timestamptz);
          create table public.factory_change_set_work_units(
            id uuid primary key,change_set_id uuid,task_id uuid,status text,
            base_commit text,output_commit text,changed_files jsonb,updated_at timestamptz);
          create table public.factory_human_gates(
            id uuid primary key,run_id uuid,status text,gate_type text,
            resolved_at timestamptz,resolution jsonb);
          create table public.factory_tool_usage(
            id bigint generated always as identity,run_id uuid,created_at timestamptz,
            tool_family text,operation text,estimated_cost numeric);
          create table public.factory_run_agent_assignments(run_id uuid,status text);
          create table public.factory_agent_scope_locks(
            run_id uuid,released_at timestamptz,lease_expires_at timestamptz);
          create table public.factory_audit_events(
            id bigint generated always as identity,project_id uuid,task_id uuid,run_id uuid,
            actor_type text,actor_ref text,event_type text,payload jsonb,
            created_at timestamptz default now());
        """)
        cur.execute(sql)
        cur.execute("insert into public.factory_projects values (%s,true,%s)",
                    (project, "leandrosilveiradepaula/crm-infodive"))
        cur.execute("insert into public.factory_project_execution_controls values(%s,'running',19)", (project,))
        cur.execute("""insert into public.factory_journeys values
          (%s,%s,'executing',19,%s,%s,null,null,null,null)""",
          (journey, project, source_sha, Jsonb(binding)))
        cur.execute("insert into public.factory_tasks values(%s,%s,'blocked',now())", (task, project))
        cur.execute("""insert into public.factory_runs values
          (%s,%s,%s,'blocked','direct',%s,4,null,null,%s,now(),%s)""",
          (run_id, task, journey, source_sha,
           "The available authorized source snapshot contains only ContractService",
           Jsonb({
               "journey_binding_v2": binding, "execution_generation": 19,
               "decision_gate_resolution": "approved",
               "preprovider_auth_recovery_once": "factory-v2-preprovider-github-broker-403-v1",
           })))
        cur.execute("""insert into public.factory_change_sets values
          (%s,%s,%s,'blocked',%s,%s,%s,null,null,null,now())""",
          (cs, project, journey, Jsonb({"blocker": {
              "type": "repository_governance", "run_id": run_id,
              "work_unit_id": unit, "reason": "insufficient source context",
          }}), source_sha, source_sha))
        cur.execute("""insert into public.factory_change_set_work_units values
          (%s,%s,%s,'blocked',%s,null,'[]'::jsonb,now())""",
          (unit, cs, task, source_sha))
        cur.execute("""insert into public.factory_human_gates values
          (%s,%s,'approved','material_requirement_change',
           '2026-11-02T17:11:14.709061+00:00',%s)""",
          (gate, run_id, Jsonb({"resolution": "approved"})))
        cur.execute("""insert into public.factory_audit_events
          (project_id,task_id,run_id,actor_type,actor_ref,event_type,payload,created_at)
          values(%s,%s,%s,'agent','development','execution.direct.claimed',%s,
             '2026-11-02T20:55:56.216782+00:00')""",
          (project, task, run_id, Jsonb({"worker_id": "gha-direct-41523358424-0"})))
        cur.execute("""insert into public.factory_audit_events
          (project_id,task_id,run_id,actor_type,actor_ref,event_type,payload,created_at)
          values(%s,%s,%s,'system','governance','change_set.work_unit.blocked','{}'::jsonb,
            '2026-11-02T20:56:27.634693+00:00')""", (project, task, run_id))
        cur.execute("""insert into public.factory_tool_usage
          (run_id,created_at,tool_family,operation,estimated_cost) values
          (%s,'2026-11-02T20:56:15.838666+00:00','openai','model_call',0.024666),
          (%s,'2026-11-02T14:56:03.845606+00:00','openai','model_call',0.020858)""",
          (run_id, run_id))

    refuses(db, lambda: call(db, workflow=1))
    refuses(db, lambda: call(db, sha="0" * 40))
    refuses(db, lambda: call(db, branch="c" * 40))
    with db.cursor() as cur:
        cur.execute("update public.factory_project_execution_controls set generation=20")
    refuses(db, lambda: call(db))
    with db.cursor() as cur:
        cur.execute("update public.factory_project_execution_controls set generation=19")
        cur.execute("update public.factory_human_gates set status='pending'")
    refuses(db, lambda: call(db))
    with db.cursor() as cur:
        cur.execute("update public.factory_human_gates set status='approved'")
        cur.execute("""insert into public.factory_tool_usage
          (run_id,created_at,tool_family,operation,estimated_cost) values
          (%s,'2026-11-02T20:56:16+00:00','openai','model_call',null)""", (run_id,))
    refuses(db, lambda: call(db))
    with db.cursor() as cur:
        cur.execute("delete from public.factory_tool_usage where estimated_cost is null")
        cur.execute("update public.factory_change_set_work_units set output_commit=%s",
                    ("c" * 40,))
    refuses(db, lambda: call(db))
    with db.cursor() as cur:
        cur.execute("update public.factory_change_set_work_units set output_commit=null")
        cur.execute("insert into public.factory_run_agent_assignments values(%s,'assigned')", (run_id,))
    refuses(db, lambda: call(db))
    with db.cursor() as cur:
        cur.execute("delete from public.factory_run_agent_assignments")
        cur.execute("""select prosecdef from pg_proc where
          oid='public.factory_recover_v2_readonly_context_once(uuid,bigint,text,text)'::regprocedure""")
        assert cur.fetchone()[0] is False
        for role, allowed in [("anon", False), ("authenticated", False), ("service_role", True)]:
            cur.execute("""select has_function_privilege(
              %s,'public.factory_recover_v2_readonly_context_once(uuid,bigint,text,text)','EXECUTE')""",
                        (role,))
            assert cur.fetchone()[0] is allowed

    result = call(db)
    assert result["requeued"] is True
    assert result["attempt_count"] == 4
    assert result["release_authorized"] is False
    assert result["run_id"] == run_id
    replay = call(db)
    assert replay["requeued"] is False
    assert replay["attempt_count"] == 4
    with db.cursor() as cur:
        cur.execute("select status,attempt_count,metadata from public.factory_runs where id=%s", (run_id,))
        status, attempts, meta = cur.fetchone()
        assert status == "queued" and attempts == 4
        assert meta["v2_readonly_context_recovery_once"] == incident
        cur.execute("select status from public.factory_change_sets where id=%s", (cs,))
        assert cur.fetchone()[0] == "building"
        cur.execute("select status from public.factory_change_set_work_units where id=%s", (unit,))
        assert cur.fetchone()[0] == "queued"
        cur.execute("select status from public.factory_tasks where id=%s", (task,))
        assert cur.fetchone()[0] == "queued_execution"
        cur.execute("""select count(*) from public.factory_audit_events
          where event_type='journey.v2.readonly_context_requeued'""")
        assert cur.fetchone()[0] == 1
        cur.execute("select count(*) from public.factory_tool_usage where run_id=%s", (run_id,))
        assert cur.fetchone()[0] == 2

print("V2_READONLY_CONTEXT_RECOVERY_POSTGRES_PASS")
