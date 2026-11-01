"""Adversarial, disposable PostgreSQL QA for audited legacy OWNER V1 quarantine.

Never connect to production: the DSN must use the isolated GitHub Actions DB.
"""
import os
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
DSN = os.environ.get("FACTORY_OWNER_V1_QUARANTINE_TEST_DSN", "")
if "localhost:5432/owner_v1_quarantine_test" not in DSN:
    raise SystemExit("REFUSING_NON_ISOLATED_OWNER_V1_QUARANTINE_DB")
MIGRATION = (ROOT / "supabase/migrations/20261101142000_owner_start_v1_misroute_quarantine.sql").read_text()
PROJECT = "11111111-1111-4111-8111-111111111111"
TASK = "22222222-2222-4222-8222-222222222222"
RUN = "33333333-3333-4333-8333-333333333333"
ACTOR = "44444444-4444-4444-8444-444444444444"
REQUEST = "55555555-5555-4555-8555-555555555555"
COMMAND = "66666666-6666-4666-8666-666666666666"
COMMENT = 7123456789

def call(c, *args):
    c.execute("select public.factory_quarantine_owner_v1_misroute(" +
              ",".join(["%s"] * len(args)) + ")", args)
    return c.fetchone()[0]

def rejects(conn, *args):
    try:
        with conn.transaction():
            with conn.cursor() as c:
                call(c, *args)
    except psycopg.Error:
        return
    raise AssertionError("unsafe or replay-mismatched recovery was accepted")

