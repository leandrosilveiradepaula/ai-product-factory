#!/usr/bin/env python3
"""Deterministic proof of audited retirement using disposable PostgreSQL 16.

Never connect to Supabase or any remote host. No model, GitHub or billing API.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

dsn = os.getenv("FACTORY_RETIRE_TEST_DSN", "")
config = conninfo_to_dict(dsn)
if (
    os.getenv("FACTORY_RETIRE_TEST_ISOLATED") != "true"
    or config.get("host") not in ("localhost", "127.0.0.1")
    or config.get("dbname") != "factory_retire_test"
    or config.get("user") != "factory_ci"
):
    raise SystemExit("refusing non-isolated retirement database")

root = Path(__file__).resolve().parents[1]
migration = (root / "supabase/migrations/20261019201000_retire_obsolete_factory_artifacts.sql").read_text()
schema = """
create role service_role nologin;
create role anon nologin;
create role authenticated nologin;
create table public.factory_projects(
  id uuid primary key,project_key text unique,project_kind text,
  repository text,is_active boolean,manifest jsonb
);
create table public.factory_project_execution_controls(
  project_id uuid primary key,state text,generation bigint
);
create table public.factory_tasks(
  id uuid primary key,project_id uuid,parent_task_id uuid,status text,
  created_at timestamptz default now(),updated_at timestamptz default now()
);
create table public.factory_runs(
  id uuid primary key,task_id uuid,status text,lease_owner text,
  lease_expires_at timestamptz
);
create table public.factory_human_gates(
  id uuid primary key,run_id uuid,status text
);
create table public.factory_change_sets(
  id uuid primary key,project_id uuid,root_task_id uuid,status text,
  source_commit text,candidate_commit text,current_wave integer,
  release_run_id uuid,lease_owner text,lease_expires_at timestamptz,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now(),updated_at timestamptz default now()
);
create table public.factory_change_set_work_units(
  id uuid primary key,change_set_id uuid,task_id uuid,
  status text,wave integer
);
create table public.factory_audit_events(
  id bigint generated always as identity primary key,
  project_id uuid,task_id uuid,actor_type text,actor_ref text,event_type text,
  payload jsonb,created_at timestamptz default now()
);
create function public.factory_control_quiescent(p_project_id uuid)
returns boolean language sql stable as $$
select not exists(
  select 1 from public.factory_runs r
  join public.factory_tasks t on t.id=r.task_id
  where t.project_id=p_project_id and r.lease_owner is not null
    and (r.lease_expires_at is null or r.lease_expires_at>now())
    and r.status not in ('completed','failed','cancelled')
) and not exists(
  select 1 from public.factory_change_sets cs
  where cs.project_id=p_project_id and cs.lease_owner is not null
    and (cs.lease_expires_at is null or cs.lease_expires_at>now())
);
$$;
"""


def target(sha: str):
    return json.dumps({"delivery_target": {
        "sha": sha,
        "mode": "open_pr_candidate",
        "branch": "preview/candidate",
        "repository": "test/crm",
    }})


with psycopg.connect(dsn, autocommit=True) as db:
    db.execute(schema)
    db.execute(migration)

    role_check = db.execute("""
      select p.prosecdef,
      has_function_privilege('service_role',p.oid,'execute'),
      has_function_privilege('anon',p.oid,'execute'),
      has_function_privilege('authenticated',p.oid,'execute')
      from pg_proc p join pg_namespace n on n.oid=p.pronamespace
      where n.nspname='public'
      and p.proname='factory_retire_obsolete_artifacts_v1'
    """).fetchone()
    assert role_check == (False,True,False,False), role_check

    crm_id, old_sha, pin = uuid.uuid4(), "a"*40, "b"*40
    db.execute("""
      insert into public.factory_projects values
      (%s,'crm','existing','test/crm',true,%s::jsonb)
    """, (crm_id,target(pin)))
    db.execute("""
      insert into public.factory_project_execution_controls values
      (%s,'running',5)
    """, (crm_id,))

    def task(project, state="completed", days=1, parent=None):
        identifier = uuid.uuid4()
        db.execute("""
          insert into public.factory_tasks(
            id,project_id,parent_task_id,status,created_at)
          values (%s,%s,%s,%s,now()-%s*interval '1 day')
        """, (identifier,project,parent,state,days))
        return identifier

    root = task(crm_id,days=2)
    child = task(crm_id,days=1)
    stale_cs, stale_unit = uuid.uuid4(), uuid.uuid4()
    db.execute("""
       insert into public.factory_change_sets(
       id,project_id,root_task_id,status,source_commit,candidate_commit,
       current_wave,created_at)
       values (%s,%s,%s,'building',%s,%s,1,now()-interval '1 day')
    """, (stale_cs,crm_id,root,old_sha,old_sha))
    db.execute("""
       insert into public.factory_change_set_work_units values
       (%s,%s,%s,'completed',1)
    """, (stale_unit,stale_cs,child))

    ghost_root = task(crm_id,days=3)
    ghost_cs = uuid.uuid4()
    db.execute("""
       insert into public.factory_change_sets(
       id,project_id,root_task_id,status,current_wave,created_at)
       values (%s,%s,%s,'review_ready',1,now()-interval '3 days')
    """,(ghost_cs,crm_id,ghost_root))
    legacy_parent = task(crm_id,days=18)
    retired_completed_task = task(crm_id,"queued",days=15,parent=legacy_parent)
    retired_cancelled_task = task(crm_id,"queued",days=15,parent=legacy_parent)
    db.execute("insert into public.factory_runs values (%s,%s,'completed',null,null)",
               (uuid.uuid4(),retired_completed_task))
    # A more recent completed task provides local proof that the historical
    # backlog is not the most recent project work.
    task(crm_id,days=1)

    def retire(project="crm",expected=pin,sets=None,tasks=None,key=None,
               reason="superseded by verified new project context"):
        return db.execute("""
          select public.factory_retire_obsolete_artifacts_v1(
          %s,%s,%s::uuid[],%s::uuid[],%s,%s)
        """, (project,expected,sets or [],tasks or [],key or uuid.uuid4(),reason)).fetchone()[0]

    def reject(**kw):
        try:
            with db.transaction():
                retire(**kw)
        except psycopg.Error:
            return
        raise AssertionError("unsafe retirement was accepted")

    # A newer operator never authorizes an invalid/deceptive candidate.
    reject(expected=old_sha,sets=[stale_cs])
    reject(sets=[stale_cs,stale_cs])
    reject(tasks=[retired_cancelled_task,retired_cancelled_task])
    reject(sets=[uuid.uuid4()])
    reject(tasks=[uuid.uuid4()])
    reject(sets=[stale_cs],reason="short")
    reject(sets=[stale_cs],tasks=[None])
    assert db.execute(
        "select status from factory_change_sets where id=%s",(stale_cs,)
    ).fetchone()[0]=="building"

    # An active lease blocks all cleanup and does not burn a retry.
    db.execute(
        "update factory_change_sets set lease_owner='worker' where id=%s",(stale_cs,)
    )
    reject(sets=[stale_cs])
    db.execute("update factory_change_sets set lease_owner=null where id=%s",
               (stale_cs,))
    # A genuine current-pin change set may not be silently archived.
    db.execute("update factory_change_sets set source_commit=%s where id=%s",
               (pin,stale_cs))
    reject(sets=[stale_cs])
    db.execute("update factory_change_sets set source_commit=%s where id=%s",
               (old_sha,stale_cs))

    # A noncompleted Work Unit prevents retirement even for stale source.
    db.execute("update factory_change_set_work_units set status='queued' where id=%s",
               (stale_unit,))
    reject(sets=[stale_cs])
    db.execute("update factory_change_set_work_units set status='completed' where id=%s",
               (stale_unit,))

    # Active or gate-pending task is never retired.
    active_run=uuid.uuid4()
    db.execute("insert into factory_runs values (%s,%s,'queued',null,null)",
               (active_run,retired_cancelled_task))
    reject(tasks=[retired_cancelled_task])
    db.execute("update factory_runs set status='cancelled' where id=%s",
               (active_run,))
    db.execute("insert into factory_human_gates values (%s,%s,'pending')",
               (uuid.uuid4(),active_run))
    reject(tasks=[retired_cancelled_task])
    db.execute("delete from factory_human_gates where run_id=%s",(active_run,))
    # Disallow retirement of work that is too recent, even if parent completed.
    too_recent=task(crm_id,"queued",days=1,parent=legacy_parent)
    reject(tasks=[too_recent])

    before_counts={
       "sets":db.execute("select count(*) from factory_change_sets").fetchone()[0],
       "units":db.execute("select count(*) from factory_change_set_work_units").fetchone()[0],
       "runs":db.execute("select count(*) from factory_runs").fetchone()[0],
       "tasks":db.execute("select count(*) from factory_tasks").fetchone()[0],
    }
    request_id=uuid.uuid4()
    kwargs=dict(sets=[stale_cs,ghost_cs],
                tasks=[retired_completed_task,retired_cancelled_task],
                key=request_id)
    receipt=retire(**kwargs)
    assert receipt["change_sets_superseded"]==2,receipt
    assert receipt["tasks_completed"]==1,receipt
    assert receipt["tasks_cancelled"]==1,receipt
    assert receipt["expected_pin"]==pin,receipt
    assert db.execute("""
      select id,status from factory_change_sets where id=any(%s) order by id
    """, ([stale_cs,ghost_cs],)).fetchall()==sorted([
        (stale_cs,"superseded"),(ghost_cs,"superseded")],key=lambda r:r[0])
    assert db.execute("""
      select status from factory_change_set_work_units where id=%s
    """,(stale_unit,)).fetchone()==("completed",)
    assert db.execute("""
      select status from factory_tasks where id=%s
    """,(retired_completed_task,)).fetchone()==("completed",)
    assert db.execute("""
      select status from factory_tasks where id=%s
    """,(retired_cancelled_task,)).fetchone()==("cancelled",)
    assert db.execute("""
      select status from factory_runs where task_id=%s
    """,(retired_completed_task,)).fetchone()==("completed",)

    # The request ID is an exact idempotency key with immutable arguments.
    assert retire(**kwargs)==receipt
    reject(sets=[stale_cs],key=request_id)
    assert db.execute("""
      select count(*) from factory_audit_events
      where event_type='project.obsolete_artifacts.retired'
    """).fetchone()[0]==1
    assert db.execute("""
      select count(*) from factory_audit_events
      where event_type='change_set.retired_obsolete'
    """).fetchone()[0]==2
    assert db.execute("""
      select count(*) from factory_audit_events
      where event_type='task.retired_obsolete'
    """).fetchone()[0]==2
    assert before_counts=={
       "sets":db.execute("select count(*) from factory_change_sets").fetchone()[0],
       "units":db.execute("select count(*) from factory_change_set_work_units").fetchone()[0],
       "runs":db.execute("select count(*) from factory_runs").fetchone()[0],
       "tasks":db.execute("select count(*) from factory_tasks").fetchone()[0],
    }, "archival deleted historical evidence"

    # Running-only: paused projects require an explicit human resume.
    platform_id=uuid.uuid4()
    db.execute("""
       insert into factory_projects values
       (%s,'factory','platform',null,true,'{}'::jsonb)
    """,(platform_id,))
    db.execute("insert into factory_project_execution_controls values (%s,'running',1)",
               (platform_id,))
    factory_parent=task(platform_id,days=25)
    factory_legacy=task(platform_id,"queued",days=20,parent=factory_parent)
    task(platform_id,days=1)
    reject(project="factory",expected=pin,tasks=[factory_legacy])
    reject(project="factory",expected="platform:no-pinned-candidate",
           sets=[stale_cs],tasks=[factory_legacy])
    db.execute("update factory_project_execution_controls set state='paused' where project_id=%s",
               (platform_id,))
    reject(project="factory",expected="platform:no-pinned-candidate",
           tasks=[factory_legacy])
    db.execute("update factory_project_execution_controls set state='running' where project_id=%s",
               (platform_id,))
    factory_receipt=retire(project="factory",
                          expected="platform:no-pinned-candidate",
                          tasks=[factory_legacy])
    assert factory_receipt["tasks_cancelled"]==1
    assert db.execute("select status from factory_tasks where id=%s",
                      (factory_legacy,)).fetchone()==("cancelled",)

print("OBSOLETE_FACTORY_ARTIFACT_RETIREMENT_POSTGRES_PASS")
