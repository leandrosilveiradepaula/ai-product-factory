#!/usr/bin/env python3
"""Exercise the candidate webhook wake SQL in isolated, disposable Postgres only."""
from __future__ import annotations
import json
import os
import uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

cfg=conninfo_to_dict(os.environ.get("FACTORY_WEBHOOK_TEST_DSN", ""))
if (os.environ.get("FACTORY_WEBHOOK_TEST_ISOLATED") != "true"
    or cfg.get("host") not in ("127.0.0.1", "localhost")
    or cfg.get("dbname") != "factory_external_webhook_test"):
    raise SystemExit("refusing non-isolated database")

root=Path(__file__).resolve().parents[1]
sql=(root/"supabase/migrations/20261029165500_github_external_event_wake_outbox.sql").read_text()
schema="""
create role service_role nologin;
create role anon nologin;
create role authenticated nologin;
create table public.factory_projects(id uuid primary key,repository text not null,is_active bool not null default true);
create table public.factory_tasks(id uuid primary key,project_id uuid not null references public.factory_projects(id));
create table public.factory_runs(id uuid primary key,task_id uuid not null references public.factory_tasks(id),
 status text,candidate_commit text,metadata jsonb not null default '{}'::jsonb,execution_route text,created_at timestamptz default now());
create table public.factory_project_execution_controls(project_id uuid primary key,state text,generation bigint);
create table public.factory_project_github_access(project_id uuid primary key,repository text,repository_id bigint,
 installation_id bigint,auth_mode text,status text);
create table public.factory_tool_usage(id bigserial primary key,run_id uuid,operation text,metadata jsonb);
create table public.factory_audit_events(project_id uuid,run_id uuid,actor_type text,actor_ref text,event_type text,payload jsonb);
"""
repo="leandrosilveiradepaula/crm-infodive"
sha="a"*40
repo_id,installation_id=1189600617,167522851
project_id,task_id,run_id=uuid.uuid4(),uuid.uuid4(),uuid.uuid4()

def claim(db,delivery_id,event="check_run",action="completed",repository=repo,
          repository_id=repo_id,installation_id=installation_id,candidate_sha=sha,pr=None):
    return db.execute("""select public.factory_claim_external_webhook_wake_v1(
    %s,%s,%s,%s,%s,%s,%s,%s)""",(delivery_id,event,action,repository_id,
    repository,installation_id,candidate_sha,pr)).fetchone()[0]

def ack(db,delivery_id,attempt,outcome):
    return db.execute("select public.factory_ack_external_webhook_wake_v1(%s,%s,%s)",
                      (delivery_id,attempt,outcome)).fetchone()[0]

