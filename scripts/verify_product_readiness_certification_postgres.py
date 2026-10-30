#!/usr/bin/env python3
"""Disposable PostgreSQL proof for durable product-readiness certification.

Requires a dedicated local database.  It intentionally never contacts GitHub,
Supabase, a model, or a production database.
"""
import json, os, threading
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict

dsn=os.environ.get("FACTORY_PRODUCT_READINESS_TEST_DSN","")
info=conninfo_to_dict(dsn)
if (os.environ.get("FACTORY_PRODUCT_READINESS_TEST_ISOLATED")!="true" or
    info.get("host") not in ("127.0.0.1","localhost") or
    info.get("dbname")!="factory_product_readiness_test"):
    raise SystemExit("REFUSING_NON_ISOLATED_PRODUCT_READINESS_DATABASE")

root=Path(__file__).resolve().parents[1]
migration=(root/"supabase/migrations/20261030110000_product_readiness_certification.sql").read_text()
schema="""
create extension if not exists pgcrypto;
do $$ begin
 if not exists(select 1 from pg_roles where rolname='service_role') then create role service_role; end if;
 if not exists(select 1 from pg_roles where rolname='anon') then create role anon; end if;
 if not exists(select 1 from pg_roles where rolname='authenticated') then create role authenticated; end if;
end $$;
create table public.factory_projects(id uuid primary key default gen_random_uuid(),project_key text unique not null,name text not null default 'x',repository text,project_kind text not null default 'platform',lifecycle_stage text not null default 'operations',manifest jsonb not null default '{}'::jsonb,is_active boolean not null default true);
create table public.factory_tasks(id uuid primary key default gen_random_uuid(),project_id uuid not null references public.factory_projects(id),external_key text,title text not null,description text,status text not null,complexity text not null,risk jsonb not null default '{}'::jsonb,acceptance_criteria jsonb not null default '[]'::jsonb,depends_on jsonb not null default '[]'::jsonb,updated_at timestamptz not null default now());
create table public.factory_runs(id uuid primary key default gen_random_uuid(),task_id uuid not null references public.factory_tasks(id),status text not null,execution_route text,source_commit text,candidate_commit text,metadata jsonb not null default '{}'::jsonb,started_at timestamptz,finished_at timestamptz);
create table public.factory_evaluations(id uuid primary key default gen_random_uuid(),run_id uuid not null references public.factory_runs(id),eval_type text not null,status text not null,score numeric,baseline_ref text,result jsonb not null default '{}'::jsonb);
create table public.factory_audit_events(id bigint generated always as identity primary key,project_id uuid,task_id uuid,run_id uuid,actor_type text not null,actor_ref text,event_type text not null,payload jsonb not null default '{}'::jsonb);
"""
sha="a"*40; digest="b"*64
domains={d:{"status":"failed","reason":"blocked","evidence":["sha:"+sha],"coverage":[],"verification_state":""} for d in ("security","observability_operations","test_strategy","product_experience","documentation","functional_completeness")}
result={"assessed_commit":sha,"assessment_ref":"product-readiness-certifier:"+digest,"ready":False,"status":"not_ready","domains":domains,"blockers":["evidence absent"]}
report={"criteria":{d:{} for d in domains},"assessment":result}

