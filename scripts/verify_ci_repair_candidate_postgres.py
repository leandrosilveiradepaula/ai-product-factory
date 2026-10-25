#!/usr/bin/env python3
"""Prove CI-repair candidate recovery only against disposable PostgreSQL 16."""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict


dsn=os.getenv("FACTORY_CI_CANDIDATE_TEST_DSN","")
cfg=conninfo_to_dict(dsn)
if (os.getenv("FACTORY_CI_CANDIDATE_TEST_ISOLATED")!="true"
    or cfg.get("host") not in ("localhost","127.0.0.1")
    or cfg.get("dbname")!="factory_ci_candidate_test"
    or cfg.get("user")!="factory_ci"):
    raise SystemExit("REFUSING_NON_ISOLATED_CI_CANDIDATE_TEST_DATABASE")

migration=(Path(__file__).resolve().parents[1] / "supabase/migrations/"
           "20261025013500_resume_blocked_ci_repair_candidate.sql").read_text()
schema="""
create role anon nologin;
create role authenticated nologin;
create role service_role nologin;
create table factory_projects(
 id uuid primary key,project_key text,repository text,
 project_kind text,is_active boolean,manifest jsonb
);
create table factory_project_execution_controls(
 project_id uuid primary key,state text,generation bigint
);
create table factory_tasks(
 id uuid primary key,project_id uuid,parent_task_id uuid,status text,
 scope_keys jsonb,updated_at timestamptz
);
create table factory_runs(
 id uuid primary key,task_id uuid,status text,execution_route text,
 candidate_commit text,branch_name text,metadata jsonb,
 attempt_count integer,lease_owner text,lease_expires_at timestamptz,
 last_error text
);
create table factory_change_sets(
 id uuid primary key,project_id uuid,root_task_id uuid,status text,
 source_commit text,candidate_commit text,integration_branch text,
 current_wave integer,release_run_id uuid,lease_owner text,lease_expires_at timestamptz,
 metadata jsonb,created_at timestamptz default now(),updated_at timestamptz
);
create table factory_change_set_work_units(
 id uuid primary key,change_set_id uuid,task_id uuid,run_id uuid,
 status text,base_commit text,output_commit text,changed_files jsonb,
 wave integer,plan_task_key text,updated_at timestamptz
);
create table factory_ci_repair_requests(
 id uuid primary key,project_id uuid,change_set_id uuid,source_run_id uuid,
 work_unit_id uuid,repository text,pr_number integer,branch text,
 original_candidate_commit text,execution_generation bigint,
 attempt integer,max_attempts integer,failure_class text,
 failures jsonb,write_scopes jsonb,status text,blocker_reason text,
 lease_owner text,lease_expires_at timestamptz,
 updated_at timestamptz,created_at timestamptz default now()
);
create table factory_audit_events(
 id bigint generated always as identity primary key,
 project_id uuid,task_id uuid,run_id uuid,actor_type text,actor_ref text,
 event_type text,payload jsonb
);
"""
project,root,task,source_run,repair_run,cs,unit_original,unit_repair,request=(uuid4() for _ in range(9))
sha="a"*40
candidate="b"*40
integration_branch="factory/change-set-673a2fc7"
scopes=["src/app/(dashboard)/service-desk/page.tsx",
        "src/components/layout/Sidebar.tsx",
        "src/lib/service-desk/entry-guard.test.ts",
        "src/lib/service-desk/entry-guard.ts"]
reason="PermissionError: repin evidence does not match exact pinned source"
blocker={"type":"implementation_preflight_error","reason":reason,
         "run_id":str(repair_run),"work_unit_id":str(unit_repair)}
meta={"change_set_id":str(cs),"execution_generation":12,
      "blocker_type":"implementation_preflight_error"}
source_meta={"change_set_id":str(cs),"ci_repair_request_id":str(request)}
manifest={"delivery_target":{
    "sha":sha,"repository":"owner/crm",
    "branch":"preview/hardening-release-candidate",
    "mode":"open_pr_candidate"}}
change_meta={"blocker":blocker,
 "integration_release_request":{"pr_number":197,"candidate_commit":candidate}}
failures=[{"name":"native-ci/typescript","failure_class":"code","conclusion":"failure"}]

