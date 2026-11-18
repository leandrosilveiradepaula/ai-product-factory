#!/usr/bin/env python3
"""Run SQL recovery regression on disposable localhost PostgreSQL only; no model/network."""
from __future__ import annotations
import json
import os
import uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

DSN = os.getenv("FACTORY_UX1506_PG_TEST_DSN", "")
cfg = conninfo_to_dict(DSN)
if (os.getenv("FACTORY_UX1506_PG_TEST_ISOLATED") != "true"
    or cfg.get("host") not in ("127.0.0.1", "localhost")
    or cfg.get("dbname") != "factory_ux1506_checkpoint_test"
    or cfg.get("user") != "factory_ci"):
    raise SystemExit("refusing non-isolated UX1506 checkpoint database")

migration = (Path(__file__).resolve().parents[1] /
    "supabase/migrations/20261118005000_platform_empty_planning_checkpoint_recovery.sql"
).read_text(encoding="utf-8")

setup = """
create role service_role nologin;
create role anon nologin;
create role authenticated nologin;
create table public.factory_projects(
 id uuid primary key, project_key text, project_kind text, is_active boolean,
 manifest jsonb);
create table public.factory_tasks(
 id uuid primary key, project_id uuid, parent_task_id uuid, status text,
 created_at timestamptz default now(), updated_at timestamptz default now());
create table public.factory_runs(
 id uuid primary key default gen_random_uuid(), task_id uuid, status text,
 execution_route text, metadata jsonb, created_at timestamptz default now());
create table public.factory_project_execution_controls(
 project_id uuid primary key, state text, generation bigint);
create table public.factory_project_state_snapshots(
 id uuid primary key, project_id uuid, run_id uuid, observed_stage text,
 summary text, evidence jsonb, gaps jsonb, constraints jsonb,
 source_status jsonb, created_at timestamptz default now());
create table public.factory_audit_events(
 id bigint generated always as identity primary key, project_id uuid,
 task_id uuid, run_id uuid, actor_type text, actor_ref text,
 event_type text, payload jsonb, created_at timestamptz default now());
"""

def rpc(db, run_id, actor=256917842):
    return db.execute(
        "select public.factory_resume_failed_product_planning_v1(%s,%s,%s,%s,%s)",
        (run_id, 987654, 1055, actor, "leandrosilveiradepaula"),
    ).fetchone()[0]

def expected_denial(db, run_id, label, actor=256917842):
    try:
        rpc(db, run_id, actor)
    except psycopg.Error as exc:
        assert exc.sqlstate in ("PT409", "PT403"), (label, exc.sqlstate)
        return
    raise AssertionError("unexpected recovery grant: " + label)

