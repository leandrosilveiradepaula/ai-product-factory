#!/usr/bin/env python3
"""Positive and negative tests for a typed Platform Change Set repin (disposable PG)."""
import json
import os
import uuid
import psycopg
from psycopg.conninfo import conninfo_to_dict
from pathlib import Path

DSN=os.getenv("FACTORY_PLATFORM_REPIN_PG_DSN","")
conn=conninfo_to_dict(DSN)
if (os.getenv("FACTORY_PLATFORM_REPIN_PG_ISOLATED")!="true"
    or conn.get("dbname")!="factory_platform_repin_test"
    or conn.get("host") not in ("127.0.0.1","localhost")
    or conn.get("user")!="factory_ci"):
    raise SystemExit("refusing non-isolated Platform repin database")

migration=(Path(__file__).resolve().parents[1]/
 "supabase/migrations/20261118022000_platform_blocked_change_set_source_repin.sql"
).read_text()
schema="""
create role service_role nologin;
create role anon nologin;
create role authenticated nologin;
create table public.factory_projects(id uuid primary key,project_kind text,
 is_active bool,repository text,manifest jsonb);
create table public.factory_project_execution_controls(project_id uuid,state text,generation bigint);
create table public.factory_tasks(id uuid primary key,project_id uuid,parent_task_id uuid,
 status text,scope_keys jsonb,updated_at timestamptz default now());
create table public.factory_runs(id uuid primary key,task_id uuid,status text,
 attempt_count integer,lease_owner text,lease_expires_at timestamptz,
 metadata jsonb,source_commit text,candidate_commit text,last_error text);
create table public.factory_change_sets(id uuid primary key,project_id uuid,status text,
 source_commit text,candidate_commit text,lease_owner text,lease_expires_at timestamptz,
 release_run_id uuid,metadata jsonb,updated_at timestamptz default now());
create table public.factory_change_set_work_units(id uuid primary key,change_set_id uuid,
 task_id uuid,run_id uuid,status text,base_commit text,output_commit text,branch_name text,
 updated_at timestamptz default now());
create table public.factory_audit_events(id bigint generated always as identity primary key,
 project_id uuid,task_id uuid,run_id uuid,actor_type text,actor_ref text,
 event_type text,payload jsonb);
"""
OLD="a"*40
NEW="b"*40
REASON="PermissionError: frozen Change Set source differs from verified candidate"
DOC="docs/UX_UI_1506_AUDIT.md"
def fixture(db, *,kind="platform",control="running",generation=1,
            error=REASON,parent_status="completed",scope=DOC,
            attempts=2,unit_status="blocked",branch_name="factory/cs-test/AUDIT"):
    db.execute("truncate public.factory_audit_events,public.factory_change_set_work_units,"
               "public.factory_change_sets,public.factory_runs,public.factory_tasks,"
               "public.factory_project_execution_controls,public.factory_projects restart identity")
    p,root,task,plan,run,cs,wu=[uuid.uuid4() for _ in range(7)]
    db.execute("insert into public.factory_projects values (%s,%s,true,%s,%s::jsonb)",
               (p,kind,"acme/factory",json.dumps({"continuation_request":{"source":"factory-console"}})))
    db.execute("insert into public.factory_project_execution_controls values (%s,%s,%s)",
               (p,control,generation))
    db.execute("insert into public.factory_tasks(id,project_id,status,scope_keys) "
               "values(%s,%s,'completed','[]'::jsonb)",(root,p))
    db.execute("insert into public.factory_tasks(id,project_id,parent_task_id,status,scope_keys) "
               "values(%s,%s,%s,'blocked',%s::jsonb)",
               (task,p,root,json.dumps([scope,"apps/console/app/nav.tsx"])))
    db.execute("insert into public.factory_runs(id,task_id,status,attempt_count,metadata) "
               "values(%s,%s,%s,0,%s::jsonb)",
               (plan,root,parent_status,json.dumps({"source":"factory-console",
                 "stage_evidence":{"planning":{"status":"completed"}}})))
    db.execute("insert into public.factory_runs(id,task_id,status,attempt_count,"
               "metadata,last_error) values(%s,%s,'blocked',%s,%s::jsonb,%s)",
               (run,task,attempts,json.dumps({"execution_generation":"1"}),error))
    blocker={"type":"implementation_preflight_error",
             "reason":error,"run_id":str(run),"work_unit_id":str(wu)}
    db.execute("insert into public.factory_change_sets(id,project_id,status,"
               "source_commit,candidate_commit,metadata) "
               "values(%s,%s,'blocked',%s,%s,%s::jsonb)",
               (cs,p,OLD,OLD,json.dumps({"blocker":blocker})))
    db.execute("insert into public.factory_change_set_work_units "
               "(id,change_set_id,task_id,run_id,status,base_commit,branch_name) "
               "values(%s,%s,%s,%s,%s,%s,%s)",
               (wu,cs,task,run,unit_status,OLD,branch_name))
    evidence={"old_sha":OLD,"new_sha":NEW,"compare_status":"ahead",
              "ahead_by":3,"behind_by":0,"file_count":2,
              "branch":"main","repository":"acme/factory",
              "work_branch":branch_name,"work_branch_sha":NEW,
              "changed_paths":["src/ai_product_factory/change_set_worker.py",
                               "supabase/migrations/20261118_fix.sql"]}
    return {"project":p,"task":task,"run":run,"cs":cs,"wu":wu,"evidence":evidence}