with psycopg.connect(dsn,autocommit=True) as db:
    db.execute(schema)
    db.execute(migration)
    acl=db.execute("""
      select prosecdef,
        has_function_privilege('service_role',oid,'execute'),
        has_function_privilege('anon',oid,'execute'),
        has_function_privilege('authenticated',oid,'execute')
      from pg_proc where proname='factory_resume_blocked_ci_repair_candidate_v1'
    """).fetchone()
    assert acl==(False,True,False,False),acl
    db.execute("insert into factory_projects values (%s,'crm','owner/crm',"
               "'existing',true,%s::jsonb)",(project,json.dumps(manifest)))
    db.execute("insert into factory_project_execution_controls values (%s,'running',12)",
               (project,))
    db.execute("insert into factory_tasks values (%s,%s,null,'completed','[]'::jsonb,null)",
               (root,project))
    db.execute("insert into factory_tasks values (%s,%s,%s,'blocked',%s::jsonb,null)",
               (task,project,root,json.dumps(scopes)))
    db.execute("insert into factory_runs values (%s,%s,'repair_pending',"
               "'direct',%s,%s,%s::jsonb,1,null,null,null)",
               (source_run,root,candidate,integration_branch,json.dumps(source_meta)))
    db.execute("insert into factory_runs values (%s,%s,'blocked',"
               "'direct',null,null,%s::jsonb,1,null,null,%s)",
               (repair_run,task,json.dumps(meta),reason))
    db.execute("insert into factory_change_sets values (%s,%s,%s,'blocked',"
               "%s,%s,%s,2,null,null,null,%s::jsonb,now(),null)",
               (cs,project,root,sha,candidate,integration_branch,json.dumps(change_meta)))
    db.execute("insert into factory_change_set_work_units values (%s,%s,%s,%s,"
               "'integrated',%s,%s,%s::jsonb,1,'service-desk-entry',null)",
               (unit_original,cs,root,source_run,sha,candidate,json.dumps(scopes)))
    db.execute("insert into factory_change_set_work_units values (%s,%s,%s,%s,"
               "'blocked',%s,null,'[]'::jsonb,2,'ci-repair-1',null)",
               (unit_repair,cs,task,repair_run,candidate))
    db.execute("insert into factory_ci_repair_requests values "
               "(%s,%s,%s,%s,%s,'owner/crm',197,%s,%s,12,1,3,'code',"
               "%s::jsonb,%s::jsonb,'failed_gate',%s,null,null,null,now())",
               (request,project,cs,source_run,unit_repair,integration_branch,candidate,
                json.dumps(failures),json.dumps(scopes),
                '{"type":"implementation_preflight_error","reason":"'+reason+'"}'))

    def invoke():
        result=db.execute(
            "select public.factory_resume_blocked_ci_repair_candidate_v1(%s)",(2,)
        ).fetchone()[0]
        assert result["product_stage_replayed"] is False,result
        assert result["release_authorized"] is False,result
        assert result["paid_model_calls"]==0,result
        return result

    def idle():
        outcome=invoke()
        assert outcome["status"]=="idle" and outcome["requeued"]==0,outcome
        assert db.execute("select status from factory_runs where id=%s",
                          (repair_run,)).fetchone()[0]=="blocked"
    db.execute("update factory_project_execution_controls set generation=13 where project_id=%s",(project,))
    idle()
    db.execute("update factory_project_execution_controls set generation=12 where project_id=%s",(project,))

    db.execute("update factory_projects set manifest=jsonb_set(manifest,"
               "'{delivery_target,sha}',to_jsonb(%s::text)) where id=%s",
               ("f"*40,project))
    idle()
    db.execute("update factory_projects set manifest=%s::jsonb where id=%s",
               (json.dumps(manifest),project))

    db.execute("update factory_runs set lease_owner='active' where id=%s",(repair_run,))
    idle()
    db.execute("update factory_runs set lease_owner=null where id=%s",(repair_run,))

    db.execute("update factory_ci_repair_requests set attempt=2 where id=%s",(request,))
    idle()
    db.execute("update factory_ci_repair_requests set attempt=1 where id=%s",(request,))

    db.execute("update factory_ci_repair_requests set failure_class='runner' where id=%s",(request,))
    idle()
    db.execute("update factory_ci_repair_requests set failure_class='code' where id=%s",(request,))

    db.execute("update factory_change_set_work_units set output_commit=%s where id=%s",
               (candidate,unit_repair))
    idle()
    db.execute("update factory_change_set_work_units set output_commit=null where id=%s",
               (unit_repair,))

    db.execute("update factory_ci_repair_requests set original_candidate_commit=%s where id=%s",
               ("f"*40,request))
    idle()
    db.execute("update factory_ci_repair_requests set original_candidate_commit=%s where id=%s",
               (candidate,request))

    db.execute("update factory_change_sets set lease_owner='worker' where id=%s",(cs,))
    idle()
    db.execute("update factory_change_sets set lease_owner=null where id=%s",(cs,))

    with psycopg.connect(dsn,autocommit=False) as held:
        held.execute("select id from factory_ci_repair_requests where id=%s for update",(request,))
        idle()
        held.rollback()

    result=invoke()
    assert result["status"]=="requeued" and result["requeued"]==1,result
    for table,key,want in (
        ("factory_ci_repair_requests",request,"queued"),
        ("factory_runs",repair_run,"queued"),
        ("factory_tasks",task,"queued_execution"),
        ("factory_change_set_work_units",unit_repair,"queued"),
        ("factory_change_sets",cs,"building"),
    ):
        got=db.execute("select status from "+table+" where id=%s",(key,)).fetchone()[0]
        assert got==want,(table,got,want)
    assert db.execute("select status from factory_runs where id=%s",
                      (source_run,)).fetchone()[0]=="repair_pending"
    assert db.execute("select attempt from factory_ci_repair_requests where id=%s",
                      (request,)).fetchone()[0]==1
    audits=db.execute("select payload from factory_audit_events where "
                      "event_type='change_set.ci_repair_candidate_requeued'").fetchall()
    assert len(audits)==1,audits
    assert audits[0][0]["candidate_commit"]==candidate,audits
    assert invoke()["requeued"]==0
    try:
        with db.transaction():
            db.execute("select public.factory_resume_blocked_ci_repair_candidate_v1(3)")
    except psycopg.Error:
        pass
    else:
        raise AssertionError("unbounded recovery unexpectedly accepted")

    print(json.dumps({"status":"pass","requeued":1,"replay_requeued":0,
       "negative_cases":9,"audit_events":1,"acl_enforced":True,
       "original_attempt_preserved":True,
       "product_stage_replayed":False,"production_modified":False,
       "paid_model_calls":0}))