def fixture(db, *, project_kind="platform", error="planning has no actionable tasks or decisions",
            reason="planning_non_actionable", source="factory-console", state="running",
            generation=1, role_status="completed", request_mismatch=False):
    db.execute("truncate table public.factory_audit_events, public.factory_runs, "
               "public.factory_project_state_snapshots, public.factory_tasks, "
               "public.factory_project_execution_controls, public.factory_projects")
    project,task,run,snapshot,request=[uuid.uuid4() for _ in range(5)]
    brief={"summary":"Executar a demanda UX/UI #1506. Relatorio e plano."}
    gap={"gaps":[{"code":"ux_not_audited"}],
         "recommended_next_work":[{"work":"inspect current issue and Console"}],
         "_evidence":{"role":"primary","provider_ref":"source-stage"}}
    manifest={"continuation_request":{"id":str(request),"source":source,**brief},
              "gap_analysis":gap}
    source_md={
        "source":source,"stages":["reconciliation","gap_analysis","planning"],
        "error":error,"execution_generation":generation,
        "continuation_request_id":str(uuid.uuid4()) if request_mismatch else str(request),
        "continuation_request":brief,
        "stage_evidence":{
           "reconciliation":{"status":"completed","output":{"summary":"real"}} ,
           "gap_analysis":{"status":role_status,"output":gap},
           "planning":{"status":"failed","output":{
               "reason_code":reason,"observed_model_response":True,
               "assessed_commit":"a"*40,"tasks_count":0,"decisions_count":0,
               "implementation_completed":False,"requires_scope_reconciliation":True,
           }}
        }
    }
    db.execute("insert into public.factory_projects(id,project_key,project_kind,is_active,manifest) "
               "values(%s,'ai-product-factory',%s,true,%s::jsonb)",
               (project,project_kind,json.dumps(manifest)))
    db.execute("insert into public.factory_project_execution_controls values(%s,%s,1)",
               (project,state))
    db.execute("insert into public.factory_tasks(id,project_id,status) values(%s,%s,'failed')",
               (task,project))
    db.execute("insert into public.factory_runs(id,task_id,status,execution_route,metadata) "
               "values(%s,%s,'failed','direct',%s::jsonb)",(run,task,json.dumps(source_md)))
    db.execute("insert into public.factory_project_state_snapshots "
               "(id,project_id,run_id,observed_stage,summary,evidence,gaps,constraints,source_status) "
               "values(%s,%s,%s,'reconciliation','valid source snapshot','[{\\"kind\\":\\"source\\"}]'::jsonb,"
               "'[]'::jsonb,'[]'::jsonb,'{}'::jsonb)",(snapshot,project,run))
    def event(kind,payload):
        db.execute("insert into public.factory_audit_events(project_id,task_id,run_id,"
                   "actor_type,actor_ref,event_type,payload) "
                   "values(%s,%s,%s,'system','test',%s,%s::jsonb)",
                   (project,task,run,kind,json.dumps(payload)))
    event("run.stage.recorded",{"stage":"reconciliation","status":"completed"})
    event("product.stage.persisted",{"stage":"reconciliation","snapshot_id":str(snapshot)})
    event("run.stage.recorded",{"stage":"gap_analysis","status":"completed"})
    event("product.stage.persisted",{"stage":"gap_analysis"})
    event("run.stage.recorded",{"stage":"planning","status":"failed"})
    return run,task

with psycopg.connect(DSN,autocommit=True) as db:
    db.execute(setup)
    db.execute(migration)
    permissions=db.execute("""
      select p.prosecdef,
        has_function_privilege('service_role',p.oid,'EXECUTE'),
        has_function_privilege('anon',p.oid,'EXECUTE'),
        has_function_privilege('authenticated',p.oid,'EXECUTE')
      from pg_proc p where p.proname='factory_resume_failed_product_planning_v1'
    """).fetchone()
    assert permissions==(False,True,False,False),permissions

    source,task=fixture(db)
    once=rpc(db,source)
    assert once["created"] is True and once["stages"]==["planning"],once
    retry=rpc(db,source)
    assert retry["created"] is False and retry["run_id"]==once["run_id"],retry
    row=db.execute("select metadata->'resume_checkpoint',status from public.factory_runs "
                   "where id=%s",(once["run_id"],)).fetchone()
    proof=row[0]
    assert proof["source_failure"]=="planning_non_actionable",proof
    assert proof["source_commit"]=="a"*40,proof
    assert row[1]=="queued"
    assert db.execute("select status from public.factory_tasks where id=%s",(task,)).fetchone()[0]=="queued"
    assert db.execute("select count(*) from public.factory_runs").fetchone()[0]==2

    for label,kwargs in (
        ("existing_kind",{"project_kind":"existing"}),
        ("wrong_error",{"error":"other"}),
        ("wrong_receipt",{"reason":"not_executed"}),
        ("paused",{"state":"paused"}),
        ("stale_epoch",{"generation":2}),
        ("broken_gap",{"role_status":"failed"}),
        ("drifted_request",{"request_mismatch":True}),
    ):
        src,_=fixture(db,**kwargs)
        expected_denial(db,src,label)
        assert db.execute("select count(*) from public.factory_runs").fetchone()[0]==1,label

    src,_=fixture(db)
    expected_denial(db,src,"not_owner",actor=99)
    assert db.execute("select count(*) from public.factory_runs").fetchone()[0]==1

    # Legacy budget checkpoint continues to be admitted without forged empty proof.
    src,_=fixture(db,project_kind="existing",
                  error="reserved provider cost exceeds remaining budget")
    legacy=rpc(db,src)
    assert legacy["created"] is True and legacy["stages"]==["planning"],legacy
    assert legacy["run_id"] is not None

print(json.dumps({"status":"PASS","pg":"disposable","cases":10,
                  "paid_model_calls":0,"production_writes":0}))
