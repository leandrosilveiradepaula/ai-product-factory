#!/usr/bin/env python3
"""Real SQL regression for platform-kind blocked Change Set recovery.

Hard abort unless targeting the disposable GitHub Actions PostgreSQL fixture.
No remote DB, OpenAI, model, GitHub writes or production migration.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

DSN = os.getenv("FACTORY_PLATFORM_RECOVERY_TEST_DSN", "")
conf = conninfo_to_dict(DSN)
if (
    os.getenv("FACTORY_PLATFORM_RECOVERY_TEST_ISOLATED") != "true"
    or conf.get("host") not in ("127.0.0.1", "localhost")
    or conf.get("dbname") != "factory_platform_recovery_test"
    or conf.get("user") != "factory_ci"
):
    raise SystemExit("refusing non-isolated platform recovery database")

root = Path(__file__).resolve().parents[1]
migration = (
    root / "supabase/migrations/20261020032500_retry_blocked_platform_kind.sql"
).read_text()

schema = """
create role service_role nologin;
create role anon nologin;
create role authenticated nologin;
create table public.factory_projects (
 id uuid primary key,project_key text,project_kind text,repository text,
 is_active boolean,manifest jsonb
);
create table public.factory_project_execution_controls (
 project_id uuid primary key,state text,generation bigint
);
create table public.factory_tasks (
 id uuid primary key,project_id uuid,parent_task_id uuid,
 status text,updated_at timestamptz default now()
);
create table public.factory_runs (
 id uuid primary key,task_id uuid,status text,
 source_commit text,candidate_commit text,branch_name text,
 lease_owner text,lease_expires_at timestamptz,attempt_count integer,
 last_error text,metadata jsonb
);
create table public.factory_change_sets (
 id uuid primary key,project_id uuid,root_task_id uuid,
 status text,current_wave integer,source_commit text,candidate_commit text,
 integration_branch text,release_run_id uuid,
 lease_owner text,lease_expires_at timestamptz,attempt_count integer,
 metadata jsonb,updated_at timestamptz default now()
);
create table public.factory_change_set_work_units (
 id uuid primary key,change_set_id uuid,task_id uuid,run_id uuid,
 status text,wave integer,base_commit text,branch_name text,
 output_commit text,changed_files jsonb,updated_at timestamptz default now()
);
create table public.factory_audit_events (
 project_id uuid,task_id uuid,run_id uuid,
 actor_type text,actor_ref text,event_type text,payload jsonb
);
"""

project, root_task, task, run, cs, unit = [uuid.uuid4() for _ in range(6)]
reason = "PermissionError: unrecognized project kind"
blocker = {
    "type": "implementation_preflight_error", "reason": reason,
    "run_id": str(run), "work_unit_id": str(unit),
}

with psycopg.connect(DSN, autocommit=True) as db:
    db.execute(schema)
    db.execute(migration)
    perm = db.execute("""
        select p.prosecdef,
          has_function_privilege('service_role',p.oid,'EXECUTE'),
          has_function_privilege('anon',p.oid,'EXECUTE'),
          has_function_privilege('authenticated',p.oid,'EXECUTE')
        from pg_proc p
        where p.proname='factory_retry_blocked_platform_kind'
    """).fetchone()
    assert perm == (False, True, False, False), perm

    db.execute("""
        insert into public.factory_projects
          (id,project_key,project_kind,repository,is_active,manifest)
        values (%s,'factory-fixture','platform','owner/repo',true,'{}'::jsonb)
    """, (project,))
    db.execute("""
        insert into public.factory_project_execution_controls
          (project_id,state,generation) values (%s,'running',3)
    """, (project,))
    db.execute("""
        insert into public.factory_tasks(id,project_id,parent_task_id,status)
        values (%s,%s,null,'completed'),(%s,%s,%s,'blocked')
    """, (root_task,project,task,project,root_task))
    db.execute("""
        insert into public.factory_runs
          (id,task_id,status,source_commit,candidate_commit,branch_name,
           lease_owner,lease_expires_at,attempt_count,last_error,metadata)
        values (%s,%s,'blocked',null,null,null,null,null,1,%s,
                jsonb_build_object('execution_generation',3))
    """, (run,task,reason))
    db.execute("""
        insert into public.factory_change_sets
          (id,project_id,root_task_id,status,current_wave,
           source_commit,candidate_commit,integration_branch,release_run_id,
           lease_owner,lease_expires_at,attempt_count,metadata)
        values (%s,%s,%s,'blocked',1,null,null,null,null,null,null,0,%s::jsonb)
    """, (cs,project,root_task,json.dumps({"blocker":blocker})))
    db.execute("""
        insert into public.factory_change_set_work_units
          (id,change_set_id,task_id,run_id,status,wave,base_commit,
           branch_name,output_commit,changed_files)
        values (%s,%s,%s,%s,'blocked',1,null,null,null,'[]'::jsonb)
    """, (unit,cs,task,run))

    def call(*, project_key="factory-fixture", generation=3, run_id=run):
        return db.execute("""
            select public.factory_retry_blocked_platform_kind(%s,%s,%s,%s,%s)
        """, (cs,run_id,project_key,generation,"Operator authorized safe retry of original work unit")).fetchone()[0]

    def reject(**kwargs):
        try:
            with db.transaction():
                call(**kwargs)
        except psycopg.Error:
            pass
        else:
            raise AssertionError("unsafe platform kind recovery unexpectedly succeeded")
        row = db.execute("""
            select status,source_commit,candidate_commit
            from public.factory_change_sets where id=%s
        """,(cs,)).fetchone()
        assert row == ("blocked",None,None), row
        assert db.execute(
            "select count(*) from public.factory_audit_events"
        ).fetchone()[0] == 0

    reject(run_id=uuid.uuid4())
    reject(generation=2)
    reject(project_key="other")

    db.execute("update public.factory_project_execution_controls set state='paused'")
    reject()
    db.execute("update public.factory_project_execution_controls set state='running'")
    db.execute("update public.factory_projects set project_kind='existing'")
    reject()
    db.execute("update public.factory_projects set project_kind='platform'")

    db.execute("update public.factory_change_set_work_units set output_commit=%s",( "c"*40,))
    reject()
    db.execute("update public.factory_change_set_work_units set output_commit=null")

    db.execute("update public.factory_change_sets set lease_owner='foreign'")
    reject()
    db.execute("update public.factory_change_sets set lease_owner=null")

    db.execute("""
        update public.factory_change_sets set metadata=%s::jsonb
    """,(json.dumps({"blocker":{**blocker, "reason":"some other failure"}}),))
    reject()
    db.execute("update public.factory_change_sets set metadata=%s::jsonb",
               (json.dumps({"blocker":blocker}),))

    restored = call()
    assert restored["status"] == "building", restored
    assert restored["change_set_id"] == str(cs), restored
    assert restored["run_id"] == str(run), restored
    assert restored["work_unit_id"] == str(unit), restored
    assert restored["generation"] == 3, restored
    assert db.execute("""
        select s.status,u.status,r.status,t.status
        from public.factory_change_sets s
        join public.factory_change_set_work_units u on u.change_set_id=s.id
        join public.factory_runs r on r.id=u.run_id
        join public.factory_tasks t on t.id=u.task_id
        where s.id=%s
    """,(cs,)).fetchone() == ("building","queued","queued","queued_execution")
    assert db.execute("""
        select status from public.factory_tasks where id=%s
    """, (root_task,)).fetchone()[0] == "completed"
    event = db.execute("""
        select event_type,payload from public.factory_audit_events
    """).fetchone()
    assert event[0] == "change_set.platform_kind_requeued"
    assert event[1]["change_set_id"] == str(cs)
    # Idempotent in the fail-closed direction: never queue this run twice.
    try:
        with db.transaction():
            call()
    except psycopg.Error:
        pass
    else:
        raise AssertionError("repeated recovery must be rejected")
    assert db.execute(
        "select count(*) from public.factory_audit_events"
    ).fetchone()[0] == 1

print("PLATFORM_KIND_RECOVERY_POSTGRES_PASS=1")
