#!/usr/bin/env python3
"""Isolated PostgreSQL proof: CI follow-up waits cannot exhaust Direct worker slots."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict

DSN = os.environ.get("FACTORY_CI_WAITING_CAPACITY_TEST_DSN", "")
cfg = conninfo_to_dict(DSN)
if (
    os.environ.get("FACTORY_CI_WAITING_CAPACITY_TEST_ISOLATED") != "true"
    or cfg.get("host") not in ("localhost", "127.0.0.1")
    or cfg.get("dbname") != "factory_ci_waiting_capacity_test"
    or cfg.get("user") != "factory_ci"
):
    raise SystemExit("REFUSING_NON_ISOLATED_CI_WAITING_CAPACITY_DATABASE")

migration = (
    Path(__file__).resolve().parents[1] / "supabase/migrations/"
    "20261104014200_portfolio_ci_waiting_capacity.sql"
).read_text()
new_predicate = (
    "r.status in ('queued','implementing','ci_pending',"
    "'specialist_review_pending','preview_ready')"
)
old_predicate = (
    "r.status in ('queued','implementing','ci_pending',"
    "'specialist_review_pending','preview_ready','repair_pending')"
)
assert migration.count(new_predicate) == 1
baseline = migration.replace(new_predicate, old_predicate)
assert "factory_portfolio_candidates" in migration
assert "to service_role" in migration

SCHEMA = """
create role anon nologin;
create role authenticated nologin;
create role service_role nologin;
create table public.factory_projects (
 id uuid primary key, project_key text, is_active boolean
);
create table public.factory_project_scheduling (
 project_id uuid primary key, priority text, deadline timestamptz,
 customer_impact integer, max_active_workers integer, paused boolean
);
create table public.factory_incidents (
 id uuid primary key, project_id uuid, severity text, status text
);
create table public.factory_project_execution_controls (
 project_id uuid primary key, state text, generation integer
);
create table public.factory_tasks (
 id uuid primary key, project_id uuid, status text
);
create table public.factory_runs (
 id uuid primary key, task_id uuid, status text, metadata jsonb
);
create table public.factory_execution_team_plans (
 id uuid primary key, project_id uuid, version integer, status text
);
create table public.factory_change_sets (
 id uuid primary key, project_id uuid, team_plan_id uuid,
 status text, current_wave integer
);
create table public.factory_change_set_work_units (
 id uuid primary key, change_set_id uuid, task_id uuid, status text,
 wave integer
);
"""

def ids(db):
    return [str(r["project_id"]) for r in db.execute(
        "select jsonb_array_elements(public.factory_portfolio_candidates(20)) as item"
    ).fetchall() for r in [r] if False]

with psycopg.connect(DSN, autocommit=True) as db:
    db.execute(SCHEMA)
    db.execute(baseline)
    p, q, paused, badplan, wave, incident = (uuid4() for _ in range(6))
    keys = {
        p: "crm-waiting", q: "busy-workers", paused: "paused",
        badplan: "stale-plan", wave: "wrong-wave", incident: "incident-p0",
    }
    tasks = {}
    for project, key in keys.items():
        db.execute("insert into factory_projects values (%s,%s,true)", (project,key))
        db.execute("insert into factory_project_execution_controls values (%s,'running',19)",(project,))
        db.execute(
            "insert into factory_project_scheduling values (%s,'P2',null,1,4,%s)",
            (project,project==paused),
        )
        task, plan, change_set, unit = (uuid4() for _ in range(4))
        tasks[project] = task
        db.execute("insert into factory_tasks values (%s,%s,'queued')",(task,project))
        db.execute(
            "insert into factory_execution_team_plans values (%s,%s,19,%s)",
            (plan,project,"superseded" if project==badplan else "ready"),
        )
        db.execute("insert into factory_change_sets values (%s,%s,%s,'building',3)",
                   (change_set,project,plan))
        db.execute(
            "insert into factory_change_set_work_units values (%s,%s,%s,'pending',%s)",
            (unit,change_set,task,2 if project==wave else 3),
        )
    for project,status,n in ((p,"repair_pending",4),(q,"implementing",4)):
        active_task=uuid4()
        db.execute("insert into factory_tasks values (%s,%s,'completed')",(active_task,project))
        for _ in range(n):
            db.execute(
                "insert into factory_runs values (%s,%s,%s,'{}'::jsonb)",
                (uuid4(),active_task,status),
            )

    def candidates():
        value=db.execute("select public.factory_portfolio_candidates(20)").fetchone()[0]
        assert isinstance(value,list),value
        return {item["project_key"]:item for item in value}

    assert candidates()=={}, "legacy predicate must reproduce stalled pilot"
    db.execute(migration)
    acl=db.execute("""
        select prosecdef,
          has_function_privilege('service_role',oid,'execute'),
          has_function_privilege('anon',oid,'execute'),
          has_function_privilege('authenticated',oid,'execute')
        from pg_proc where proname='factory_portfolio_candidates'
    """).fetchone()
    assert acl==(False,True,False,False),acl
    result=candidates()
    assert set(result)=={"crm-waiting","incident-p0"},result
    assert result["crm-waiting"]["active_runs"]==0,result
    assert result["crm-waiting"]["max_active_workers"]==4,result
    assert "busy-workers" not in result
    assert "paused" not in result
    assert "stale-plan" not in result
    assert "wrong-wave" not in result

    # Worker slots still count all runnable/active execution states.
    db.execute(
        "update factory_runs set status='implementing' "
        "where task_id=(select id from factory_tasks "
        "where project_id=%s and status='completed' limit 1)",
        (p,),
    )
    assert "crm-waiting" not in candidates(), "four active workers must still block"
    db.execute(
        "update factory_runs set status='repair_pending' "
        "where task_id=(select id from factory_tasks "
        "where project_id=%s and status='completed' limit 1)",
        (p,),
    )

    # Explicit P0 preemption is preserved.
    db.execute("insert into factory_incidents values (%s,%s,'P0','open')",(uuid4(),incident))
    assert set(candidates())=={"incident-p0"}, "P0 must preempt normal work"

    # Incident resolved: CRM regains slot, but workflow state still governs dispatch.
    db.execute("update factory_incidents set status='resolved' where project_id=%s",(incident,))
    assert "crm-waiting" in candidates()
    db.execute(
        "update factory_change_set_work_units set status='blocked' "
        "where task_id=%s",(tasks[p],),
    )
    assert "crm-waiting" not in candidates(),"blocked unit must never dispatch"
    print("PORTFOLIO_CI_WAITING_CAPACITY_QA=PASS")
    print("WAITING_RUNS=4 WORKER_SLOTS_RELEASED=4 ACTIVE_WORKER_LIMIT_PRESERVED=true")
    print("PAUSE_PLAN_WAVE_INCIDENT_AND_WORK_UNIT_GATES=PASS")
