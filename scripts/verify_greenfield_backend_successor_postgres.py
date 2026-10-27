#!/usr/bin/env python3
"""Adversarial real PG16 QA; refuses any non-disposable database identity."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import json
import os

import psycopg
from psycopg.conninfo import conninfo_to_dict

dsn=os.environ.get("FACTORY_GREENFIELD_SUCCESSOR_TEST_DSN","")
config=conninfo_to_dict(dsn)
if (os.environ.get("FACTORY_GREENFIELD_SUCCESSOR_TEST_ISOLATED")!="true"
    or config.get("host") not in ("127.0.0.1","localhost")
    or config.get("dbname")!="factory_greenfield_successor_test"
    or config.get("user")!="factory_ci"):
    raise SystemExit("REFUSING_NON_ISOLATED_GREENFIELD_SUCCESSOR_DATABASE")

root=Path(__file__).resolve().parents[1]
sql=(root/"supabase/migrations/20261027001500_recover_greenfield_backend_candidate_successor.sql").read_text()
assert sql.strip().endswith("COMMIT;")
project,task,run,cs=(uuid4() for _ in range(4))
old,new,origin="a"*40,"b"*40,"c"*40
branch="factory/change-set-60dd6b73"
repo="owner/infodive-service-desk"
url_old="https://old-service-desk-preview.vercel.app"
url_new="https://new-service-desk-preview.vercel.app"
pr=10

schema="""
-- Roles are cluster-scoped; the earlier isolated QA script may have created
-- them in a separate disposable database on this same temporary PG service.
do $roles$
begin
  if not exists (select 1 from pg_roles where rolname='service_role') then
    create role service_role nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname='anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname='authenticated') then
    create role authenticated nologin;
  end if;
end;
$roles$;
create table public.factory_projects (
 id uuid primary key, project_kind text, is_active boolean,repository text,manifest jsonb);
create table public.factory_tasks (id uuid primary key, project_id uuid,status text,updated_at timestamptz);
create table public.factory_change_sets (
 id uuid primary key, project_id uuid,root_task_id uuid,release_run_id uuid,
 status text,candidate_commit text,integration_branch text,
 lease_owner text,lease_expires_at timestamptz,
 metadata jsonb,updated_at timestamptz);
create table public.factory_project_execution_controls (
 project_id uuid primary key,state text,generation bigint);
create table public.factory_runs (
 id uuid primary key,task_id uuid,status text,
 candidate_commit text,branch_name text,metadata jsonb,
 lease_owner text,lease_expires_at timestamptz,
 finished_at timestamptz,last_error text);
create table public.factory_evaluations (
 id uuid primary key default gen_random_uuid(),run_id uuid,
 eval_type text,status text,baseline_ref text,result jsonb,
 created_at timestamptz default now());
create table public.factory_deployments (
 run_id uuid,environment text,status text,metadata jsonb);
create table public.factory_specialist_lane_jobs (
 run_id uuid,role text,status text,required boolean,candidate_commit text);
create table public.factory_tool_usage (
 id bigint generated always as identity primary key,run_id uuid,
 tool_family text,operation text,usage_units numeric,estimated_cost numeric,
 metadata jsonb);
create table public.factory_audit_events (
 id bigint generated always as identity primary key,
 project_id uuid,task_id uuid,run_id uuid,
 actor_type text,actor_ref text,event_type text,payload jsonb);
