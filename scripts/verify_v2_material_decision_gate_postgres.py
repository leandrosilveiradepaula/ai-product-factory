"""Adversarial QA for a V2 material-requirement decision gate.

Refuses non-local database connection. Never queries the real Supabase project.
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

DSN = os.environ.get("FACTORY_MATERIAL_GATE_TEST_DSN", "")
from urllib.parse import urlsplit

url = urlsplit(DSN)
if (url.scheme != "postgresql" or url.hostname not in ("localhost", "127.0.0.1")
    or url.port != 5432 or url.path != "/v2_material_gate_test"
    or url.query or url.fragment):
    raise SystemExit("REFUSING_NON_ISOLATED_MATERIAL_GATE_DATABASE")

migration = (
    Path(__file__).resolve().parents[1]
    / "supabase/migrations/20261102165000_v2_material_decision_gate.sql"
).read_text()
P = "11111111-1111-4111-8111-111111111111"
J = "22222222-2222-4222-8222-222222222222"
T = "33333333-3333-4333-8333-333333333333"
RUN = "44444444-4444-4444-8444-444444444444"
CS = "55555555-5555-4555-8555-555555555555"
WU = "66666666-6666-4666-8666-666666666666"
ACTOR = "77777777-7777-4777-8777-777777777777"
SHA = "b1935c8f6e61ae246eb8958673b2a9e18c3da81f"
REASON = "CURRENT_TASK explicitly prohibits visibility change without a human decision."
QUOTE = "Não modificar sem decisão humana explícita a visibilidade de contratos legados sem deal_id."
BINDING = {
    "journey_id": J, "binding_version": 2, "execution_generation": 19,
    "source_commit": SHA, "integration_branch": "factory/journey-" + J,
}
DECISION = {
    "decision_kind": "material_requirement_change",
    "question": "Como tratar a visibilidade dos contratos sem vínculo com negócio?",
    "why_needed": "A regra de produto exige uma escolha humana antes de autorizar a mudança.",
    "governance_path": "docs/codex/CURRENT_TASK.md",
    "governance_quote": QUOTE, "reason": REASON,
}

def open_gate(db, payload=DECISION):
    with db.cursor() as cur:
        cur.execute("select public.factory_open_v2_work_unit_decision_gate(%s,%s)",
                    (RUN, Jsonb(payload)))
        return cur.fetchone()[0]

def resolve(db, gate, status, note, actor=ACTOR):
    with db.cursor() as cur:
        cur.execute("select public.factory_resolve_v2_material_decision_gate(%s,%s,%s,%s)",
                    (gate, status, note, actor))
        return cur.fetchone()[0]

def rejects(db, fun):
    try:
        with db.transaction():
            fun()
    except psycopg.Error:
        return
    raise AssertionError("unsafe state or request was accepted")

with psycopg.connect(DSN, autocommit=True) as db:
    with db.cursor() as cur:
        cur.execute("drop schema public cascade; create schema public;")
        cur.execute("""
          do $$ begin
            if not exists(select 1 from pg_roles where rolname='service_role') then
              create role service_role; end if;
            if not exists(select 1 from pg_roles where rolname='anon') then
              create role anon; end if;
            if not exists(select 1 from pg_roles where rolname='authenticated') then
              create role authenticated; end if;
          end $$;
          create table public.factory_projects(
            id uuid primary key, is_active boolean, manifest jsonb, lifecycle_stage text,
            updated_at timestamptz default now());
          create table public.factory_project_execution_controls(
            project_id uuid, state text, generation bigint, version bigint);
          create table public.factory_journeys(
            id uuid primary key,project_id uuid,state text,execution_generation bigint,
            source_commit text,binding jsonb,candidate_commit text,
            work_unit_output_commit text,preview_merge_sha text,production_release_sha text);
          create table public.factory_tasks(
            id uuid primary key,project_id uuid,journey_id uuid,status text,
            updated_at timestamptz default now());
          create table public.factory_runs(
            id uuid primary key,task_id uuid,journey_id uuid,status text,source_commit text,
            candidate_commit text,metadata jsonb,lease_owner text,last_error text,
            lease_expires_at timestamptz,finished_at timestamptz);
          create table public.factory_change_sets(
            id uuid primary key,project_id uuid,journey_id uuid,status text,source_commit text,
            candidate_commit text,metadata jsonb,current_wave integer,
            lease_owner text,lease_expires_at timestamptz,
            updated_at timestamptz default now());
          create table public.factory_change_set_work_units(
            id uuid primary key,change_set_id uuid,run_id uuid,task_id uuid,
            wave integer,status text,base_commit text,output_commit text,
            updated_at timestamptz default now());
          create table public.factory_console_operators(user_id uuid,role text,is_active boolean);
          create table public.factory_human_gates(
            id uuid primary key default gen_random_uuid(),run_id uuid,
            gate_type text,status text,reasons jsonb,resolution jsonb,
            resolved_at timestamptz,resolved_by text);
          create table public.factory_audit_events(
            id bigint generated always as identity,project_id uuid,task_id uuid,
            run_id uuid,actor_type text,actor_ref text,event_type text,payload jsonb);
          create table public.factory_decisions(
            id uuid default gen_random_uuid(),project_id uuid,task_id uuid,
            decision_type text,question text,decision jsonb,decided_by text);
          create function public.factory_control_quiescent(project_id uuid)
            returns boolean language sql stable security invoker
            set search_path='' as $f$ select true $f$;
          create function public.factory_block_change_set_work_unit(
             p_run_id uuid,p_reason text,p_blocker_type text)
            returns jsonb language sql security invoker set search_path='' as $f$
            select '{}'::jsonb $f$;
        """)
        cur.execute(migration)
        cur.execute("insert into public.factory_projects(id,is_active,manifest) values(%s,true,%s)",
                    (P,Jsonb({"human_decisions":[]})))
        cur.execute("insert into public.factory_project_execution_controls values(%s,'running',19,19)",(P,))
        cur.execute("""insert into public.factory_journeys values
          (%s,%s,'executing',19,%s,%s,null,null,null,null)""",(J,P,SHA,Jsonb(BINDING)))
        cur.execute("insert into public.factory_tasks values(%s,%s,%s,'blocked',now())",(T,P,J))
        cur.execute("""insert into public.factory_runs(
          id,task_id,journey_id,status,source_commit,metadata)
          values(%s,%s,%s,'blocked',%s,%s)""",
          (RUN,T,J,SHA,Jsonb({
            "journey_binding_v2":BINDING,"execution_generation":19,
            "blocker_type":"repository_governance","blocker_reason":REASON,
          })))
        cur.execute("""insert into public.factory_change_sets(
          id,project_id,journey_id,status,source_commit,candidate_commit,
          metadata,current_wave)
          values(%s,%s,%s,'blocked',%s,%s,%s,1)""",
          (CS,P,J,SHA,SHA,Jsonb({"blocker":{
            "type":"repository_governance","reason":REASON,
            "run_id":RUN,"work_unit_id":WU,
          }})))
        cur.execute("""insert into public.factory_change_set_work_units(
          id,change_set_id,run_id,task_id,wave,status,base_commit)
          values(%s,%s,%s,%s,1,'blocked',%s)""",(WU,CS,RUN,T,SHA))
        cur.execute("insert into public.factory_console_operators values(%s,'admin',true)",(ACTOR,))

    rejects(db, lambda: open_gate(db,{**DECISION,"decision_kind":"technical_problem"}))
    rejects(db, lambda: open_gate(db,{**DECISION,"governance_quote":"not verified"}))
    with db.cursor() as cur:
        cur.execute("update public.factory_project_execution_controls set state='paused'")
    rejects(db, lambda: open_gate(db))
    with db.cursor() as cur:
        cur.execute("update public.factory_project_execution_controls set state='running'")

    gate_receipt=open_gate(db)
    assert gate_receipt["status"]=="awaiting_human" and gate_receipt["release_authorized"] is False
    assert gate_receipt["created"] is True
    gate=gate_receipt["gate_id"]
    assert open_gate(db)["gate_id"]==gate and open_gate(db)["created"] is False
    with db.cursor() as cur:
        cur.execute("select count(*) from public.factory_human_gates where status='pending'")
        assert cur.fetchone()[0]==1
        cur.execute("select status from public.factory_runs where id=%s",(RUN,))
        assert cur.fetchone()[0]=="awaiting_human"
        cur.execute("select status from public.factory_tasks where id=%s",(T,))
        assert cur.fetchone()[0]=="awaiting_human"
        cur.execute("select status from public.factory_change_sets where id=%s",(CS,))
        assert cur.fetchone()[0]=="blocked"

    # Neither generic resolution nor fallback blocker may demote a pending gate.
    rejects(db, lambda: db.execute(
        "select public.factory_block_change_set_work_unit(%s,%s,'repository_governance')",
        (RUN,REASON)))
    # The general-purpose resolver must not bypass the Change Set CAS.
    rejects(db, lambda: db.execute(
        "select public.factory_resolve_human_gate(%s,'approved','any-operator','bypass')",
        (gate,)))
    rejects(db, lambda: resolve(db,gate,"approved","short","88888888-8888-4888-8888-888888888888"))
    rejects(db, lambda: resolve(db,gate,"approved",""))
    with db.cursor() as cur:
        cur.execute("update public.factory_project_execution_controls set generation=20")
    rejects(db, lambda: resolve(db,gate,"approved","Preservar somente o escopo do owner"))
    with db.cursor() as cur:
        cur.execute("update public.factory_project_execution_controls set generation=19")
        cur.execute("update public.factory_journeys set source_commit=%s where id=%s",("c"*40,J))
    rejects(db, lambda: resolve(db,gate,"approved","Preservar somente o escopo do owner"))
    with db.cursor() as cur:
        cur.execute("update public.factory_journeys set source_commit=%s where id=%s",(SHA,J))
    answer="Aprovado apenas para contratos com proprietário comprovável; legados sem negócio permanecem restritos a administradores."
    result=resolve(db,gate,"approved",answer)
    assert result["status"]=="resumed" and result["release_authorized"] is False
    assert result["source_commit"]==SHA
    assert resolve(db,gate,"approved",answer)==result
    rejects(db, lambda: resolve(db,gate,"rejected",None))
    with db.cursor() as cur:
        cur.execute("select status,metadata from public.factory_runs where id=%s",(RUN,))
        status,meta=cur.fetchone()
        assert status=="queued" and meta.get("requested_action") is None
        cur.execute("select status from public.factory_tasks where id=%s",(T,))
        assert cur.fetchone()[0]=="queued_execution"
        cur.execute("select status from public.factory_change_set_work_units where id=%s",(WU,))
        assert cur.fetchone()[0]=="queued"
        cur.execute("select status,source_commit,candidate_commit from public.factory_change_sets where id=%s",(CS,))
        assert cur.fetchone()==("building",SHA,SHA)
        cur.execute("select manifest from public.factory_projects where id=%s",(P,))
        decisions=cur.fetchone()[0]["human_decisions"]
        assert len(decisions)==1
        assert decisions[0]["journey_id"]==J and decisions[0]["change_set_id"]==CS
        assert decisions[0]["response"]==answer
        cur.execute("select count(*) from public.factory_audit_events where event_type='journey.v2.material_decision_gate_resolved'")
        assert cur.fetchone()[0]==1
        cur.execute("select count(*) from public.factory_human_gates where run_id=%s",(RUN,))
        assert cur.fetchone()[0]==1

print("V2_MATERIAL_DECISION_GATE_POSTGRES_PASS")