with psycopg.connect(os.environ["FACTORY_WEBHOOK_TEST_DSN"],autocommit=True) as db:
    db.execute(schema)
    db.execute(sql)
    for fn in ("factory_claim_external_webhook_wake_v1",
               "factory_ack_external_webhook_wake_v1"):
        perms=db.execute("""select p.prosecdef,
          has_function_privilege('service_role',p.oid,'EXECUTE'),
          has_function_privilege('anon',p.oid,'EXECUTE'),
          has_function_privilege('authenticated',p.oid,'EXECUTE')
          from pg_proc p where p.proname=%s""",(fn,)).fetchone()
        assert perms==(False,True,False,False),(fn,perms)
    rls=db.execute("""select c.relrowsecurity from pg_class c where c.relname='factory_external_webhook_wakes'""").fetchone()
    assert rls==(True,),rls

    db.execute("insert into public.factory_projects(id,repository) values(%s,%s)",(project_id,repo))
    db.execute("insert into public.factory_tasks(id,project_id) values(%s,%s)",(task_id,project_id))
    db.execute("insert into public.factory_runs(id,task_id,status,candidate_commit,metadata,execution_route) values(%s,%s,'ci_pending',%s,%s::jsonb,'direct')",
       (run_id,task_id,sha,json.dumps({"execution_generation":5})))
    db.execute("insert into public.factory_project_execution_controls values(%s,'running',5)",(project_id,))
    db.execute("insert into public.factory_project_github_access values(%s,%s,%s,%s,'github_app','ready')",
               (project_id,repo,repo_id,installation_id))
    db.execute("insert into public.factory_tool_usage(run_id,operation,metadata) values(%s,'create_pr',%s::jsonb)",
               (run_id,json.dumps({"pr":205,"head_sha":sha})))

    for wrong in (
       {"repository_id":999}, {"installation_id":999}, {"repository":"attacker/other"},
       {"candidate_sha":"b"*40}, {"pr":206}):
        assert claim(db,uuid.uuid4(),**wrong)=={"status":"ignored"},wrong
    assert db.execute("select count(*) from public.factory_external_webhook_wakes").fetchone()[0]==0

    delivery=uuid.uuid4()
    first=claim(db,delivery,pr=205)
    assert first["status"]=="claimed" and first["attempt"]==1 and first["run_id"]==str(run_id),first
    assert claim(db,delivery,pr=205)=={"status":"duplicate"},"concurrent duplicate was claimed"
    try:
        with db.transaction():claim(db,delivery,pr=206)
    except psycopg.Error:pass
    else:raise AssertionError("delivery identity drift not rejected")
    assert ack(db,delivery,1,"requested")=={"status":"requested"}
    assert claim(db,delivery,pr=205)=={"status":"duplicate"},"redelivery relaunched"
    assert db.execute("select attempts from public.factory_external_webhook_wakes where delivery_id=%s",(delivery,)).fetchone()[0]==1

    failing=uuid.uuid4()
    assert claim(db,failing)["status"]=="claimed"
    assert ack(db,failing,1,"failed")=={"status":"retryable"}
    assert claim(db,failing)=={"status":"deferred"}
    db.execute("update public.factory_external_webhook_wakes set next_attempt_at=now()-interval '1 minute' where delivery_id=%s",(failing,))
    assert claim(db,failing)["attempt"]==2
    db.execute("update public.factory_project_execution_controls set state='paused' where project_id=%s",(project_id,))
    assert ack(db,failing,2,"requested")=={"status":"suppressed"},"paused project acknowledged active wake"
    assert claim(db,uuid.uuid4())=={"status":"ignored"},"paused project admitted"
    db.execute("update public.factory_project_execution_controls set state='running',generation=6 where project_id=%s",(project_id,))
    assert claim(db,uuid.uuid4())=={"status":"ignored"},"old execution epoch admitted"

    db.execute("update public.factory_runs set metadata=%s::jsonb where id=%s",(json.dumps({"execution_generation":6}),run_id))
    d=uuid.uuid4();assert claim(db,d)["status"]=="claimed"
    db.execute("update public.factory_project_execution_controls set state='stopped' where project_id=%s",(project_id,))
    assert ack(db,d,1,"requested")=={"status":"suppressed"}

    db.execute("update public.factory_project_execution_controls set state='running' where project_id=%s",(project_id,))
    db.execute("update public.factory_runs set status='preview_ready' where id=%s",(run_id,))
    dep=uuid.uuid4();assert claim(db,dep,event="deployment_status",action="created")["status"]=="claimed"
    assert claim(db,uuid.uuid4(),event="workflow_run")=={"status":"ignored"}
    assert ack(db,dep,1,"requested")=={"status":"requested"}
    db.execute("update public.factory_runs set status='awaiting_release' where id=%s",(run_id,))
    pr=uuid.uuid4();assert claim(db,pr,event="pull_request",action="closed",pr=205)["status"]=="claimed"
    assert claim(db,uuid.uuid4(),event="pull_request",action="closed",pr=999)=={"status":"ignored"}
    assert ack(db,pr,1,"requested")=={"status":"requested"}
    assert db.execute("select count(*) from public.factory_audit_events where event_type='github.webhook.wake_acknowledged'").fetchone()[0]==6

    # Candidate recovery SQL runs only in this disposable PostgreSQL fixture.
    recovery_sql=(root/"supabase/migrations/20261030024500_reconcile_external_webhook_wake_retries.sql").read_text()
    db.execute(recovery_sql)
    acl=db.execute("""select p.prosecdef,
      has_function_privilege('service_role',p.oid,'EXECUTE'),
      has_function_privilege('anon',p.oid,'EXECUTE'),
      has_function_privilege('authenticated',p.oid,'EXECUTE')
      from pg_proc p where p.proname='factory_reconcile_external_webhook_wakes_v1'""").fetchone()
    assert acl==(False,True,False,False),acl
    def reconcile(ci=False,preview=False,release=False):
        return db.execute("""select public.factory_reconcile_external_webhook_wakes_v1(
          %s,%s,%s,%s,%s)""",(40989033146,ci,preview,release,8)).fetchone()[0]
    # No valid lane -> no fabricated dispatch or task claim.
    assert reconcile()=={"status":"ok","inspected":0,"runner_observed":0,
                            "suppressed":0,"exhausted":0,"deferred":0}
    db.execute("update public.factory_runs set status='ci_pending' where id=%s",(run_id,))
    stale=uuid.uuid4()
    assert claim(db,stale)["status"]=="claimed"
    assert ack(db,stale,1,"failed")=={"status":"retryable"}
    db.execute("update public.factory_external_webhook_wakes set next_attempt_at=now()-interval '1 second' where delivery_id=%s",(stale,))
    deferred=reconcile(ci=False)
    assert deferred["deferred"]==1,deferred
    observed=reconcile(ci=True)
    assert observed["runner_observed"]==1,observed
    receipt=db.execute("select status,last_result,attempts from public.factory_external_webhook_wakes where delivery_id=%s",(stale,)).fetchone()
    assert receipt==("requested","runner_probe_observed_no_http_dispatch",1),receipt
    assert reconcile(ci=True)["inspected"]==0,"must not observe twice"
    # Pause suppresses pending wake even with a true lane from another project.
    paused=uuid.uuid4();assert claim(db,paused)["status"]=="claimed"
    assert ack(db,paused,1,"failed")=={"status":"retryable"}
    db.execute("update public.factory_external_webhook_wakes set next_attempt_at=now()-interval '1 second' where delivery_id=%s",(paused,))
    db.execute("update public.factory_project_execution_controls set state='paused' where project_id=%s",(project_id,))
    assert reconcile(ci=True)["suppressed"]==1
    db.execute("update public.factory_project_execution_controls set state='running' where project_id=%s",(project_id,))
    # Generation change revokes the immutable delivery even if the lane is true.
    epoch=uuid.uuid4();assert claim(db,epoch)["status"]=="claimed"
    assert ack(db,epoch,1,"failed")=={"status":"retryable"}
    db.execute("update public.factory_external_webhook_wakes set next_attempt_at=now()-interval '1 second' where delivery_id=%s",(epoch,))
    db.execute("update public.factory_project_execution_controls set generation=7 where project_id=%s",(project_id,))
    assert reconcile(ci=True)["suppressed"]==1
    assert db.execute("""select count(*) from public.factory_audit_events
      where event_type='github.webhook.wake_reconciled'""").fetchone()[0]==3

print("GITHUB_EXTERNAL_WEBHOOK_POSTGRES_PASS=1")