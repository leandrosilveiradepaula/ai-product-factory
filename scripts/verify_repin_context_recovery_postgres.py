#!/usr/bin/env python3
"""Exercise exact-epoch repin recovery only on disposable PostgreSQL 16."""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict


dsn=os.getenv("FACTORY_REPIN_RECOVERY_DSN","")
info=conninfo_to_dict(dsn)
if (os.getenv("FACTORY_REPIN_RECOVERY_ISOLATED")!="true"
    or info.get("host") not in ("localhost","127.0.0.1")
    or info.get("dbname")!="factory_repin_recovery_test"
    or info.get("user")!="factory_ci"):
    raise SystemExit("REFUSING_NON_ISOLATED_REPIN_RECOVERY_DATABASE")

migration=(Path(__file__).resolve().parents[1] / "supabase/migrations/"
  "20261025010500_resume_blocked_repin_context.sql").read_text()

schema="""
create role anon nologin;
create role authenticated nologin;
create role service_role nologin;
create table factory_projects(
  id uuid primary key,project_key text,repository text,
  project_kind text,is_active boolean,manifest jsonb
);
create table factory_project_execution_controls(
  project_id uuid primary key,state text,generation bigint,version bigint
);
create table factory_tasks(
  id uuid primary key,project_id uuid,status text,scope_keys jsonb,updated_at timestamptz
);
create table factory_runs(
  id uuid primary key,task_id uuid,status text,execution_route text,
  candidate_commit text,metadata jsonb,
  attempt_count integer,lease_owner text,lease_expires_at timestamptz,
  last_error text
);
create table factory_change_sets(
  id uuid primary key,project_id uuid,root_task_id uuid,status text,
  source_commit text,candidate_commit text,current_wave integer,
  release_run_id uuid,lease_owner text,lease_expires_at timestamptz,
  metadata jsonb,created_at timestamptz not null default now(),
  updated_at timestamptz
);
create table factory_change_set_work_units(
  id uuid primary key,change_set_id uuid,run_id uuid,task_id uuid,
  status text,base_commit text,branch_name text,output_commit text,
  changed_files jsonb,wave integer,updated_at timestamptz
);
create table factory_work_unit_context_packets(
  id uuid primary key,project_id uuid,run_id uuid,
  work_unit_id uuid,change_set_id uuid,version integer,
  packet_hash text,packet jsonb
);
create table factory_audit_events(
  id bigint generated always as identity primary key,
  project_id uuid,task_id uuid,run_id uuid,
  actor_type text,actor_ref text,event_type text,payload jsonb
);
"""

project,root_task,task,root_run,run,change_set,unit,ctx=(uuid4() for _ in range(8))
sha="a"*40
old_sha="b"*40
repo="owner/crm"
branch="preview/release-candidate"
unit_branch="factory/cs-repin-entry"
previous_hash="c"*64
current_hash="d"*64
scopes=["src/components/layout/Sidebar.tsx",
        "src/app/(dashboard)/service-desk/page.tsx",
        "src/lib/service-desk/entry-guard.ts",
        "src/lib/service-desk/entry-guard.test.ts"]
error=("The active docs/codex/CURRENT_TASK.md authorizes implementation only from "
       +branch+" at "+old_sha
       +", or a successor explicitly repinned after exact CRM validation. "
       +"The supplied work unit instead requires exact base "+sha
       +", with no explicit repin. This conflict prevents confirming the task "
       +"is authorized on the provided base, so no files were changed.")
manifest={"delivery_target":{"repository":repo,"branch":branch,"sha":sha,
 "mode":"open_pr_candidate","schema_version":1,"candidate_pr_number":56,
 "repin_policy":{"enabled":True,"native_ci":{
    "event":"pull_request","workflow_id":372542929,"workflow_name":"CRM validation"}}}}
blocked={"type":"repository_governance","reason":error,
         "run_id":str(run),"work_unit_id":str(unit)}
metadata={"source":"change-set","change_set_id":str(change_set),
          "execution_generation":12,"literal_scope_recovery":{
             "previous_packet_hash":previous_hash,"execution_generation":12}}