params = (RUN, TASK, COMMAND, ACTOR, 17, 17, COMMENT, REQUEST)
with psycopg.connect(DSN, autocommit=True) as db:
    with db.cursor() as c:
        c.execute("drop schema public cascade; create schema public;")
        c.execute("""
        create role service_role; create role authenticated; create role anon;
        create table public.factory_projects(id uuid primary key, project_key text,
          repository text, project_kind text, is_active boolean, manifest jsonb);
        create table public.factory_project_execution_controls(
          project_id uuid, state text, generation bigint, version bigint);
        create table public.factory_console_operators(user_id uuid,role text,is_active boolean);
        create table public.factory_tasks(id uuid primary key,project_id uuid,parent_task_id uuid,
          journey_id uuid, status text,updated_at timestamptz default now());
        create table public.factory_runs(id uuid primary key,task_id uuid,status text,
          journey_id uuid,lease_owner text,lease_expires_at timestamptz,
          source_commit text,candidate_commit text,branch_name text,
          metadata jsonb,finished_at timestamptz,last_error text);
        create table public.factory_change_sets(root_task_id uuid);
        create table public.factory_human_gates(run_id uuid);
        create table public.factory_evaluations(run_id uuid);
        create table public.factory_deployments(run_id uuid);
        create table public.factory_release_reports(run_id uuid);
        create table public.factory_tool_usage(run_id uuid,operation text,metadata jsonb);
        create table public.factory_audit_events(id bigint generated always as identity,
          project_id uuid,task_id uuid,run_id uuid,actor_type text,actor_ref text,
          event_type text,payload jsonb,created_at timestamptz default now());
        create function public.factory_control_quiescent(p_project uuid)
        returns boolean language sql stable security invoker set search_path='' as $f$
        select not exists(select 1 from public.factory_runs r join public.factory_tasks t
          on t.id=r.task_id where t.project_id=p_project and
          r.lease_owner is not null and (r.lease_expires_at is null or r.lease_expires_at>now())
          and r.status not in ('completed','cancelled','failed','blocked'))
        $f$;
        """)
        c.execute(MIGRATION)
        c.execute("insert into public.factory_console_operators values (%s,'admin',true)",(ACTOR,))
        c.execute("""insert into public.factory_projects values
          (%s,'crm-infodive','leandrosilveiradepaula/crm-infodive','existing',
          true,%s)""",(PROJECT,Jsonb({"journey_delivery_binding_v2":{"enabled":True}})))
        c.execute("insert into public.factory_project_execution_controls values (%s,'paused',17,17)",(PROJECT,))
        c.execute("insert into public.factory_tasks(id,project_id,status) values(%s,%s,'queued')",(TASK,PROJECT))
        meta={"source":"github-owner","execution_generation":17,
          "continuation_request_id":REQUEST,
          "continuation_request":{"github":{
            "actor_id":256917842,"comment_id":COMMENT,"issue_number":1055}},
          "stages":["reconciliation","gap_analysis","planning"]}
        c.execute("""insert into public.factory_runs(id,task_id,status,metadata)
          values(%s,%s,'created',%s)""",(RUN,TASK,Jsonb(meta)))
        c.execute("""insert into public.factory_tool_usage values
          (%s,'enqueue_project_reconciliation',%s)""",
          (RUN,Jsonb({"comment_id":COMMENT,"request_id":REQUEST})))
        for event in ("project.continuation.requested","project.reconciliation.enqueued"):
            c.execute("""insert into public.factory_audit_events(
              project_id,task_id,run_id,actor_type,event_type,payload)
              values (%s,%s,%s,'system',%s,'{}')""",(PROJECT,TASK,RUN,event))

    # Roles and wrong inputs must never be allowed to transition.
    rejects(db, *params[:4], 17, 16, COMMENT, REQUEST)
    rejects(db, RUN, TASK, COMMAND, "77777777-7777-4777-8777-777777777777",17,17,COMMENT,REQUEST)
    rejects(db, *params[:7], "88888888-8888-4888-8888-888888888888")
    rejects(db, *params[:6], COMMENT+1, REQUEST)
    with db.transaction():
        with db.cursor() as c:
            c.execute("set local role authenticated")
            try:
                call(c,*params)
            except psycopg.Error:
                pass
            else:
                raise AssertionError("authenticated reached service-only RPC")
    with db.cursor() as c:
        c.execute("update public.factory_project_execution_controls set state='running'")
    rejects(db,*params)
    with db.cursor() as c:
        c.execute("update public.factory_project_execution_controls set state='paused'")
        c.execute("update public.factory_runs set lease_owner='worker'")
    rejects(db,*params)
    with db.cursor() as c:
        c.execute("update public.factory_runs set lease_owner=null")
        c.execute("insert into public.factory_human_gates values (%s)",(RUN,))
    rejects(db,*params)
    with db.cursor() as c:
        c.execute("delete from public.factory_human_gates")
        c.execute("insert into public.factory_tool_usage values (%s,'unexpected', '{}'::jsonb)",(RUN,))
    rejects(db,*params)
    with db.cursor() as c:
        c.execute("delete from public.factory_tool_usage where operation='unexpected'")
        c.execute("insert into public.factory_tasks(id,project_id,parent_task_id,status) values ('99999999-9999-4999-8999-999999999999',%s,%s,'queued')",(PROJECT,TASK))
    rejects(db,*params)
    with db.cursor() as c:
        c.execute("delete from public.factory_tasks where parent_task_id=%s",(TASK,))
        receipt=call(c,*params)
        assert receipt["status"]=="quarantined" and receipt["generation"]==17
        assert receipt["ready_for_production"] is False
        assert receipt["journey_created"] is False
        again=call(c,*params)
        assert again==receipt, "same command must replay idempotently"
        c.execute("select status,finished_at from public.factory_runs where id=%s",(RUN,))
        status, finished_at=c.fetchone()
        assert status=="cancelled" and finished_at is not None
        c.execute("select status from public.factory_tasks where id=%s",(TASK,))
        assert c.fetchone()[0]=="cancelled"
        c.execute("select count(*) from public.factory_audit_events where run_id=%s and event_type='owner_start.v1_misroute_quarantined'",(RUN,))
        assert c.fetchone()[0]==1, "audit must be written once"
        c.execute("select state,generation,version from public.factory_project_execution_controls where project_id=%s",(PROJECT,))
        assert c.fetchone()==("paused",17,17), "quarantine must not resume or advance epoch"
        c.execute("select count(*) from public.factory_runs where journey_id is not null")
        assert c.fetchone()[0]==0, "no synthetic journey is allowed"
    rejects(db, RUN, TASK, COMMAND, ACTOR,17,17,COMMENT+1,REQUEST)
    rejects(db, RUN, TASK, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",ACTOR,17,17,COMMENT,REQUEST)

print("OWNER_V1_MISROUTE_QUARANTINE_POSTGRES_PASS")
