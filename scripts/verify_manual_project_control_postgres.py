#!/usr/bin/env python3
"""Disposable PostgreSQL regression: no remote DB, no model, no production write."""
import os
import uuid
import psycopg
from psycopg.conninfo import conninfo_to_dict
from pathlib import Path

dsn=os.environ.get("FACTORY_CONTROL_TEST_DSN","")
cfg=conninfo_to_dict(dsn)
if os.environ.get("FACTORY_CONTROL_TEST_ISOLATED")!="true" or cfg.get("host") not in ("localhost","127.0.0.1") or cfg.get("dbname")!="factory_project_control_test":
    raise SystemExit("refusing non-isolated database")
root=Path(__file__).resolve().parents[1]
setup="""
create role service_role nologin;create role anon nologin;create role authenticated nologin;
create table public.factory_projects(
 id uuid primary key default gen_random_uuid(),project_key text unique,name text default 'x',
 repository text,project_kind text default 'greenfield',lifecycle_stage text default 'discovery',
 manifest jsonb default '{}'::jsonb,is_active boolean default true,updated_at timestamptz default now());
create table public.factory_tasks(
 id uuid primary key default gen_random_uuid(),project_id uuid references public.factory_projects(id),
 parent_task_id uuid,external_key text,title text,description text,status text default 'queued',
 complexity text,risk jsonb,acceptance_criteria jsonb,depends_on jsonb,
 created_at timestamptz default now(),updated_at timestamptz default now());
create table public.factory_runs(
 id uuid primary key default gen_random_uuid(),task_id uuid references public.factory_tasks(id),
 status text default 'created',execution_route text,metadata jsonb,
 lease_owner text,lease_expires_at timestamptz,started_at timestamptz,created_at timestamptz default now());
create table public.factory_change_sets(
 id uuid primary key default gen_random_uuid(),project_id uuid references public.factory_projects(id),
 status text,lease_owner text,lease_expires_at timestamptz);
create table public.factory_run_agent_assignments(
 id uuid primary key default gen_random_uuid(),run_id uuid references public.factory_runs(id),status text);
create table public.factory_product_specs(project_id uuid,version int,status text,spec jsonb);
create table public.factory_project_attachments(project_id uuid,draft_id uuid,operator_user_id uuid,finalized_at timestamptz);
create table public.factory_tool_usage(run_id uuid,tool_family text,operation text,usage_units int,estimated_cost numeric,metadata jsonb);
create table public.factory_audit_events(
 project_id uuid,run_id uuid,task_id uuid,actor_type text,actor_ref text,event_type text,payload jsonb);
create function public.factory_finalize_project_attachments(uuid,uuid,uuid) returns int language sql as $$select 0$$;
create function public.factory_start_project_intake_v1(text,text,text,text,jsonb,jsonb,uuid,uuid,integer)
returns jsonb language sql as $$select '{}'::jsonb$$;
grant execute on function public.factory_start_project_intake_v1(text,text,text,text,jsonb,jsonb,uuid,uuid,integer) to service_role;
"""
with psycopg.connect(dsn,autocommit=True) as conn:
    conn.execute(setup)
    conn.execute((root/"supabase/migrations/20260925200339_factory_create_project_intake_rpc.sql").read_text())
    conn.execute((root/"supabase/migrations/20261014160500_atomic_project_continuation.sql").read_text())
    legacy=conn.execute("insert into public.factory_projects(project_key) values ('legacy') returning id").fetchone()[0]
    conn.execute((root/"supabase/migrations/20261017111500_factory_manual_project_execution_controls.sql").read_text())
    conn.execute((root/"supabase/migrations/20261017193000_factory_graceful_stop_preserve_queue.sql").read_text())
    assert conn.execute("select state from public.factory_project_execution_controls where project_id=%s",(legacy,)).fetchone()[0]=="running"
    request_id=uuid.uuid4()
    actor=uuid.uuid4()
    args=("new-qa","Test","","greenfield",
        '{"source":"factory-console","onboarding_mode":"greenfield"}',
        '{"summary":"test"}',request_id,actor,0)
    def register():
        return conn.execute("select public.factory_register_project_intake_v2(%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)",args).fetchone()[0]
    draft=register()
    assert draft["state"]=="draft" and draft["created"] is True,draft
    assert register()["created"] is False
    pid=draft["project_id"]
    assert conn.execute("select count(*) from public.factory_tasks where project_id=%s",(pid,)).fetchone()[0]==0
    def call(command,version,key=None):
        return conn.execute("select public.factory_control_project_v1(%s,%s,%s,%s,%s)",("new-qa",command,key or uuid.uuid4(),version,actor)).fetchone()[0]
    try:
        with conn.transaction():
            conn.execute("insert into public.factory_tasks(project_id,title) values (%s,'bad')",(pid,))
    except psycopg.Error: pass
    else: raise AssertionError("draft admitted work")
    start_id=uuid.uuid4()
    started=call("start",0,start_id)
    assert started["state"]=="running" and started["run_id"],started
    assert call("start",0,start_id)==started
    # An unbounded worker lease prevents false PAUSED.
    run_id=started["run_id"]
    conn.execute("update public.factory_runs set lease_owner='worker-a', lease_expires_at=null where id=%s",(run_id,))
    pause=call("pause",1)
    assert pause["state"]=="pausing",pause
    pending=conn.execute("select public.factory_settle_project_control_v1(%s)",("new-qa",)).fetchone()[0]
    assert pending["state"]=="pausing" and pending["changed"] is False,pending
    # Graceful pause also lets the current owner finish without admitting a new claim.
    conn.execute("update public.factory_runs set lease_expires_at=now()+interval '10 minutes' where id=%s",(run_id,))
    conn.execute("update public.factory_runs set lease_owner=null, lease_expires_at=null where id=%s",(run_id,))
    settled=conn.execute("select public.factory_settle_project_control_v1(%s)",("new-qa",)).fetchone()[0]
    assert settled["state"]=="paused" and settled["version"]==3,settled
    try:
        with conn.transaction():
            conn.execute("insert into public.factory_tasks(project_id,title) values (%s,'bad')",(pid,))
    except psycopg.Error: pass
    else: raise AssertionError("paused admitted work")
    resume=call("resume",3)
    assert resume["state"]=="running" and resume["generation"]==2
    stopped=call("stop",4)
    assert stopped["state"]=="stopped",stopped
    restart_id=uuid.uuid4()
    restarted=call("restart",5,restart_id)
    assert restarted["state"]=="running" and restarted["generation"]==3
    assert call("restart",5,restart_id)==restarted
    assert conn.execute("select version,generation from public.factory_project_execution_controls where project_id=%s",(pid,)).fetchone()==(6,3)
    assert conn.execute("select count(*) from public.factory_tasks where project_id=%s",(pid,)).fetchone()[0]==1
    # A concurrent operator lock must prevent a new claim without deadlock.
    # Use an independent connection: the primary session owns the control lock.
    with psycopg.connect(dsn,autocommit=True) as contender:
        with conn.transaction():
            conn.execute("select 1 from public.factory_project_execution_controls where project_id=%s for update",(pid,))
            contender.execute("set statement_timeout='3000ms'")
            blocked=contender.execute("select public.factory_claim_next_run(%s)",("blocked-worker",)).fetchone()[0]
            assert blocked is None,blocked
    # Releasing the operator lock makes the queued run claimable again.
    # Runtime claim returns the same generation used for external side-effect fencing.
    claim=conn.execute("select public.factory_claim_next_run(%s)",("qa-worker",)).fetchone()[0]
    assert claim is not None and claim["execution_generation"]==3,claim
    assert conn.execute("select metadata->>'execution_generation' from public.factory_runs where id=%s",(claim["run_id"],)).fetchone()[0]=="3"
    # Claim must not reuse a run that is already running.
    duplicate=conn.execute("select public.factory_claim_next_run(%s)",("qa-worker-2",)).fetchone()[0]
    assert duplicate is None,duplicate
    # The claim captures the generation in durable metadata.
    assert conn.execute("select status from public.factory_runs where id=%s",
                        (claim["run_id"],)).fetchone()[0]=="running"
    # Side-effect checkpoints fail closed after pause and after resume
    # with a stale generation; this is independent of task/run status.
    conn.execute("select public.factory_assert_project_execution_epoch(%s,%s)",(pid,3))
    try:
        with conn.transaction():
            conn.execute("select public.factory_assert_project_execution_epoch(%s,%s)",(pid,2))
    except psycopg.Error: pass
    else: raise AssertionError("stale execution epoch admitted")
    # Reject a stale operator command without mutating state.
    try:
        with conn.transaction():
            call("pause",4)
    except psycopg.Error: pass
    else: raise AssertionError("stale version accepted")
    assert conn.execute("select state,version from public.factory_project_execution_controls where project_id=%s",(pid,)).fetchone()==("running",6)
    # A paused project must reject a fresh change-set claim, not just task insertion.
    paused_again=call("pause",6)
    assert paused_again["state"]=="paused",paused_again
    try:
        with conn.transaction():
            conn.execute("insert into public.factory_change_sets(project_id,status) values (%s,'queued')",(pid,))
    except psycopg.Error: pass
    else: raise AssertionError("paused project admitted change set")
    # Existing runs cannot acquire a new lease after pause.
    try:
        with conn.transaction():
            conn.execute("update public.factory_runs set lease_owner='worker-new' where id=%s",(run_id,))
    except psycopg.Error: pass
    else: raise AssertionError("paused project admitted run claim")
    try:
        with conn.transaction():
            conn.execute("select public.factory_assert_project_execution_epoch(%s,%s)",(pid,3))
    except psycopg.Error: pass
    else: raise AssertionError("paused project admitted external side effect")
    assert call("resume",7)["state"]=="running"
    conn.execute("select public.factory_assert_project_execution_epoch(%s,%s)",(pid,4))
    try:
        with conn.transaction():
            conn.execute("select public.factory_assert_project_execution_epoch(%s,%s)",(pid,3))
    except psycopg.Error: pass
    else: raise AssertionError("previous generation admitted after resume")

    # A STOP with a live lease must remain pending until the worker quiesces.
    current_version=conn.execute("select version from public.factory_project_execution_controls where project_id=%s",(pid,)).fetchone()[0]
    fresh_run=conn.execute("select r.id from public.factory_runs r join public.factory_tasks t on t.id=r.task_id where t.project_id=%s order by r.created_at desc limit 1",(pid,)).fetchone()
    assert fresh_run is not None
    conn.execute("update public.factory_runs set status='running' where id=%s",(fresh_run[0],))
    conn.execute("update public.factory_runs set lease_owner='stop-test-worker',lease_expires_at=null where id=%s",(fresh_run[0],))
    queued_task=conn.execute("insert into public.factory_tasks(project_id,title,status) values (%s,'preserved queued work','queued') returning id",(pid,)).fetchone()[0]
    queued_run=conn.execute("insert into public.factory_runs(task_id,status) values (%s,'queued') returning id",(queued_task,)).fetchone()[0]
    command_id=uuid.uuid4()
    pending_stop=call("stop",current_version,command_id)
    assert pending_stop["state"]=="stopping",pending_stop
    before=conn.execute("select version from public.factory_project_execution_controls where project_id=%s",(pid,)).fetchone()[0]
    blocked_settlement=conn.execute("select public.factory_settle_project_control_v1(%s)",("new-qa",)).fetchone()[0]
    assert blocked_settlement["state"]=="stopping" and blocked_settlement["changed"] is False
    assert conn.execute("select version from public.factory_project_execution_controls where project_id=%s",(pid,)).fetchone()[0]==before
    try:
        with conn.transaction():
            conn.execute("select public.factory_assert_project_execution_epoch(%s,%s)",(pid,4))
    except psycopg.Error: pass
    else: raise AssertionError("stopping admitted side effect")
    conn.execute("update public.factory_runs set lease_expires_at=now()+interval '10 minutes' where id=%s",(fresh_run[0],))
    try:
        with conn.transaction():
            conn.execute("update public.factory_runs set lease_owner='intruder' where id=%s",(fresh_run[0],))
    except psycopg.Error: pass
    else: raise AssertionError("stopping allowed lease takeover")
    conn.execute("update public.factory_runs set lease_owner=null,lease_expires_at=null where id=%s",(fresh_run[0],))
    done_stop=conn.execute("select public.factory_settle_project_control_v1(%s)",("new-qa",)).fetchone()[0]
    assert done_stop["state"]=="stopped" and done_stop["changed"] is True,done_stop
    assert conn.execute("select status from public.factory_tasks where id=%s",(queued_task,)).fetchone()[0]=="queued"
    assert conn.execute("select status from public.factory_runs where id=%s",(queued_run,)).fetchone()[0]=="queued"
    assert conn.execute("select version from public.factory_project_execution_controls where project_id=%s",(pid,)).fetchone()[0]==before+1
    # A command replay with a different actor or payload is forbidden.
    assert call("stop",current_version,command_id)==pending_stop
    try:
        with conn.transaction():
            conn.execute("select public.factory_control_project_v1(%s,%s,%s,%s,%s)",("new-qa","stop",command_id,current_version,uuid.uuid4()))
    except psycopg.Error: pass
    else: raise AssertionError("command ID reused by another actor")
    try:
        with conn.transaction():
            call("resume",before+1)
    except psycopg.Error: pass
    else: raise AssertionError("invalid transition admitted")

    acl=conn.execute("""select has_function_privilege('anon','public.factory_control_project_v1(text,text,uuid,bigint,uuid)','EXECUTE'),
     has_function_privilege('authenticated','public.factory_control_project_v1(text,text,uuid,bigint,uuid)','EXECUTE'),
     has_function_privilege('service_role','public.factory_control_project_v1(text,text,uuid,bigint,uuid)','EXECUTE')""").fetchone()
    assert acl==(False,False,True),acl
print("PROJECT_MANUAL_CONTROL_POSTGRES_PASS=1")
