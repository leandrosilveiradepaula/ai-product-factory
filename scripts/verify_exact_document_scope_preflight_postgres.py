#!/usr/bin/env python3
"""Disposable PostgreSQL regression for narrowly typed audit document recovery."""
from __future__ import annotations
import json
import os
import uuid
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict

DSN = os.environ.get("FACTORY_DOCUMENT_SCOPE_PG_TEST_DSN", "")
cfg = conninfo_to_dict(DSN)
if (os.environ.get("FACTORY_DOCUMENT_SCOPE_PG_TEST_ISOLATED") != "true"
    or cfg.get("host") not in ("127.0.0.1", "localhost")
    or cfg.get("dbname") != "factory_document_scope_test"
    or cfg.get("user") != "factory_ci"):
    raise SystemExit("refusing non-isolated document scope PostgreSQL")

sql = (Path(__file__).resolve().parents[1] /
       "supabase/migrations/20261118014500_retry_verified_document_scope_preflight.sql").read_text()
schema = """
create role service_role nologin;
create role anon nologin;
create role authenticated nologin;
create table public.factory_projects(id uuid primary key, project_kind text, is_active boolean);
create table public.factory_project_execution_controls(project_id uuid, state text, generation bigint);
create table public.factory_tasks(
 id uuid primary key,project_id uuid,parent_task_id uuid,status text,agent_role text,
 scope_keys jsonb,updated_at timestamptz default now());
create table public.factory_runs(
 id uuid primary key,task_id uuid,status text,attempt_count integer,
 lease_owner text,lease_expires_at timestamptz,last_error text,metadata jsonb,
 candidate_commit text);
create table public.factory_change_sets(
 id uuid primary key,project_id uuid,status text,metadata jsonb,lease_owner text,
 lease_expires_at timestamptz,updated_at timestamptz default now(),source_commit text);
create table public.factory_change_set_work_units(
 id uuid primary key,change_set_id uuid,task_id uuid,run_id uuid,
 status text,output_commit text,updated_at timestamptz default now());
create table public.factory_audit_events(
 id bigint generated always as identity primary key,project_id uuid,
 task_id uuid,run_id uuid,actor_type text,actor_ref text,event_type text,payload jsonb);
"""
DOC = "docs/UX_UI_1506_AUDIT.md"
REASON = "PermissionError: exact new-file scope lacks a verified populated parent: " + DOC
def fixture(db, *, kind="platform", state="running", role="ui", scope=DOC,
            generation=1, reason=REASON, parent_source="factory-console", parent_status="completed"):
    db.execute("truncate public.factory_audit_events,public.factory_change_set_work_units,"
               "public.factory_change_sets,public.factory_runs,public.factory_tasks,"
               "public.factory_project_execution_controls,public.factory_projects restart identity")
    project,root,task,run,planned,cs,unit = [uuid.uuid4() for _ in range(7)]
    db.execute("insert into factory_projects values (%s,%s,true)",(project,kind))
    db.execute("insert into factory_project_execution_controls values (%s,%s,%s)",(project,state,generation))
    db.execute("insert into factory_tasks (id,project_id,parent_task_id,status,agent_role,scope_keys) "
               "values(%s,%s,null,'completed',null,'[]'::jsonb)",(root,project))
    db.execute("insert into factory_tasks (id,project_id,parent_task_id,status,agent_role,scope_keys) "
               "values(%s,%s,%s,'blocked',%s,%s::jsonb)",
               (task,project,root,role,json.dumps([scope])))
    plan_md={"source":parent_source,"stage_evidence":{"planning":{"status":"completed"}}}
    db.execute("insert into factory_runs(id,task_id,status,attempt_count,metadata) "
               "values(%s,%s,%s,0,%s::jsonb)",(planned,root,parent_status,json.dumps(plan_md)))
    failed_md={"execution_generation":"1","source":"change-set","change_set_id":str(cs)}
    db.execute("insert into factory_runs(id,task_id,status,attempt_count,last_error,metadata) "
               "values(%s,%s,'blocked',0,%s,%s::jsonb)",
               (run,task,reason,json.dumps(failed_md)))
    blocker={"type":"implementation_preflight_error","run_id":str(run),
             "work_unit_id":str(unit),"reason":reason}
    db.execute("insert into factory_change_sets(id,project_id,status,metadata,source_commit) "
               "values(%s,%s,'blocked',%s::jsonb,%s)",
               (cs,project,json.dumps({"blocker":blocker}),"a"*40))
    db.execute("insert into factory_change_set_work_units "
               "(id,change_set_id,task_id,run_id,status) "
               "values(%s,%s,%s,%s,'blocked')",(unit,cs,task,run))
    return cs,run,task,unit
def rpc(db,cs):
    return db.execute("select public.factory_retry_blocked_change_set_preflight(%s,%s)",
                      (cs,"exact document scope supported by current worker")).fetchone()[0]
def deny(db,cs,label):
    try:
        with db.transaction():
            rpc(db,cs)
    except psycopg.Error:
        return
    raise AssertionError("unexpected recovery on " + label)

with psycopg.connect(DSN,autocommit=True) as db:
    db.execute(schema)
    db.execute(sql)
    acl=db.execute("""
      select p.prosecdef,
        has_function_privilege('service_role',p.oid,'EXECUTE'),
        has_function_privilege('anon',p.oid,'EXECUTE'),
        has_function_privilege('authenticated',p.oid,'EXECUTE')
      from pg_proc p where p.proname='factory_retry_blocked_change_set_preflight'
    """).fetchone()
    assert acl==(False,True,False,False),acl
    cs,run,task,unit=fixture(db)
    result=rpc(db,cs)
    assert result["status"]=="building" and result["run_id"]==str(run),result
    assert db.execute("select status from factory_runs where id=%s",(run,)).fetchone()[0]=="queued"
    assert db.execute("select status from factory_tasks where id=%s",(task,)).fetchone()[0]=="queued_execution"
    assert db.execute("select status from factory_change_set_work_units where id=%s",(unit,)).fetchone()[0]=="queued"
    assert db.execute("select count(*) from factory_audit_events").fetchone()[0]==1
    deny(db,cs,"idempotent second call")

    for label,kwargs in (
        ("not_platform",{"kind":"existing"}),("paused",{"state":"paused"}),
        ("wrong_epoch",{"generation":2}),("wrong_builder",{"role":"qa"}),
        ("unknown_scope",{"scope":"docs/DIFFERENT.md"}),
        ("unsafe_reason",{"reason":"PermissionError: exact new-file scope lacks a verified populated parent: docs/../unsafe.md"}),
        ("wrong_parent_source",{"parent_source":"github-owner"}),
        ("failed_plan",{"parent_status":"failed"}),
    ):
        cs,_,_,_=fixture(db,**kwargs)
        deny(db,cs,label)
        assert db.execute("select count(*) from factory_audit_events").fetchone()[0]==0,label

    # Existing oversized-context recovery has its original eligibility path.
    cs,_,_,_=fixture(db,kind="existing",role="development",
                    scope="src/app/page.tsx",reason="repository context file too large")
    result=rpc(db,cs)
    assert result["status"]=="building",result
print(json.dumps({"status":"PASS","cases":11,"paid_calls":0,
                  "production_writes":0,"environment":"isolated_postgres"}))