with psycopg.connect(dsn,autocommit=True) as conn:
    conn.execute("drop schema public cascade; create schema public; grant all on schema public to public")
    conn.execute(schema); conn.execute(migration)
    # Privileged test caller and Supabase-like service role are distinct.
    # Exercise the migration's ACL contract, not only a superuser happy path.
    conn.execute("grant usage on schema public to anon,authenticated,service_role")
    conn.execute("grant select,insert,update,delete on all tables in schema public to service_role")
    conn.execute("grant usage,select on all sequences in schema public to service_role")
    for fn in (
        "factory_begin_product_readiness_certification_v1(text,text,text,text)",
        "factory_persist_product_readiness_certification_v1(uuid,uuid,text,text,jsonb,jsonb)",
    ):
        for role in ("anon","authenticated"):
            assert not conn.execute(
                "select has_function_privilege(%s,%s,'EXECUTE')",(role,"public."+fn)
            ).fetchone()[0],(fn,role)
        assert conn.execute(
            "select has_function_privilege('service_role',%s,'EXECUTE')",("public."+fn,)
        ).fetchone()[0],fn
    security=conn.execute(
        "select relrowsecurity from pg_class where oid='public.factory_product_readiness_certifications'::regclass"
    ).fetchone()[0]
    assert security is True
    assert conn.execute(
        "select count(*) from pg_policies where schemaname='public' "
        "and tablename='factory_product_readiness_certifications'"
    ).fetchone()[0]==0
    project=conn.execute("insert into public.factory_projects(project_key,repository) values('factory','owner/repo') returning id").fetchone()[0]
    def begin(connection, evidence_digest=digest):
        return connection.execute("select public.factory_begin_product_readiness_certification_v1(%s,%s,%s,%s)",("factory","owner/repo",sha,evidence_digest)).fetchone()[0]
    one=begin(conn); two=begin(conn)
    assert one["run_id"]==two["run_id"] and two["idempotent"] is True
    run=one["run_id"]
    # A crash after reservation must not leave a root task/run that blocks
    # human-authorized continuation of the same Factory/CRM project.
    assert one["state"]=="collecting"
    assert conn.execute("select count(*) from public.factory_tasks").fetchone()[0]==0
    assert conn.execute("select count(*) from public.factory_runs").fetchone()[0]==0
    saved=conn.execute("select public.factory_persist_product_readiness_certification_v1(%s,%s,%s,%s,%s::jsonb,%s::jsonb)",(one["certification_id"],run,sha,digest,json.dumps(result),json.dumps(report))).fetchone()[0]
    replay=conn.execute("select public.factory_persist_product_readiness_certification_v1(%s,%s,%s,%s,%s::jsonb,%s::jsonb)",(one["certification_id"],run,sha,digest,json.dumps(result),json.dumps(report))).fetchone()[0]
    assert saved["evaluation_status"]=="failed" and replay["idempotent"] is True
    assert conn.execute("select count(*) from public.factory_evaluations where run_id=%s",(run,)).fetchone()[0]==1
    assert conn.execute("select count(*) from public.factory_tasks where status<>'completed'").fetchone()[0]==0
    assert conn.execute("select count(*) from public.factory_runs where status<>'completed'").fetchone()[0]==0
    # Wrong SHA, run and cross-project persistence are all rejected.
    for args in ((one["certification_id"],run,"c"*40,digest), (one["certification_id"],"00000000-0000-0000-0000-000000000000",sha,digest)):
        try: conn.execute("select public.factory_persist_product_readiness_certification_v1(%s,%s,%s,%s,%s::jsonb,%s::jsonb)",(*args,json.dumps(result),json.dumps(report)))
        except psycopg.Error: pass
        else: raise AssertionError("mismatched persistence was accepted")
    # Distinct evidence is a new assessment; two concurrent callers of the
    # same digest converge to one durable run through the uniqueness boundary.
    second="d"*64
    a=begin(conn,second)
    outcomes=[]
    def concurrent_begin():
        with psycopg.connect(dsn,autocommit=True) as c: outcomes.append(begin(c,second)["run_id"])
    threads=[threading.Thread(target=concurrent_begin) for _ in range(2)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert outcomes==[a["run_id"],a["run_id"]]
    # A newer independent assessment on the SAME SHA may supersede a prior
    # failed report. History remains immutable and the current pointer unique.
    newer=dict(result)
    newer["assessment_ref"]="product-readiness-certifier:"+second
    newer["blockers"]=["new independent evidence remains incomplete"]
    newer_report={"criteria":{d:{} for d in domains},"assessment":newer}
    persisted=conn.execute(
        "select public.factory_persist_product_readiness_certification_v1(%s,%s,%s,%s,%s::jsonb,%s::jsonb)",
        (a["certification_id"],a["run_id"],sha,second,json.dumps(newer),json.dumps(newer_report))
    ).fetchone()[0]
    assert persisted["evaluation_status"]=="failed"
    pointers=conn.execute(
        "select evidence_digest,is_current from public.factory_product_readiness_certifications "
        "where project_id=%s and assessed_commit=%s order by evidence_digest",(project,sha)
    ).fetchall()
    assert pointers==[(digest,False),(second,True)],pointers
    assert conn.execute("select count(*) from public.factory_evaluations where baseline_ref=%s",(sha,)).fetchone()[0]==2
    assert conn.execute("select count(*) from public.factory_tasks where status<>'completed'").fetchone()[0]==0
    assert conn.execute("select count(*) from public.factory_runs where status<>'completed'").fetchone()[0]==0
    # Begin/persist RPCs can also be invoked as the intended service_role
    # after the migration, with no public policy. Normal users cannot.
    conn.execute("alter role service_role bypassrls")
    conn.execute("set role service_role")
    try:
        svc=begin(conn,second)
        assert svc["run_id"]==a["run_id"] and svc["idempotent"] is True
    finally:
        conn.execute("reset role")
    # Reject contradictory replay without destroying the authoritative row.
    try:
        conn.execute("select public.factory_persist_product_readiness_certification_v1(%s,%s,%s,%s,%s::jsonb,%s::jsonb)",
           (a["certification_id"],a["run_id"],sha,second,json.dumps(newer),json.dumps(report)))
    except psycopg.Error:
        pass
    else:
        raise AssertionError("contradictory persisted report replay was accepted")
    print("PRODUCT_READINESS_CERTIFICATION_POSTGRES_OK")
