#!/usr/bin/env python3
"""Verify literal-scope recovery on disposable PostgreSQL, never live Supabase."""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict

dsn = os.getenv("FACTORY_LITERAL_SCOPE_TEST_DSN", "")
cfg = conninfo_to_dict(dsn)
if (os.getenv("FACTORY_LITERAL_SCOPE_TEST_ISOLATED") != "true"
    or cfg.get("host") not in ("localhost", "127.0.0.1")
    or cfg.get("dbname") != "factory_literal_scope_test"
    or cfg.get("user") != "factory_ci"):
    raise SystemExit("REFUSING_NON_ISOLATED_SCOPE_RECOVERY_DATABASE")

migration = (Path(__file__).resolve().parents[1] / "supabase/migrations/"
    "20261024235800_resume_blocked_literal_scope_misresolution.sql").read_text()

schema = """
create role anon nologin;
create role authenticated nologin;
create role service_role nologin;
create table factory_projects (
 id uuid primary key, project_key text not null, repository text not null,
 project_kind text not null, is_active boolean not null, manifest jsonb not null
);
create table factory_project_execution_controls (
 project_id uuid primary key references factory_projects(id),
 state text not null, generation bigint not null
);
create table factory_tasks (
 id uuid primary key, project_id uuid not null references factory_projects(id),
 status text not null, scope_keys jsonb not null,updated_at timestamptz
);
create table factory_runs (
 id uuid primary key,task_id uuid not null references factory_tasks(id),
 status text not null,candidate_commit text,metadata jsonb not null,
 lease_owner text,lease_expires_at timestamptz,attempt_count integer not null,
 last_error text
);
create table factory_change_sets (
 id uuid primary key,project_id uuid not null references factory_projects(id),
 status text not null,source_commit text,candidate_commit text,
 release_run_id uuid,lease_owner text,lease_expires_at timestamptz,
 metadata jsonb not null,current_wave integer not null,
 created_at timestamptz not null default now(),updated_at timestamptz
);
create table factory_change_set_work_units (
 id uuid primary key,change_set_id uuid references factory_change_sets(id),
 run_id uuid references factory_runs(id),task_id uuid references factory_tasks(id),
 status text not null,base_commit text,branch_name text,output_commit text,
 changed_files jsonb,wave integer not null,updated_at timestamptz
);
create table factory_work_unit_context_packets (
 id uuid primary key,project_id uuid references factory_projects(id),
 run_id uuid references factory_runs(id),
 work_unit_id uuid references factory_change_set_work_units(id),
 change_set_id uuid references factory_change_sets(id),
 version integer not null,packet_hash text,packet jsonb not null
);
create table factory_audit_events (
 id bigint generated always as identity primary key,
 project_id uuid,task_id uuid,run_id uuid,actor_type text,actor_ref text,
 event_type text,payload jsonb
);
"""
project,task,run,cs,unit,ctx = (uuid4() for _ in range(6))
sha = "a" * 40
branch = "preview/hardening-release-candidate"
unit_branch = "factory/cs-real/service-desk"
repository = "owner/crm"
bad = ("Blocked: the enforced repository.write_scopes permits only src/components/layout/Sidebar.tsx "
       "and unrelated existing files; it does not permit required files "
       "src/app/(dashboard)/service-desk/page.tsx and src/lib/service-desk/entry-guard.ts")
scopes = ["src/components/layout/Sidebar.tsx", "src/app/(dashboard)/service-desk/page.tsx",
          "src/lib/service-desk/entry-guard.ts", "src/lib/service-desk/entry-guard.test.ts"]
packet_hash = "b" * 64
packet = {"version": 1, "sha256": packet_hash,
          "repository": {
              "project_key": "crm", "repository": repository, "exact_base_commit": sha,
              "work_branch": unit_branch,
              "write_scopes": ["src/components/layout/Sidebar.tsx",
                               "src/lib/unrelated-existing-file.ts"]}}
meta = {"change_set_id": str(cs), "execution_generation": 3,
        "blocker_reason": bad, "blocker_type": "repository_governance",
        "implementation_blocked": True}
blocker = {"type": "repository_governance", "reason": bad,
           "run_id": str(run), "work_unit_id": str(unit)}

