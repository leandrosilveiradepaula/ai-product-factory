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
    assert paused_again["state"]=="pausing",paused_again
    conn.execute("update public.factory_runs set lease_owner=null,lease_expires_at=null where id=%s",(claim["run_id"],))
    settled_again=conn.execute("select public.factory_settle_project_control_v1(%s)",("new-qa",)).fetchone()[0]
    assert settled_again["state"]=="paused",settled_again
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
    assert call("resume",8)["state"]=="running"
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
    conn.execute("update public.factory_runs set metadata=coalesce(metadata,'{}'::jsonb)||jsonb_build_object('execution_generation',4) where id=%s",(fresh_run[0],))
    command_id=uuid.uuid4()
    pending_stop=call("stop",current_version,command_id)
    assert pending_stop["state"]=="stopping",pending_stop
    conn.execute("select public.factory_assert_claimed_run_epoch(%s,%s,%s,%s)",(pid,4,fresh_run[0],"stop-test-worker"))
    for bad_worker in ("intruder",""):
        try:
            with conn.transaction():
                conn.execute("select public.factory_assert_claimed_run_epoch(%s,%s,%s,%s)",(pid,4,fresh_run[0],bad_worker))
        except psycopg.Error: pass
        else: raise AssertionError("stopping admitted unclaimed worker")
    try:
        with conn.transaction():
            conn.execute("select public.factory_assert_claimed_run_epoch(%s,%s,%s,%s)",(pid,3,fresh_run[0],"stop-test-worker"))
    except psycopg.Error: pass
    else: raise AssertionError("stopping admitted stale generation")
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

    # An operator can upgrade PAUSING to STOPPING while a run is still
    # owned, without discarding queued work or granting a fresh claim.
    legacy_task=conn.execute("insert into public.factory_tasks(project_id,title,status) values (%s,'already claimed','running') returning id",(legacy,)).fetchone()[0]
    legacy_run=conn.execute("""insert into public.factory_runs(task_id,status,lease_owner,metadata)
     values (%s,'running','legacy-worker',jsonb_build_object('execution_generation',1))
     returning id""",(legacy_task,)).fetchone()[0]
    pending_task=conn.execute("insert into public.factory_tasks(project_id,title,status) values (%s,'preserved after pause-to-stop','queued') returning id",(legacy,)).fetchone()[0]
    pending_run=conn.execute("insert into public.factory_runs(task_id,status) values (%s,'queued') returning id",(pending_task,)).fetchone()[0]
    def legacy_command(command,version):
        return conn.execute("select public.factory_control_project_v1(%s,%s,%s,%s,%s)",("legacy",command,uuid.uuid4(),version,actor)).fetchone()[0]
    pausing_legacy=legacy_command("pause",0)
    assert pausing_legacy["state"]=="pausing",pausing_legacy
    stopping_legacy=legacy_command("stop",1)
    assert stopping_legacy["state"]=="stopping",stopping_legacy
    assert conn.execute("select public.factory_settle_project_control_v1(%s)",("legacy",)).fetchone()[0]["changed"] is False
    assert conn.execute("select status from public.factory_runs where id=%s",(pending_run,)).fetchone()[0]=="queued"
    assert conn.execute("select status from public.factory_tasks where id=%s",(pending_task,)).fetchone()[0]=="queued"
    conn.execute("update public.factory_runs set status='completed',lease_owner=null,lease_expires_at=null where id=%s",(legacy_run,))
    conn.execute("update public.factory_tasks set status='completed' where id=%s",(legacy_task,))
    stopped_legacy=conn.execute("select public.factory_settle_project_control_v1(%s)",("legacy",)).fetchone()[0]
    assert stopped_legacy["state"]=="stopped" and stopped_legacy["version"]==3,stopped_legacy
    assert conn.execute("select status from public.factory_runs where id=%s",(pending_run,)).fetchone()[0]=="queued"
    assert conn.execute("select status from public.factory_tasks where id=%s",(pending_task,)).fetchone()[0]=="queued"

    acl=conn.execute("""select has_function_privilege('anon','public.factory_control_project_v1(text,text,uuid,bigint,uuid)','EXECUTE'),
     has_function_privilege('authenticated','public.factory_control_project_v1(text,text,uuid,bigint,uuid)','EXECUTE'),
     has_function_privilege('service_role','public.factory_control_project_v1(text,text,uuid,bigint,uuid)','EXECUTE')""").fetchone()
    assert acl==(False,False,True),acl

    # Execute the actual routed checkpoint SQL in the disposable local fixture.
    sql=(root/"supabase/migrations/20261017224500_guard_routed_claims_manual_control.sql").read_text()
    marker="create or replace function public.factory_assert_routed_run_epoch("
    assert sql.count(marker)==1
    definition=marker+sql.split(marker,1)[1].split("$f$;",1)[0]+"$f$;"
    conn.execute(definition)
    # Earlier scenarios deliberately leave new-qa stopped; use a fresh fixture.
    pid=conn.execute("insert into public.factory_projects(project_key) values ('routed-epoch-qa') returning id").fetchone()[0]
    conn.execute("select public.factory_control_project_v1(%s,%s,%s,%s,%s)",("routed-epoch-qa","start",uuid.uuid4(),0,actor))
    generation,version=conn.execute("select generation,version from public.factory_project_execution_controls where project_id=%s",(pid,)).fetchone()
    task=conn.execute("insert into public.factory_tasks(project_id,title,status) values (%s,'routed epoch fixture','running') returning id",(pid,)).fetchone()[0]
    run=conn.execute("""insert into public.factory_runs(task_id,status,execution_route,lease_owner,lease_expires_at,metadata)
      values (%s,'implementing','direct','routed-worker',now()+interval '10 minutes',jsonb_build_object('execution_generation',%s)) returning id""",(task,generation)).fetchone()[0]
    def check_epoch(gen,owner,allowed):
        try:
            with conn.transaction():
                conn.execute("select public.factory_assert_routed_run_epoch(%s,%s,%s,%s)",(pid,gen,run,owner))
        except psycopg.Error:
            if allowed:raise
        else:
            if not allowed:raise AssertionError("revoked routed capability accepted")
    check_epoch(generation,"routed-worker",True)
    check_epoch(generation-1,"routed-worker",False)
    check_epoch(generation,"intruder",False)
    conn.execute("update public.factory_runs set lease_expires_at=now()-interval '1 second' where id=%s",(run,))
    check_epoch(generation,"routed-worker",False)
    conn.execute("update public.factory_runs set lease_expires_at=now()+interval '10 minutes' where id=%s",(run,))
    pausing=conn.execute("select public.factory_control_project_v1(%s,%s,%s,%s,%s)",("routed-epoch-qa","pause",uuid.uuid4(),version,actor)).fetchone()[0]
    assert pausing["state"]=="pausing",pausing
    check_epoch(generation,"routed-worker",True)
    conn.execute("update public.factory_runs set lease_owner=null,lease_expires_at=null where id=%s",(run,))
    paused=conn.execute("select public.factory_settle_project_control_v1(%s)",("routed-epoch-qa",)).fetchone()[0]
    assert paused["state"]=="paused",paused
    check_epoch(generation,"routed-worker",False)
    resumed=conn.execute("select public.factory_control_project_v1(%s,%s,%s,%s,%s)",("routed-epoch-qa","resume",uuid.uuid4(),paused["version"],actor)).fetchone()[0]
    assert resumed["generation"]==generation+1,resumed
    check_epoch(generation,"routed-worker",False)

    # Integration fencing: execute the actual production candidate migration in this
    # disposable PostgreSQL fixture, never in the connected production project.
    conn.execute("""alter table public.factory_change_sets
      add column source_commit text, add column candidate_commit text,
      add column integration_branch text, add column current_wave integer default 1,
      add column attempt_count integer default 0,
      add column created_at timestamptz default now(),
      add column updated_at timestamptz default now()""")
    conn.execute("""create table public.factory_change_set_work_units(
      id uuid primary key default gen_random_uuid(),
      change_set_id uuid references public.factory_change_sets(id),
      wave integer, status text, task_id uuid, plan_task_key text,
      agent_key text, base_commit text, branch_name text,
      output_commit text, changed_files jsonb)""")
    migration=(root/"supabase/migrations/20261018003000_fence_change_set_integration_epoch.sql").read_text()
    conn.execute(migration)
    # A fresh running project and completed work unit make a genuine claim possible.
    integration_project=conn.execute(
      "insert into public.factory_projects(project_key,repository) values ('integration-epoch-qa','owner/repo') returning id"
    ).fetchone()[0]
    conn.execute("select public.factory_control_project_v1(%s,%s,%s,%s,%s)",
      ("integration-epoch-qa","start",uuid.uuid4(),0,actor))
    epoch=conn.execute("select generation from public.factory_project_execution_controls where project_id=%s",
      (integration_project,)).fetchone()[0]
    change_set=conn.execute("""insert into public.factory_change_sets(
      project_id,status,source_commit,candidate_commit,integration_branch,current_wave)
      values (%s,'building','source','candidate','factory/integration-qa',1) returning id""",
      (integration_project,)).fetchone()[0]
    conn.execute("""insert into public.factory_change_set_work_units(
      change_set_id,wave,status,plan_task_key,base_commit,output_commit,changed_files)
      values (%s,1,'completed','task-a','candidate','output','["src/a.py"]'::jsonb)""",(change_set,))
    def claim(worker="integration-worker"):
        return conn.execute("select public.factory_claim_change_set_integration(%s,%s)",
          (worker,600)).fetchone()[0]
    claimed=claim()
    assert claimed and claimed["change_set_id"]==str(change_set),claimed
    assert claimed["execution_generation"]==epoch and claimed["lease_owner"]=="integration-worker",claimed
    assert claimed["project_id"]==str(integration_project),claimed
    assert claim("second-worker") is None
    def integration_checkpoint(generation=epoch,owner="integration-worker",wave=1,allowed=True):
        try:
            with conn.transaction():
                conn.execute("select public.factory_assert_change_set_integration_epoch(%s,%s,%s,%s,%s)",
                  (change_set,integration_project,generation,owner,wave))
        except psycopg.Error:
            if allowed:raise
        else:
            if not allowed:raise AssertionError("revoked integration capability accepted")
    integration_checkpoint()
    integration_checkpoint(epoch-1,allowed=False)
    integration_checkpoint(owner="intruder",allowed=False)
    integration_checkpoint(wave=2,allowed=False)
    conn.execute("update public.factory_change_sets set lease_expires_at=now()-interval '1 second' where id=%s",(change_set,))
    integration_checkpoint(allowed=False)
    # A stale lease may be reclaimed only by a running project.
    reclaimed=claim("replacement-worker")
    assert reclaimed and reclaimed["lease_owner"]=="replacement-worker",reclaimed
    integration_checkpoint(allowed=False)
    integration_checkpoint(owner="replacement-worker")
    conn.execute("update public.factory_change_sets set lease_expires_at=now()-interval '1 second' where id=%s",(change_set,))
    current_version=conn.execute("select version from public.factory_project_execution_controls where project_id=%s",
      (integration_project,)).fetchone()[0]
    pausing=conn.execute("select public.factory_control_project_v1(%s,%s,%s,%s,%s)",
      ("integration-epoch-qa","pause",uuid.uuid4(),current_version,actor)).fetchone()[0]
    assert pausing["state"] in ("pausing","paused"),pausing
    integration_checkpoint(owner="replacement-worker",allowed=False)
    assert claim("paused-worker") is None
    if pausing["state"]=="pausing":
        settled=conn.execute("select public.factory_settle_project_control_v1(%s)",("integration-epoch-qa",)).fetchone()[0]
        assert settled["state"]=="paused",settled
    else:
        settled=pausing
    resumed=conn.execute("select public.factory_control_project_v1(%s,%s,%s,%s,%s)",
      ("integration-epoch-qa","resume",uuid.uuid4(),settled["version"],actor)).fetchone()[0]
    assert resumed["generation"]==epoch+1,resumed
    integration_checkpoint(owner="replacement-worker",allowed=False)
    assert claim("resumed-worker") is not None
    integration_checkpoint(generation=epoch+1,owner="resumed-worker")
    acl=conn.execute("""select
      has_function_privilege('anon','public.factory_assert_change_set_integration_epoch(uuid,uuid,bigint,text,integer)','EXECUTE'),
      has_function_privilege('authenticated','public.factory_assert_change_set_integration_epoch(uuid,uuid,bigint,text,integer)','EXECUTE'),
      has_function_privilege('service_role','public.factory_assert_change_set_integration_epoch(uuid,uuid,bigint,text,integer)','EXECUTE')""").fetchone()
    assert acl==(False,False,True),acl
    print("INTEGRATION_EPOCH_POSTGRES_PASS=1")

    # Apply the new atomic SQL against this disposable local PostgreSQL service.
    # Production migrations are always gated independently of a code merge.
    conn.execute("""alter table public.factory_change_sets
      add column root_task_id uuid, add column release_run_id uuid,
      add column metadata jsonb not null default '{}'::jsonb""")
    conn.execute("""alter table public.factory_change_set_work_units
      add column updated_at timestamptz default now()""")
    conn.execute("""alter table public.factory_runs
      add column candidate_commit text, add column branch_name text""")
    conn.execute("""create table public.factory_repair_jobs(
      id uuid primary key default gen_random_uuid(),change_set_id uuid,
      work_unit_id uuid,status text,candidate_commit text,
      updated_at timestamptz default now())""")
    legacy_functions=(
      ("factory_complete_change_set_integration","uuid,text,jsonb"),
      ("factory_mark_repair_wave_integrated","uuid,integer,text"),
      ("factory_prepare_change_set_release","uuid,integer,text,integer,text,text"),
    )
    for name,args in legacy_functions:
        conn.execute(f"create function public.{name}({args}) returns jsonb language sql as $ select '{{}}'::jsonb $")
        conn.execute(f"grant execute on function public.{name}({args}) to service_role")
    new_sql=(root/"supabase/migrations/20261018013000_atomic_change_set_integration_epoch_writes.sql").read_text()
    conn.execute(new_sql)
    readiness=conn.execute("select public.factory_integration_epoch_write_readiness()").fetchone()[0]
    assert readiness=={
        "version":1,"atomic_completion":True,"atomic_release":True,"phase_checkpoints":True,
    },readiness
    try:
        with conn.transaction():
            conn.execute("""grant execute on function
              public.factory_complete_change_set_integration(uuid,text,jsonb) to service_role""")
            conn.execute("select public.factory_integration_epoch_write_readiness()")
    except psycopg.Error: pass
    else: raise AssertionError("readiness ignored an unsafe legacy mutation grant")
    for name,args in legacy_functions:
        acl=conn.execute(f"""select
          has_function_privilege('service_role','public.{name}({args})','EXECUTE'),
          has_function_privilege('anon','public.{name}({args})','EXECUTE'),
          has_function_privilege('authenticated','public.{name}({args})','EXECUTE')""").fetchone()
        assert acl==(False,False,False),(name,acl)
    for name,args in (
        ("factory_complete_change_set_integration_epoch","uuid,uuid,bigint,text,integer,text,jsonb"),
        ("factory_prepare_change_set_release_epoch","uuid,uuid,bigint,text,integer,integer,text,integer,text,text"),
    ):
        acl=conn.execute(f"""select
          has_function_privilege('service_role','public.{name}({args})','EXECUTE'),
          has_function_privilege('anon','public.{name}({args})','EXECUTE'),
          has_function_privilege('authenticated','public.{name}({args})','EXECUTE')""").fetchone()
        assert acl==(True,False,False),(name,acl)

    # The previous claim was resumed at generation+1 and still has a live lease.
    latest_epoch=epoch+1
    release_task=conn.execute(
      "insert into public.factory_tasks(project_id,title,status) values (%s,'integration release root','completed') returning id",
      (integration_project,)).fetchone()[0]
    conn.execute("update public.factory_change_sets set root_task_id=%s where id=%s",
      (release_task,change_set))
    work_unit_id=conn.execute(
      "update public.factory_change_set_work_units set task_id=%s where change_set_id=%s returning id",
      (release_task,change_set)).fetchone()[0]
    repair_id=conn.execute("""insert into public.factory_repair_jobs(
      change_set_id,work_unit_id,status,candidate_commit)
      values (%s,%s,'running','candidate') returning id""",
      (change_set,work_unit_id)).fetchone()[0]
    def finish(project=integration_project,generation=latest_epoch,owner="resumed-worker",
               wave=1,candidate="new-sha",paths='["src/a.py"]'):
        return conn.execute("""select public.factory_complete_change_set_integration_epoch(
          %s,%s,%s,%s,%s,%s,%s::jsonb)""",
          (change_set,project,generation,owner,wave,candidate,paths)).fetchone()[0]
    def rejected(callable_,message):
        try:
            with conn.transaction():
                callable_()
        except psycopg.Error:
            return
        raise AssertionError(message)
    rejected(lambda:finish(generation=epoch),"stale completion generation accepted")
    rejected(lambda:finish(owner="stolen-worker"),"stale completion owner accepted")
    rejected(lambda:finish(wave=2),"wrong completion wave accepted")
    rejected(lambda:finish(project=pid),"cross-project completion accepted")
    rejected(lambda:finish(paths='["src/foreign.py"]'),"unproven file change accepted")
    rejected(lambda:finish(paths='["src/a.py","src/a.py"]'),"duplicate file accepted")
    rejected(lambda:finish(paths='[]'),"empty file set accepted")
    rejected(lambda:finish(candidate="candidate"),"unchanged commit accepted")
    conn.execute("update public.factory_change_sets set lease_expires_at=now()-interval '1 second' where id=%s",(change_set,))
    rejected(finish,"expired integration lease accepted")
    conn.execute("update public.factory_change_sets set lease_expires_at=now()+interval '10 minutes' where id=%s",(change_set,))
    assert conn.execute("select status from public.factory_change_sets where id=%s",(change_set,)).fetchone()[0]=="integrating"
    assert conn.execute("select status from public.factory_repair_jobs where id=%s",(repair_id,)).fetchone()[0]=="running"
    result=finish()
    assert result["status"]=="review_ready" and result["repair_jobs_integrated"]==1,result
    assert result["change_set_id"]==str(change_set) and result["current_wave"]==1,result
    assert conn.execute("select status from public.factory_repair_jobs where id=%s",(repair_id,)).fetchone()[0]=="integrated"
    assert conn.execute("select status from public.factory_tasks where id=%s",(release_task,)).fetchone()[0]=="integrated"
    assert conn.execute("select status from public.factory_change_set_work_units where id=%s",(work_unit_id,)).fetchone()[0]=="integrated"
    integration_checkpoint(generation=latest_epoch,owner="resumed-worker")
    integration_checkpoint(generation=latest_epoch,owner="stolen-worker",allowed=False)
    rejected(finish,"replayed integration completion accepted")

    def release(project=integration_project,generation=latest_epoch,owner="resumed-worker",wave=1,
                issue=7,url="https://github.com/owner/repo/issues/7",
                pr=9,candidate="new-sha",branch="factory/integration-qa"):
        return conn.execute("""select public.factory_prepare_change_set_release_epoch(
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
          (change_set,project,generation,owner,wave,issue,url,pr,candidate,branch)).fetchone()[0]
    before_runs=conn.execute("select count(*) from public.factory_runs").fetchone()[0]
    rejected(lambda:release(generation=epoch),"stale release epoch accepted")
    rejected(lambda:release(owner="wrong"),"wrong release owner accepted")
    rejected(lambda:release(wave=2),"wrong release wave accepted")
    rejected(lambda:release(candidate="foreign"),"foreign release SHA accepted")
    rejected(lambda:release(branch="factory/wrong"),"foreign release branch accepted")
    rejected(lambda:release(url="https://github.com/attacker/repo/issues/7"),"foreign release issue accepted")
    rejected(lambda:release(project=pid),"foreign release project accepted")
    assert conn.execute("select count(*) from public.factory_runs").fetchone()[0]==before_runs
    prepared=release()
    assert prepared["status"]=="ci_pending" and prepared["idempotent"] is False,prepared
    assert release()["idempotent"] is True
    assert release()["release_run_id"]==prepared["release_run_id"]
    rejected(lambda:release(pr=10),"conflicting release retry accepted")
    assert conn.execute("select count(*) from public.factory_runs").fetchone()[0]==before_runs+1
    assert conn.execute("select count(*) from public.factory_tool_usage where run_id=%s",
      (prepared["release_run_id"],)).fetchone()[0]==1
    assert conn.execute("select count(*) from public.factory_audit_events where run_id=%s",
      (prepared["release_run_id"],)).fetchone()[0]==1
    integration_checkpoint(generation=latest_epoch,owner="resumed-worker")

    # Operator pause invalidates GitHub writes even after completion and CI registration.
    current_version=conn.execute("select version from public.factory_project_execution_controls where project_id=%s",
      (integration_project,)).fetchone()[0]
    pause_result=conn.execute("select public.factory_control_project_v1(%s,%s,%s,%s,%s)",
      ("integration-epoch-qa","pause",uuid.uuid4(),current_version,actor)).fetchone()[0]
    assert pause_result["state"] in ("pausing","paused"),pause_result
    integration_checkpoint(generation=latest_epoch,owner="resumed-worker",allowed=False)
    rejected(release,"paused project reissued release")
    if pause_result["state"]=="pausing":
        settled=conn.execute("select public.factory_settle_project_control_v1(%s)",
          ("integration-epoch-qa",)).fetchone()[0]
        assert settled["state"]=="paused",settled
    else:
        settled=pause_result
    resumed=conn.execute("select public.factory_control_project_v1(%s,%s,%s,%s,%s)",
      ("integration-epoch-qa","resume",uuid.uuid4(),settled["version"],actor)).fetchone()[0]
    assert resumed["generation"]==latest_epoch+1,resumed
    integration_checkpoint(generation=latest_epoch,owner="resumed-worker",allowed=False)
    rejected(release,"stale release generation after resume accepted")

    # A multi-wave completion must retain the next wave but revoke the old lease.
    future_project=conn.execute("insert into public.factory_projects(project_key,repository) values ('integration-next-qa','owner/repo') returning id").fetchone()[0]
    started_future=conn.execute("select public.factory_control_project_v1(%s,%s,%s,%s,%s)",
      ("integration-next-qa","start",uuid.uuid4(),0,actor)).fetchone()[0]
    future_epoch=started_future["generation"]
    future_set=conn.execute("""insert into public.factory_change_sets(
      project_id,status,source_commit,candidate_commit,integration_branch,current_wave,attempt_count)
      values (%s,'integrating','source','candidate','factory/next-wave-qa',1,1) returning id""",
      (future_project,)).fetchone()[0]
    conn.execute("""update public.factory_change_sets
      set lease_owner='next-worker',lease_expires_at=now()+interval '10 minutes'
      where id=%s""",(future_set,))
    for wave,status,path in ((1,"completed","src/one.py"),(2,"pending","src/two.py")):
        conn.execute("""insert into public.factory_change_set_work_units(
          change_set_id,wave,status,plan_task_key,base_commit,output_commit,changed_files)
          values (%s,%s,%s,%s,'candidate','out',%s::jsonb)""",
          (future_set,wave,f"task-{wave}",'["'+path+'"]'))
    next_result=conn.execute("""select public.factory_complete_change_set_integration_epoch(
      %s,%s,%s,%s,%s,%s,%s::jsonb)""",
      (future_set,future_project,future_epoch,"next-worker",1,"next-sha",'["src/one.py"]')).fetchone()[0]
    assert next_result["status"]=="building" and next_result["current_wave"]==2,next_result
    assert conn.execute("""select attempt_count,lease_owner,metadata?'integration_epoch_receipt'
      from public.factory_change_sets where id=%s""",(future_set,)).fetchone()==(0,None,False)
    print("ATOMIC_INTEGRATION_EPOCH_POSTGRES_PASS=1")


print("PROJECT_MANUAL_CONTROL_POSTGRES_PASS=1")
