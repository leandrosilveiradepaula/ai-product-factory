#!/usr/bin/env python3
"""Isolated PostgreSQL contract for owner-requested blocked-work recovery.

Requires a disposable PostgreSQL database only. No Supabase credentials,
network calls, paid providers, external GitHub writes, or production mutations.
"""
import json
import os
import uuid
import sys
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

dsn = os.environ.get("FACTORY_BLOCKED_RECOVERY_TEST_DSN", "")
cfg = conninfo_to_dict(dsn)
if (os.environ.get("FACTORY_BLOCKED_RECOVERY_TEST_ISOLATED") != "true"
        or cfg.get("host") not in ("127.0.0.1", "localhost")
        or cfg.get("dbname") != "factory_blocked_recovery_test"):
    raise SystemExit("REFUSING_NON_ISOLATED_BLOCKED_RECOVERY_DATABASE")

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from ai_product_factory.runtime_worker import RuntimeWorker, WorkItem, WorkStatus
historical_epoch_sql = (root / "supabase/migrations/20261017111500_factory_manual_project_execution_controls.sql").read_text()
def extract_ddl(text, start_marker, end_marker):
    start=text.index(start_marker)
    return text[start:text.index(end_marker,start)]
epoch_sql=extract_ddl(historical_epoch_sql,
    "create function public.factory_assert_project_execution_epoch(",
    "revoke all on function public.factory_assert_project_execution_epoch")
live_claim_sql=(root / "tests/fixtures/factory_claim_next_run_20261118.sql").read_text()
wake_sql = (root / "supabase/migrations/20261019002000_project_control_wake_outbox.sql").read_text()
recovery_sql = (root / "supabase/migrations/20261118160000_operator_blocked_work_recovery.sql").read_text()
hardening_sql = (root / "supabase/migrations/20261118163000_blocked_recovery_trigger_function_acl.sql").read_text()
schema = """
create role service_role nologin;create role anon nologin;create role authenticated nologin;
create table public.factory_projects(
 id uuid primary key default gen_random_uuid(),project_key text not null unique,
 is_active boolean not null default true,manifest jsonb not null default '{}'::jsonb);
create table public.factory_project_execution_controls(
 project_id uuid primary key references public.factory_projects(id),
 state text not null,version bigint not null,generation bigint not null);
create table public.factory_project_execution_commands(
 project_id uuid references public.factory_projects(id),
 command_id uuid not null,command text not null,expected_version bigint not null,
 actor_id uuid not null,result jsonb not null,primary key(project_id,command_id));
create table public.factory_tasks(
 id uuid primary key default gen_random_uuid(),project_id uuid not null references public.factory_projects(id),
 parent_task_id uuid references public.factory_tasks(id),external_key text,title text not null,
 description text,status text not null,complexity text not null default 'medium',
 risk jsonb not null default '{}'::jsonb,acceptance_criteria jsonb not null default '[]'::jsonb,
 depends_on jsonb not null default '[]'::jsonb,
 created_at timestamptz not null default now(),updated_at timestamptz not null default now());
create table public.factory_runs(
 id uuid primary key default gen_random_uuid(),task_id uuid references public.factory_tasks(id),
 status text not null,execution_route text,source_commit text,candidate_commit text,
 branch_name text,metadata jsonb not null default '{}'::jsonb,
 lease_owner text,lease_expires_at timestamptz,started_at timestamptz,
 created_at timestamptz not null default now());
create table public.factory_change_sets(
 id uuid primary key default gen_random_uuid(),
 project_id uuid references public.factory_projects(id),
 root_task_id uuid references public.factory_tasks(id),
 status text not null,lease_owner text,lease_expires_at timestamptz);
create table public.factory_repair_jobs(
 id uuid primary key default gen_random_uuid(),project_id uuid references public.factory_projects(id),
 task_id uuid references public.factory_tasks(id),source_run_id uuid references public.factory_runs(id),
 change_set_id uuid references public.factory_change_sets(id),status text not null,
 cycle integer not null,max_cycles integer not null,
 updated_at timestamptz not null default now());
create table public.factory_audit_events(
 project_id uuid,task_id uuid,run_id uuid,actor_type text,
 actor_ref text,event_type text,payload jsonb,
 created_at timestamptz not null default now());
"""