"""


def github():
    return {"source":"github_actions_exact_sha","repository":repo,
      "old_sha":old,"new_sha":new,"head_sha":new,"head_ref":branch,
      "pr_number":str(pr),"pr_state":"open","merged":False,"draft":False,
      "base_ref":"main","compare_status":"ahead","ahead_by":"4",
      "behind_by":"0","ci_run_id":"40420003503","ci_conclusion":"success",
      "vercel_state":"success","vercel_deployment_id":"dpl_CuYdAFK73HVwJKMzRJe9Uc1HXVQi",
      "preview_url":url_new}

def probe():
    return {"kind":"unauthenticated_json_session_probe","candidate_commit":new,
       "url":url_new+"/api/session","http_status":"401",
       "content_type":"application/json; charset=utf-8",
       "checked_at":datetime.now(timezone.utc).isoformat(timespec="seconds")}

def read(db,q,*args):
    return db.execute(q,args).fetchone()[0]

def invoke(db,evidence=None,health=None,old_sha=old,new_sha=new,pr_num=pr):
    return read(db,
      "select public.factory_recover_greenfield_backend_successor_v1"
      "(%s,%s,%s,%s,%s::jsonb,%s::jsonb)",
      run,old_sha,new_sha,pr_num,
      json.dumps(github() if evidence is None else evidence),
      json.dumps(probe() if health is None else health))

def assert_old(db):
    assert read(db,"select status from public.factory_runs where id=%s",run)=="failed"
    assert read(db,"select candidate_commit from public.factory_runs where id=%s",run)==old
    assert read(db,"select status from public.factory_tasks where id=%s",task)=="failed"
    assert read(db,"select candidate_commit from public.factory_change_sets where id=%s",cs)==old
    assert read(db,"select count(*) from public.factory_audit_events")==0
    assert read(db,"select count(*) from public.factory_evaluations where eval_type='browser_e2e'")==1
    assert read(db,"select count(*) from public.factory_tool_usage where operation='reconcile_pr_candidate'")==1

def blocked(db,*,evidence=None,health=None,old_sha=old,new_sha=new,pr_num=pr):
    try:
        with db.transaction():
            invoke(db,evidence=evidence,health=health,old_sha=old_sha,new_sha=new_sha,pr_num=pr_num)
    except psycopg.Error:
        pass
    else:
        raise AssertionError("invalid environmental successor was accepted")
    assert_old(db)

with psycopg.connect(dsn,autocommit=True) as db:
    db.execute(schema)
    db.execute(sql)
    a=db.execute("""
      select p.prosecdef,has_function_privilege('service_role',p.oid,'execute'),
             has_function_privilege('anon',p.oid,'execute'),
             has_function_privilege('authenticated',p.oid,'execute')
      from pg_proc p join pg_namespace n on n.oid=p.pronamespace
      where n.nspname='public' and p.proname='factory_recover_greenfield_backend_successor_v1'
    """).fetchone()
    assert a==(False,True,False,False),a

    db.execute("insert into public.factory_projects values (%s,'greenfield',true,%s,%s::jsonb)",
      (project,repo,json.dumps({"preview":{"required":True,"provider":"vercel"}})))
    db.execute("insert into public.factory_project_execution_controls values (%s,'running',1)",(project,))
    db.execute("insert into public.factory_tasks(id,project_id,status) values (%s,%s,'failed')",(task,project))
    db.execute("""insert into public.factory_change_sets
      (id,project_id,root_task_id,release_run_id,status,candidate_commit,integration_branch,metadata)
      values (%s,%s,%s,%s,'ci_pending',%s,%s,%s::jsonb)""",
      (cs,project,task,run,old,branch,json.dumps({
         "integration_release_request":{"candidate_commit":old,"pr_number":pr,"branch":branch},
         "integration_epoch_receipt":{"candidate_commit":old,"project_id":str(project),"generation":1}})))
    db.execute("""insert into public.factory_runs
      (id,task_id,status,candidate_commit,branch_name,metadata,finished_at,last_error)
      values (%s,%s,'failed',%s,%s,%s::jsonb,now(),'backend unavailable')""",
      (run,task,old,branch,json.dumps({"change_set_id":str(cs),"execution_generation":1})))
    db.execute("""insert into public.factory_tool_usage
      (run_id,tool_family,operation,metadata) values
      (%s,'github','create_pr',%s::jsonb),(%s,'github','reconcile_pr_candidate',%s::jsonb)""",
      (run,json.dumps({"pr":pr,"head_sha":origin,"change_set_id":str(cs)}),
       run,json.dumps({"pr_number":str(pr),"old_sha":origin,"new_sha":old,
                       "previous_commit":origin,"candidate_commit":old,
                       "change_set_id":str(cs),"compare_status":"ahead",
                       "ahead_by":"5","behind_by":"0"})))
    for role in ("security","qa","operations"):
        db.execute("insert into public.factory_specialist_lane_jobs values (%s,%s,'passed',true,%s)",
          (run,role,old))
    for kind,status,baseline,result in (
        ("github_ci","success",old,{"head_sha":old,"ci_state":"success","pr":str(pr)}),
        ("quality_gate","success",old,{"passed":True}),
        ("browser_e2e","failure",url_old,{"preview_url":url_old,
            "detail":"http_503: fetch /api/session"})):
        db.execute("""insert into public.factory_evaluations
          (run_id,eval_type,status,baseline_ref,result) values (%s,%s,%s,%s,%s::jsonb)""",
          (run,kind,status,baseline,json.dumps(result)))
    db.execute("""insert into public.factory_deployments values
      (%s,'preview','success',%s::jsonb)""",
      (run,json.dumps({"candidate_commit":old,"preview_url":url_old})))
    assert_old(db)
    for field,bad in (
      ("pr_state","closed"),("merged",True),("draft",True),
      ("base_ref","other"),("repository","wrong/repo"),
      ("head_ref","factory/change-set-other"),("compare_status","diverged"),
      ("ahead_by","0"),("behind_by","1"),("ci_conclusion","failure"),
      ("ci_run_id","0"),("vercel_state","pending"),
      ("vercel_deployment_id","invalid"),("preview_url","https://evil.test")):
        g=github();g[field]=bad
        blocked(db,evidence=g)
    for field,bad in (
      ("http_status","503"),("http_status",None),
      ("url","https://evil.vercel.app/api/session"),
      ("candidate_commit",old),("kind","malformed"),
      ("content_type","text/html"),
      ("checked_at",(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()),
      ("checked_at",(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())):
        h=probe();h[field]=bad
        blocked(db,health=h)

    def flip_then_block(q,revert):
        db.execute(q)
        blocked(db)
        db.execute(revert)

    flip_then_block(
      "update public.factory_project_execution_controls set state='paused'",
      "update public.factory_project_execution_controls set state='running'")
    flip_then_block(
      "update public.factory_project_execution_controls set generation=2",
      "update public.factory_project_execution_controls set generation=1")
    flip_then_block("update public.factory_change_sets set lease_owner='busy'",
                    "update public.factory_change_sets set lease_owner=null")
    flip_then_block("update public.factory_runs set lease_owner='busy'",
                    "update public.factory_runs set lease_owner=null")
    flip_then_block("update public.factory_specialist_lane_jobs set status='blocked'",
                    "update public.factory_specialist_lane_jobs set status='passed'")
    flip_then_block("update public.factory_projects set project_kind='existing'",
                    "update public.factory_projects set project_kind='greenfield'")
    flip_then_block("update public.factory_evaluations set status='success' where eval_type='browser_e2e'",
                    "update public.factory_evaluations set status='failure' where eval_type='browser_e2e'")
    flip_then_block("update public.factory_deployments set status='failed'",
                    "update public.factory_deployments set status='success'")

    # Historical receipts are immutable provenance: latest-hop validity alone
    # must not accept a broken original-to-candidate chain.
    db.execute("""update public.factory_tool_usage set metadata =
      jsonb_set(metadata,'{old_sha}',to_jsonb(%s::text),true)
      where operation='reconcile_pr_candidate'""",("d"*40,))
    blocked(db)
    db.execute("""update public.factory_tool_usage set metadata =
      jsonb_set(metadata,'{old_sha}',to_jsonb(%s::text),true)
      where operation='reconcile_pr_candidate'""",(origin,))
    db.execute("""update public.factory_tool_usage set metadata =
      jsonb_set(metadata,'{head_sha}',to_jsonb(%s::text),true)
      where operation='create_pr'""",("e"*40,))
    blocked(db)
    db.execute("""update public.factory_tool_usage set metadata =
      jsonb_set(metadata,'{head_sha}',to_jsonb(%s::text),true)
      where operation='create_pr'""",(origin,))
    assert_old(db)

    result=invoke(db)
    assert result["status"]=="ci_pending" and result["release_authorized"] is False
    assert result["ci_quality_specialists_browser_must_rerun"] is True
    assert read(db,"select candidate_commit from public.factory_runs where id=%s",run)==new
    assert read(db,"select status from public.factory_tasks where id=%s",task)=="integrated"
    assert read(db,"select candidate_commit from public.factory_change_sets where id=%s",cs)==new
    assert read(db,"select count(*) from public.factory_tool_usage where operation='reconcile_pr_candidate'")==2
    assert read(db,"select count(*) from public.factory_evaluations where eval_type='browser_e2e' and status='failure'")==1
    assert read(db,"select count(*) from public.factory_evaluations where eval_type='browser_e2e' and status='pending'")==1
    assert read(db,"select count(*) from public.factory_evaluations where eval_type='browser_e2e' and status='success'")==0
    assert read(db,"select count(*) from public.factory_evaluations where eval_type='quality_gate' and baseline_ref=%s",new)==0
    assert read(db,"select count(*) from public.factory_specialist_lane_jobs where candidate_commit=%s",new)==0
    assert read(db,"select count(*) from public.factory_audit_events")==1
    try:
      with db.transaction():
        invoke(db)
    except psycopg.Error:
      pass
    else:
      raise AssertionError("unbounded duplicate resume was accepted")

print("GREENFIELD_SUCCESSOR_RECOVERY_PG16_PASS=1")