with psycopg.connect(dsn, autocommit=True) as db:
    db.execute(schema)
    db.execute(migration)
    privileges = db.execute("""
    select prosecdef,
      has_function_privilege('service_role',oid,'execute'),
      has_function_privilege('anon',oid,'execute'),
      has_function_privilege('authenticated',oid,'execute')
    from pg_proc where proname='factory_resume_blocked_literal_scope_misresolution_v1'
    """).fetchone()
    assert privileges == (False, True, False, False), privileges

    manifest = {"delivery_target": {
        "sha": sha, "branch": branch, "repository": repository}}
    db.execute(
        "insert into factory_projects values (%s,'crm',%s,'existing',true,%s::jsonb)",
        (project,repository,json.dumps(manifest)),
    )
    db.execute("insert into factory_project_execution_controls values (%s,'running',3)",(project,))
    db.execute("insert into factory_tasks values (%s,%s,'blocked',%s::jsonb,null)",
               (task,project,json.dumps(scopes)))
    db.execute("insert into factory_runs values (%s,%s,'blocked',null,%s::jsonb,"
               "null,null,1,%s)",(run,task,json.dumps(meta),bad))
    db.execute("insert into factory_change_sets values (%s,%s,'blocked',%s,%s,"
               "null,null,null,%s::jsonb,1,now(),null)",
               (cs,project,sha,sha,json.dumps({"blocker":blocker})))
    db.execute("insert into factory_change_set_work_units values (%s,%s,%s,%s,"
               "'blocked',%s,%s,null,'[]'::jsonb,1,null)",
               (unit,cs,run,task,sha,unit_branch))
    db.execute("insert into factory_work_unit_context_packets values (%s,%s,%s,"
               "%s,%s,1,%s,%s::jsonb)",(ctx,project,run,unit,cs,packet_hash,json.dumps(packet)))

    def call():
        return db.execute(
            "select public.factory_resume_blocked_literal_scope_misresolution_v1(%s)",
            (2,),
        ).fetchone()[0]

    def assert_blocked():
        assert call()["requeued"] == 0
        assert db.execute("select status from factory_runs where id=%s",(run,)).fetchone()[0]=="blocked"
    db.execute("update factory_project_execution_controls set generation=4 where project_id=%s",(project,))
    assert_blocked()
    db.execute("update factory_project_execution_controls set generation=3 where project_id=%s",(project,))
    db.execute("update factory_runs set lease_owner='active' where id=%s",(run,))
    assert_blocked()
    db.execute("update factory_runs set lease_owner=null where id=%s",(run,))
    db.execute("update factory_change_sets set candidate_commit=%s where id=%s",("f"*40,cs))
    assert_blocked()
    db.execute("update factory_change_sets set candidate_commit=%s where id=%s",(sha,cs))
    db.execute("update factory_change_set_work_units set output_commit=%s where id=%s",(sha,unit))
    assert_blocked()
    db.execute("update factory_change_set_work_units set output_commit=null where id=%s",(unit,))
    db.execute("update factory_work_unit_context_packets set packet=jsonb_set(packet,"
               "'{repository,write_scopes}',%s::jsonb) where id=%s",
               (json.dumps(scopes),ctx))
    assert_blocked()
    db.execute("update factory_work_unit_context_packets set packet=%s::jsonb where id=%s",
               (json.dumps(packet),ctx))

    with psycopg.connect(dsn,autocommit=False) as held:
        held.execute("select id from factory_change_sets where id=%s for update",(cs,))
        assert_blocked()
        held.rollback()

    actual = call()
    assert actual["status"]=="requeued" and actual["requeued"]==1, actual
    assert actual["product_stage_replayed"] is False
    assert actual["release_authorized"] is False
    for table,ident,wanted in (
        ("factory_runs",run,"queued"),("factory_tasks",task,"queued_execution"),
        ("factory_change_set_work_units",unit,"queued"),
        ("factory_change_sets",cs,"building"),
    ):
        status=db.execute(f"select status from {table} where id=%s",(ident,)).fetchone()[0]
        assert status==wanted,(table,status)
    audits=db.execute(
        "select payload from factory_audit_events"
        " where event_type='change_set.literal_scope_requeued'"
    ).fetchall()
    assert len(audits)==1 and audits[0][0]["source_sha"]==sha, audits
    assert call()["requeued"]==0
    try:
        with db.transaction():
            db.execute("select public.factory_resume_blocked_literal_scope_misresolution_v1(4)")
    except psycopg.Error:
        pass
    else:
        raise AssertionError("unbounded recovery accepted")
    print(json.dumps({"status": "pass", "requeued": 1, "replay": 0,
        "guard_cases": 5, "audit_events": 1, "acl_enforced": True,
        "product_stage_replayed": False, "production_modified": False,
        "paid_model_calls": 0}))