def call(db,key,command,version,actor):
    return db.execute(
        "select public.factory_restart_blocked_work_v1(%s,%s,%s,%s)",
        (key,command,version,actor)).fetchone()[0]

def denied(db,key,command,version,actor):
    try:
        with db.transaction():
            call(db,key,command,version,actor)
    except psycopg.Error:
        return
    raise AssertionError("an unsafe restart was unexpectedly accepted")

def fixture(db,key,*,cycle=2,max_cycles=3,broken_context=False):
    pid=db.execute("insert into public.factory_projects(project_key) values (%s) returning id",(key,)).fetchone()[0]
    db.execute("insert into public.factory_project_execution_controls values(%s,'running',3,1)",(pid,))
    root_task=db.execute(
        "insert into public.factory_tasks(project_id,title,status) values(%s,'source','completed') returning id",(pid,)).fetchone()[0]
    src_run=db.execute(
        "insert into public.factory_runs(task_id,status,source_commit) values (%s,'merged',%s) returning id",
        (root_task,"a"*40)).fetchone()[0]
    cs=db.execute("insert into public.factory_change_sets(project_id,root_task_id,status) values(%s,%s,'completed') returning id",(pid,root_task)).fetchone()[0]
    repair_task=db.execute(
        "insert into public.factory_tasks(project_id,parent_task_id,title,status) values(%s,%s,'blocked repair','blocked') returning id",
        (pid,root_task)).fetchone()[0]
    run=db.execute(
        "insert into public.factory_runs(task_id,status,source_commit,metadata) values(%s,'blocked',%s,%s::jsonb) returning id",
        (repair_task,"a"*40,json.dumps({"change_set_id":str(uuid.uuid4()) if broken_context else str(cs)}))).fetchone()[0]
    job=db.execute(
        "insert into public.factory_repair_jobs(project_id,task_id,source_run_id,change_set_id,status,cycle,max_cycles) "
        "values(%s,%s,%s,%s,'blocked',%s,%s) returning id",
        (pid,repair_task,src_run,cs,cycle,max_cycles)).fetchone()[0]
    return {"project":pid,"root_task":root_task,"source_run":src_run,"change_set":cs,
            "repair_task":repair_task,"run":run,"job":job}


class IsolatedWorkerQueue:
    """Actual RuntimeWorker + PostgreSQL claim; test handler is explicitly offline."""
    def __init__(self, db):
        self.db=db

    def claim_next(self, worker_id):
        row=self.db.execute("select public.factory_claim_next_run(%s)",
                            (worker_id,)).fetchone()
        if not row or row[0] is None:
            return None
        c=row[0]
        return WorkItem(run_id=str(c["run_id"]),task_id=str(c["task_id"]),
            project_id=str(c["project_id"]),project_key=str(c["project_key"]),
            stages=tuple(c["stages"]),context=c["context"],
            execution_generation=c["execution_generation"],worker_id=worker_id)

    def assert_execution_epoch(self, item):
        self.db.execute("select public.factory_assert_project_execution_epoch(%s,%s)",
                        (uuid.UUID(item.project_id),item.execution_generation))

    def record_stage(self,item,evidence):
        self.db.execute("update public.factory_runs set metadata=jsonb_set("
            "metadata,array['stage_evidence',%s],%s::jsonb,true) where id=%s",
            (evidence.stage,json.dumps({"status":evidence.status,"output":evidence.output}),
             uuid.UUID(item.run_id)))

    def complete(self,item):
        self.db.execute("update public.factory_runs set status='completed' where id=%s",
                        (uuid.UUID(item.run_id),))
        self.db.execute("update public.factory_tasks set status='completed' where id=%s",
                        (uuid.UUID(item.task_id),))

    def fail(self,item,error):
        self.db.execute("update public.factory_runs set status='failed' where id=%s",
                        (uuid.UUID(item.run_id),))
        self.db.execute("update public.factory_tasks set status='failed' where id=%s",
                        (uuid.UUID(item.task_id),))