def rpc(db,fixture,proof=None,old=OLD,new=NEW):
    return db.execute(
       "select public.factory_repin_blocked_platform_source_v1(%s,%s,%s,%s::jsonb,%s)",
       (fixture["cs"],old,new,json.dumps(proof or fixture["evidence"]),
        "Rebase only verified ancestor, preserve independent merge gate")
    ).fetchone()[0]
def denied(db,f,proof=None,old=OLD,new=NEW):
    try:
        with db.transaction():
            rpc(db,f,proof,old=old,new=new)
    except psycopg.Error as ex:
        assert ex.sqlstate=="PT409",ex.sqlstate
        return
    raise AssertionError("dangerous Platform repin accepted")

with psycopg.connect(DSN,autocommit=True) as db:
    db.execute(schema)
    db.execute(migration)
    privileges=db.execute("""
      select p.prosecdef,
      has_function_privilege('service_role',p.oid,'EXECUTE'),
      has_function_privilege('anon',p.oid,'EXECUTE'),
      has_function_privilege('authenticated',p.oid,'EXECUTE')
      from pg_proc p where p.proname='factory_repin_blocked_platform_source_v1'
    """).fetchone()
    assert privileges==(False,True,False,False),privileges
    f=fixture(db)
    receipt=rpc(db,f)
    assert receipt["status"]=="requeued" and receipt["source_commit"]==NEW,receipt
    assert db.execute("select status,source_commit,candidate_commit from public.factory_change_sets where id=%s",(f["cs"],)).fetchone()==("building",NEW,NEW)
    assert db.execute("select status,base_commit from public.factory_change_set_work_units where id=%s",(f["wu"],)).fetchone()==("queued",NEW)
    assert db.execute("select status,source_commit,last_error from public.factory_runs where id=%s",(f["run"],)).fetchone()==("queued",NEW,None)
    assert db.execute("select status from public.factory_tasks where id=%s",(f["task"],)).fetchone()[0]=="queued_execution"
    assert db.execute("select count(*) from public.factory_audit_events").fetchone()[0]==1
    denied(db,f) # idempotence; no duplicate changes

    negative=[
      ("kind",{"kind":"existing"},None),
      ("paused",{"control":"paused"},None),
      ("epoch",{"generation":2},None),
      ("wrong_reason",{"error":"other"},None),
      ("planned_failed",{"parent_status":"failed"},None),
      ("too_many_attempts",{"attempts":3},None),
      ("unit_moved",{"unit_status":"completed"},None),
      ("bad_scope",{},{"changed_paths":["apps/console/app/nav.tsx"]}),
      ("governance",{},{"changed_paths":["AGENTS.md"]}),
      ("protected_console",{},{"changed_paths":["apps/console/app/new.tsx"]}),
      ("wrong_repo",{},{"repository":"intruder/factory"}),
      ("not_ancestor",{},{"compare_status":"diverged"}),
      ("wrong_branch",{},{"branch":"preview"}),
      ("unverified_branch",{},{"work_branch_sha":OLD}),
    ]
    for label,kwargs,ev_patch in negative:
        f=fixture(db,**kwargs)
        evidence=dict(f["evidence"])
        if ev_patch:
            evidence.update(ev_patch)
            if "changed_paths" in ev_patch:
                evidence["file_count"]=len(evidence["changed_paths"])
        denied(db,f,evidence)
        assert db.execute("select count(*) from public.factory_audit_events").fetchone()[0]==0,label
        assert db.execute("select status from public.factory_change_sets where id=%s",(f["cs"],)).fetchone()[0]=="blocked",label
print(json.dumps({"status":"PASS","cases":16,"production_writes":0,"paid_calls":0}))