change_metadata={"blocker":blocked,"last_literal_scope_recovery":{
   "run_id":str(run),"work_unit_id":str(unit),
   "previous_packet_hash":previous_hash}}
packet={"version":1,"sha256":current_hash,"repository":{
    "project_key":"crm","repository":repo,
    "exact_base_commit":sha,"work_branch":unit_branch,"write_scopes":scopes}}
repin_receipt={"source":"github_actions_exact_sha","status":"updated",
  "project_key":"crm","repository":repo,"branch":branch,"pr_number":56,
  "old_sha":old_sha,"new_sha":sha,"ci_sha":sha,"ci_run_id":40143764314,
  "generation":12,"version":11,"compare_status":"ahead",
  "ahead_by":1,"behind_by":0}
old_recovery={"change_set_id":str(change_set),"work_unit_id":str(unit),
  "previous_packet_hash":previous_hash,"execution_generation":12}


with psycopg.connect(dsn,autocommit=True) as db:
    db.execute(schema)
    db.execute(migration)
    acl=db.execute("""
      select prosecdef,
        has_function_privilege('service_role',oid,'execute'),
        has_function_privilege('anon',oid,'execute'),
        has_function_privilege('authenticated',oid,'execute')
      from pg_proc where proname='factory_resume_blocked_repin_context_v1'
    """).fetchone()
    assert acl==(False,True,False,False),acl
    db.execute("insert into factory_projects values (%s,'crm',%s,'existing',true,%s::jsonb)",
               (project,repo,json.dumps(manifest)))
    db.execute("insert into factory_project_execution_controls values (%s,'running',12,11)",
               (project,))
    db.execute("insert into factory_tasks values (%s,%s,'completed','[]'::jsonb,null)",
               (root_task,project))
    db.execute("insert into factory_tasks values (%s,%s,'blocked',%s::jsonb,null)",
               (task,project,json.dumps(scopes)))
    db.execute("insert into factory_runs values (%s,%s,'completed','direct',null,"
               "'{}'::jsonb,1,null,null,null)",(root_run,root_task))
    db.execute("insert into factory_runs values (%s,%s,'blocked','direct',null,"
               "%s::jsonb,2,null,null,%s)",(run,task,json.dumps(metadata),error))
    db.execute("insert into factory_change_sets values (%s,%s,%s,'blocked',%s,%s,"
               "1,null,null,null,%s::jsonb,now(),null)",
               (change_set,project,root_task,sha,sha,json.dumps(change_metadata)))
    db.execute("insert into factory_change_set_work_units values (%s,%s,%s,%s,"
               "'blocked',%s,%s,null,'[]'::jsonb,1,null)",
               (unit,change_set,run,task,sha,unit_branch))
    db.execute("insert into factory_work_unit_context_packets values (%s,%s,%s,"
               "%s,%s,1,%s,%s::jsonb)",
               (ctx,project,run,unit,change_set,current_hash,json.dumps(packet)))
    db.execute("insert into factory_audit_events(project_id,run_id,"
               "actor_type,actor_ref,event_type,payload) values"
               "(%s,%s,'system','literal-scope-recovery',"
               "'change_set.literal_scope_requeued',%s::jsonb)",
               (project,run,json.dumps(old_recovery)))
    db.execute("insert into factory_audit_events(project_id,actor_type,"
               "actor_ref,event_type,payload) values"
               "(%s,'system','factory-candidate-reconciler',"
               "'project.delivery_target.reconciled',%s::jsonb)",
               (project,json.dumps(repin_receipt)))

    def recover():
        result=db.execute(
            "select public.factory_resume_blocked_repin_context_v1(%s)",(2,)
        ).fetchone()[0]
        assert result["release_authorized"] is False,result
        assert result["product_stage_replayed"] is False,result
        assert result["paid_model_calls"]==0,result
        return result

    def must_stay_blocked():
        result=recover()
        assert result["requeued"]==0,result
        assert db.execute("select status from factory_runs where id=%s",
                          (run,)).fetchone()[0]=="blocked"

    # No recovery under cross-epoch, stale proof, leases, stale schema or
    # previous code writes. All mutations here touch ONLY disposable fixtures.
    db.execute("update factory_project_execution_controls set generation=13 where project_id=%s",
               (project,))
    must_stay_blocked()
    db.execute("update factory_project_execution_controls set generation=12 where project_id=%s",
               (project,))

    db.execute("update factory_project_execution_controls set version=12 where project_id=%s",
               (project,))
    must_stay_blocked()
    db.execute("update factory_project_execution_controls set version=11 where project_id=%s",
               (project,))

    db.execute("update factory_runs set lease_owner='active-worker' where id=%s",(run,))
    must_stay_blocked()
    db.execute("update factory_runs set lease_owner=null where id=%s",(run,))

    db.execute("update factory_change_set_work_units set output_commit=%s where id=%s",
               (sha,unit))
    must_stay_blocked()
    db.execute("update factory_change_set_work_units set output_commit=null where id=%s",
               (unit,))

    db.execute("update factory_work_unit_context_packets set packet=jsonb_set("
               "packet,'{repository,delivery_repin_evidence}','{}'::jsonb)"
               " where id=%s",(ctx,))
    must_stay_blocked()
    db.execute("update factory_work_unit_context_packets set packet=%s::jsonb where id=%s",
               (json.dumps(packet),ctx))

    db.execute("update factory_runs set attempt_count=3 where id=%s",(run,))
    must_stay_blocked()
    db.execute("update factory_runs set attempt_count=2 where id=%s",(run,))

    db.execute("update factory_tasks set status='running' where id=%s",(root_task,))
    must_stay_blocked()
    db.execute("update factory_tasks set status='completed' where id=%s",(root_task,))

    db.execute("update factory_projects set manifest=jsonb_set(manifest,"
               "'{delivery_target,sha}',to_jsonb(%s::text)) where id=%s",
               ("f"*40,project))
    must_stay_blocked()
    db.execute("update factory_projects set manifest=%s::jsonb where id=%s",
               (json.dumps(manifest),project))

    db.execute("update factory_audit_events set payload=jsonb_set(payload,"
               "'{ci_sha}',to_jsonb(%s::text))"
               " where event_type='project.delivery_target.reconciled'",
               ("f"*40,))
    must_stay_blocked()
    db.execute("update factory_audit_events set payload=%s::jsonb"
               " where event_type='project.delivery_target.reconciled'",
               (json.dumps(repin_receipt),))

    with psycopg.connect(dsn,autocommit=False) as held:
        held.execute("select id from factory_change_sets where id=%s for update",
                     (change_set,))
        must_stay_blocked()
        held.rollback()

    result=recover()
    assert result["status"]=="requeued" and result["requeued"]==1,result
    states=(
        ("factory_runs",run,"queued"),
        ("factory_tasks",task,"queued_execution"),
        ("factory_change_set_work_units",unit,"queued"),
        ("factory_change_sets",change_set,"building"),
    )
    for table,key,wanted in states:
        actual=db.execute("select status from "+table+" where id=%s",
                          (key,)).fetchone()[0]
        assert actual==wanted,(table,actual,wanted)
    assert db.execute("select status from factory_tasks where id=%s",
                      (root_task,)).fetchone()[0]=="completed"
    audit=db.execute("select payload from factory_audit_events"
                     " where event_type='change_set.repin_context_requeued'").fetchall()
    assert len(audit)==1,audit
    assert audit[0][0]["source_sha"]==sha,audit
    assert audit[0][0]["native_ci_run_id"]==40143764314,audit
    assert audit[0][0]["product_stage_replayed"] is False,audit
    assert recover()["requeued"]==0
    try:
        with db.transaction():
            db.execute("select public.factory_resume_blocked_repin_context_v1(3)")
    except psycopg.Error:
        pass
    else:
        raise AssertionError("unbounded requeue accepted")

    print(json.dumps({
       "status":"pass","requeued":1,"replay_requeued":0,
       "negative_cases":9,"audit_events":1,"acl_enforced":True,
       "product_stage_replayed":False,"production_modified":False,
       "paid_model_calls":0,
    }))