class IsolatedStageHandler:
    """Deterministic, no LLM/API/GitHub/network calls. Not product-ready evidence."""
    def __init__(self,fail_at=None):
        self.fail_at=fail_at

    def execute(self,item,stage):
        if stage==self.fail_at:
            raise RuntimeError("isolated_stage_failure")
        return {"stage":stage,"summary":"offline execution verified"}


with psycopg.connect(dsn,autocommit=True) as db:
    db.execute(schema)
    db.execute(wake_sql)
    db.execute(recovery_sql)
    db.execute(hardening_sql)
    db.execute(epoch_sql)
    db.execute(live_claim_sql)
    helper=db.execute("""
      select p.prosecdef,has_function_privilege('service_role',p.oid,'execute'),
             has_function_privilege('anon',p.oid,'execute'),
             has_function_privilege('authenticated',p.oid,'execute')
      from pg_proc p where p.proname='factory_sync_blocked_work_recovery_request'
    """).fetchone()
    assert helper == (False, True, False, False),helper
    # The callable entrypoint and data remain inaccessible to both public roles.
    permissions=db.execute("""
     select p.prosecdef,has_function_privilege('service_role',p.oid,'execute'),
       has_function_privilege('anon',p.oid,'execute'),
       has_function_privilege('authenticated',p.oid,'execute')
     from pg_proc p where p.proname='factory_restart_blocked_work_v1'
    """).fetchone()
    assert permissions==(False,True,False,False),permissions
    rls=db.execute("""
     select c.relrowsecurity,has_table_privilege('anon',c.oid,'select'),
       has_table_privilege('authenticated',c.oid,'select')
     from pg_class c where c.oid='public.factory_blocked_work_recovery_requests'::regclass
    """).fetchone()
    assert rls==(True,False,False),rls
    actor=uuid.uuid4()
    initial=fixture(db,"linked-repair")
    command=uuid.uuid4()
    first=call(db,"linked-repair",command,3,actor)
    assert first["status"]=="queued" and first["idempotent"] is False,first
    assert first["run_id"]!=str(initial["run"])
    linked=db.execute("""
     select t.parent_task_id,t.project_id,t.status,r.metadata,r.status
     from public.factory_tasks t join public.factory_runs r on r.task_id=t.id
     where r.id=%s
    """,(uuid.UUID(first["run_id"]),)).fetchone()
    assert linked[0]==initial["repair_task"] and linked[1]==initial["project"]
    assert linked[2:] and linked[2]=="queued" and linked[4]=="queued"
    assert linked[3]["terminal_change_set_id"]==str(initial["change_set"])
    assert linked[3]["recovery_source_run_id"]==str(initial["run"])
    assert linked[3]["execution_generation"]==1
    assert db.execute(
      "select status from public.factory_change_sets where id=%s",(initial["change_set"],)).fetchone()[0]=="completed"
    assert db.execute(
      "select status from public.factory_repair_jobs where id=%s",(initial["job"],)).fetchone()[0]=="blocked"
    wake=db.execute(
      "select status,generation from public.factory_project_control_wakes where command_id=%s",(command,)).fetchone()
    assert wake==("pending",1),wake
    repeat=call(db,"linked-repair",command,3,actor)
    assert repeat["idempotent"] is True and repeat["run_id"]==first["run_id"]
    denied(db,"linked-repair",command,2,actor)
    denied(db,"linked-repair",command,3,uuid.uuid4())
    denied(db,"linked-repair",uuid.uuid4(),3,actor)
    assert db.execute("select count(*) from public.factory_blocked_work_recovery_requests").fetchone()[0]==1
    assert db.execute("select count(*) from public.factory_project_control_wakes").fetchone()[0]==1
    # Project workers use "running", not only "implementing": the owner
    # state must advance when the real queue claims an item.
    newrun=uuid.UUID(first["run_id"])
    db.execute(
        "update public.factory_runs set status='running',started_at=now(),lease_owner='fixture-worker' where id=%s",
        (newrun,))
    assert db.execute(
        "select status from public.factory_blocked_work_recovery_requests where continuation_run_id=%s",(newrun,)
        ).fetchone()[0]=="recovering"
    db.execute("update public.factory_runs set status='completed' where id=%s",(newrun,))
    assert db.execute(
        "select status from public.factory_blocked_work_recovery_requests where continuation_run_id=%s",(newrun,)
        ).fetchone()[0]=="completed"
    assert call(db,"linked-repair",command,3,actor)["status"]=="completed"
    # A request cannot override paused control, stale version, exhausted cycle,
    # an active worker, or source-run provenance.
    paused=fixture(db,"paused-repair")
    db.execute("update public.factory_project_execution_controls set state='paused' where project_id=%s",(paused["project"],))
    denied(db,"paused-repair",uuid.uuid4(),3,actor)
    stale=fixture(db,"stale-repair")
    denied(db,"stale-repair",uuid.uuid4(),2,actor)
    exhausted=fixture(db,"exhausted",cycle=3,max_cycles=3)
    denied(db,"exhausted",uuid.uuid4(),3,actor)
    tampered=fixture(db,"wrong-source",broken_context=True)
    denied(db,"wrong-source",uuid.uuid4(),3,actor)
    foreign=fixture(db,"foreign-lineage")
    db.execute("update public.factory_change_sets set project_id=%s where id=%s",
               (initial["project"],foreign["change_set"]))
    denied(db,"foreign-lineage",uuid.uuid4(),3,actor)
    busy=fixture(db,"busy")
    active_task=db.execute(
        "insert into public.factory_tasks(project_id,title,status) values(%s,'working','running') returning id",
        (busy["project"],)).fetchone()[0]
    db.execute(
        "insert into public.factory_runs(task_id,status,lease_owner) values (%s,'running','active-worker')",
        (active_task,))
    denied(db,"busy",uuid.uuid4(),3,actor)
    assert db.execute(
        "select count(*) from public.factory_blocked_work_recovery_requests").fetchone()[0]==1
    try:
        with db.transaction():
            db.execute("set local role anon")
            call(db,"linked-repair",uuid.uuid4(),3,actor)
    except psycopg.Error:
        pass
    else:
        raise AssertionError("anon role executed private restart")
    # This proves the genuine Python RuntimeWorker can claim and settle a
    # newly linked continuation against the PostgreSQL function snapshot.
    # It does NOT execute a paid model or prove the live production scheduler.
    historical=fixture(db,"runtime-continues")
    receipt=call(db,"runtime-continues",uuid.uuid4(),3,actor)
    offline=IsolatedWorkerQueue(db)
    result=RuntimeWorker(queue=offline,handler=IsolatedStageHandler(),
                         worker_id="isolated-worker-success").run_once()
    assert result is not None and result.status==WorkStatus.COMPLETED,result
    assert tuple(x.stage for x in result.evidence)==(
       "reconciliation","gap_analysis","planning"),result
    assert db.execute(
       "select status from public.factory_blocked_work_recovery_requests where id=%s",
       (uuid.UUID(receipt["request_id"]),)).fetchone()[0]=="completed"
    assert db.execute("select status from public.factory_repair_jobs where id=%s",
                      (historical["job"],)).fetchone()[0]=="blocked"
    assert db.execute("select status from public.factory_change_sets where id=%s",
                      (historical["change_set"],)).fetchone()[0]=="completed"
    assert offline.claim_next("isolated-worker-repeat") is None

    failing=fixture(db,"runtime-fails")
    denied_command=uuid.uuid4()
    failed_receipt=call(db,"runtime-fails",denied_command,3,actor)
    failure=RuntimeWorker(queue=offline,
       handler=IsolatedStageHandler(fail_at="gap_analysis"),
       worker_id="isolated-worker-failure").run_once()
    assert failure is not None and failure.status==WorkStatus.FAILED,failure
    assert len(failure.evidence)==1
    assert db.execute(
       "select status from public.factory_blocked_work_recovery_requests where id=%s",
       (uuid.UUID(failed_receipt["request_id"]),)).fetchone()[0]=="blocked"

print("BLOCKED_WORK_RECOVERY_POSTGRES_PASS")
