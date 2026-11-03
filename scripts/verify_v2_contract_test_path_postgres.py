"""Test the exact, one-time CRM #209 test-path amendment on isolated PostgreSQL."""
from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit
import psycopg
from psycopg.types.json import Jsonb

dsn = os.environ.get("FACTORY_V2_TEST_PATH_QA_DSN", "")
u = urlsplit(dsn)
if (u.scheme != "postgresql" or u.hostname not in ("localhost","127.0.0.1")
        or u.port != 5432 or u.path != "/v2_contract_test_path_qa" or u.query or u.fragment):
    raise SystemExit("REFUSING_NON_DISPOSABLE_POSTGRES")

sql=(Path(__file__).resolve().parents[1]
    /"supabase/migrations/20261103042000_v2_approved_contract_test_path.sql").read_text()
project="2d30e00a-ff72-4044-b838-011c263ed672"
journey="bb14e150-2c7e-423b-8e5d-e211dab6225c"
run="b11daad8-dfc2-4a42-ba4a-a98e0d529238"
task="c4ba95ac-9d09-4665-ad53-1efa1090ee38"
cs="3f09952e-0384-46ee-97aa-a46c89346678"
unit="179b34b0-e8f2-4055-bd28-7c7a89de3fc0"
plan="9be36fa0-c688-4816-85d3-b114b79727fd"
gate="edbee01d-1d23-4e6b-a7a0-0b5a562183d4"
sha="b1935c8f6e61ae246eb8958673b2a9e18c3da81f"
factory="2ae9f7d40df57fcd4700bff690ed5a9ae75e445f"
branch="factory/cs-3f09952e/issue209-contracts-isolated-read"
old_path="src/services/ContractService.test.ts"
new_path="test/contract-access.test.ts"
scopes=["src/services/ContractService.ts","contract-query-call-sites",old_path,
        "src/app/(dashboard)/contracts/actions.ts"]
context=["src/services/ContractService.ts","src/app/(dashboard)/contracts/actions.ts"]
old_rule=(old_path+" contém testes determinísticos e isolados de serviços remotos para leitura "
    "autorizada, isolamento entre organizações, isolamento entre proprietários quando aplicável "
    "ao modelo verificado, contratos sem deal quando aplicável, ordenação com empates, paginação "
    "global sem duplicatas, cenário aplicável acima de 1.000 itens ou vínculos e erro de "
    "consulta sem sucesso parcial.")
criteria=["Critério existente "+str(i) for i in range(14)]
criteria[12]=old_rule
tick=chr(96)
failure=("Bloqueado: os critérios obrigatórios exigem "+tick+old_path+tick+
    ", mas o "+tick+"CURRENT_TASK.md"+tick+" autoriza testes somente em "+
    tick+"test/*contract*.test.ts"+tick+" ou "+tick+"tests/*contract*.test.ts"+tick+
    ", e esses caminhos não estão em "+tick+"repository.write_scopes"+tick+
    ". Não é possível implementar e validar integralmente a tarefa sem uma decisão humana "
    "que alinhe os escopos.")
binding={"source_commit":sha,"execution_generation":19,"project_id":project,"journey_id":journey}

def call(db,uid=run,workflow=41570692508,failed_sha=factory,work_sha=sha):
    with db.cursor() as cur:
        cur.execute("select public.factory_approve_v2_contract_test_path_once(%s,%s,%s,%s)",
                    (uid,workflow,failed_sha,work_sha))
        return cur.fetchone()[0]

def must_reject(db,action):
    try:
        with db.transaction():
            action()
    except psycopg.Error:
        return
    raise AssertionError("unauthorized test-path amendment accepted")

with psycopg.connect(dsn,autocommit=True) as db:
    with db.cursor() as cur:
        cur.execute("drop schema public cascade; create schema public")
        cur.execute("""
          do $$ begin
            if not exists(select 1 from pg_roles where rolname='service_role') then create role service_role; end if;
            if not exists(select 1 from pg_roles where rolname='anon') then create role anon; end if;
            if not exists(select 1 from pg_roles where rolname='authenticated') then create role authenticated; end if;
          end $$;
          create table public.factory_projects(id uuid primary key,is_active boolean,repository text);
          create table public.factory_project_execution_controls(project_id uuid,state text,generation bigint);
          create table public.factory_journeys(id uuid primary key,project_id uuid,state text,
            execution_generation bigint,source_commit text,binding jsonb,candidate_commit text,
            work_unit_output_commit text,preview_merge_sha text,production_release_sha text);
          create table public.factory_tasks(id uuid primary key,project_id uuid,journey_id uuid,status text,
            scope_keys jsonb,acceptance_criteria jsonb,updated_at timestamptz);
          create table public.factory_runs(id uuid primary key,task_id uuid,journey_id uuid,status text,
            execution_route text,source_commit text,attempt_count integer,lease_owner text,
            lease_expires_at timestamptz,last_error text,finished_at timestamptz,metadata jsonb);
          create table public.factory_change_sets(id uuid primary key,project_id uuid,
            journey_id uuid,team_plan_id uuid,status text,metadata jsonb,source_commit text,
            candidate_commit text,release_run_id uuid,lease_owner text,
            lease_expires_at timestamptz,updated_at timestamptz);
          create table public.factory_change_set_work_units(id uuid primary key,change_set_id uuid,
            task_id uuid,status text,branch_name text,base_commit text,output_commit text,
            changed_files jsonb,updated_at timestamptz);
          create table public.factory_execution_team_plans(id uuid primary key,project_id uuid,
            status text,version integer,plan jsonb);
          create table public.factory_human_gates(id uuid primary key,run_id uuid,status text,
            gate_type text,resolved_at timestamptz,resolution jsonb);
          create table public.factory_tool_usage(id bigint generated always as identity,
            run_id uuid,created_at timestamptz,tool_family text,operation text,estimated_cost numeric);
          create table public.factory_run_agent_assignments(run_id uuid,status text);
          create table public.factory_agent_scope_locks(run_id uuid,released_at timestamptz,
            lease_expires_at timestamptz);
          create table public.factory_audit_events(id bigint generated always as identity,
            project_id uuid,task_id uuid,run_id uuid,actor_type text,actor_ref text,
            event_type text,payload jsonb,created_at timestamptz default now());
        """)
        cur.execute(sql)
        cur.execute("insert into public.factory_projects values(%s,true,%s)",
            (project,"leandrosilveiradepaula/crm-infodive"))
        cur.execute("insert into public.factory_project_execution_controls values(%s,'running',19)",(project,))
        cur.execute("insert into public.factory_journeys values(%s,%s,'executing',19,%s,%s,null,null,null,null)",
            (journey,project,sha,Jsonb(binding)))
        cur.execute("insert into public.factory_tasks values(%s,%s,%s,'blocked',%s,%s,now())",
            (task,project,journey,Jsonb(scopes),Jsonb(criteria)))
        cur.execute("insert into public.factory_runs values(%s,%s,%s,'blocked','direct',%s,6,null,null,%s,now(),%s)",
            (run,task,journey,sha,failure,Jsonb({
                "journey_binding_v2":binding,"execution_generation":19,
                "decision_gate_resolution":"approved",
                "v2_single_caller_scope_approved_once":"v2-owner-approved-single-actions-scope-41558099308-v1",
            })))
        cur.execute("insert into public.factory_change_sets values(%s,%s,%s,%s,'blocked',%s,%s,%s,null,null,null,now())",
            (cs,project,journey,plan,Jsonb({"blocker":{
                "type":"repository_governance","run_id":run,
                "work_unit_id":unit,"reason":failure}}),sha,sha))
        cur.execute("insert into public.factory_change_set_work_units values(%s,%s,%s,'blocked',%s,%s,null,'[]'::jsonb,now())",
            (unit,cs,task,branch,sha))
        cur.execute("insert into public.factory_execution_team_plans values(%s,%s,'ready',19,%s)",
            (plan,project,Jsonb({
                "task_assignments":[{"task_key":"issue209-contracts-isolated-read",
                    "scope_keys":scopes,"context_paths":context}],
                "operator_scope_amendment":{
                    "added_exact_write_path":"src/app/(dashboard)/contracts/actions.ts",
                    "approval_reference":"operator-explicit-approval-2026-11-03T01:18:12Z"},
            })))
        cur.execute("insert into public.factory_human_gates values(%s,%s,'approved','material_requirement_change',now(),%s)",
            (gate,run,Jsonb({"resolution":"approved"})))
        cur.execute("""insert into public.factory_audit_events(
          project_id,task_id,run_id,actor_type,actor_ref,event_type,payload,created_at)
          values(%s,%s,%s,'agent','development','execution.direct.claimed',%s,
          '2026-11-03T03:12:48.529201+00:00')""",
            (project,task,run,Jsonb({"worker_id":"gha-direct-41570692508-0"})))
        cur.execute("""insert into public.factory_audit_events(
          project_id,task_id,run_id,actor_type,actor_ref,event_type,payload,created_at)
          values(%s,%s,%s,'system','governance','change_set.work_unit.blocked','{}',
          '2026-11-03T03:13:32.00434+00:00')""",(project,task,run))
        cur.execute("""insert into public.factory_tool_usage(
          run_id,created_at,tool_family,operation,estimated_cost) values(
          %s,'2026-11-03T03:13:18.240475+00:00','openai','model_call',0.035042)""",(run,))

    must_reject(db,lambda:call(db,uid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))
    must_reject(db,lambda:call(db,workflow=1))
    must_reject(db,lambda:call(db,failed_sha="a"*40))
    must_reject(db,lambda:call(db,work_sha="b"*40))
    with db.cursor() as cur:cur.execute("update public.factory_project_execution_controls set generation=20")
    must_reject(db,lambda:call(db))
    with db.cursor() as cur:
        cur.execute("update public.factory_project_execution_controls set generation=19")
        cur.execute("update public.factory_human_gates set status='pending'")
    must_reject(db,lambda:call(db))
    with db.cursor() as cur:
        cur.execute("update public.factory_human_gates set status='approved'")
        cur.execute("update public.factory_tasks set scope_keys=%s",(Jsonb([*scopes,"test/other.test.ts"]),))
    must_reject(db,lambda:call(db))
    with db.cursor() as cur:
        cur.execute("update public.factory_tasks set scope_keys=%s",(Jsonb(scopes),))
        cur.execute("update public.factory_tasks set acceptance_criteria=%s",
                    (Jsonb([*criteria[:12],"different",*criteria[13:]]),))
    must_reject(db,lambda:call(db))
    with db.cursor() as cur:
        cur.execute("update public.factory_tasks set acceptance_criteria=%s",(Jsonb(criteria),))
        cur.execute("update public.factory_change_set_work_units set output_commit=%s",("f"*40,))
    must_reject(db,lambda:call(db))
    with db.cursor() as cur:
        cur.execute("update public.factory_change_set_work_units set output_commit=null")
        cur.execute("insert into public.factory_run_agent_assignments values(%s,'assigned')",(run,))
    must_reject(db,lambda:call(db))
    with db.cursor() as cur:
        cur.execute("delete from public.factory_run_agent_assignments")
        cur.execute("""insert into public.factory_tool_usage(
          run_id,created_at,tool_family,operation,estimated_cost) values(
          %s,'2026-11-03T03:13:20+00:00','openai','model_call',null)""",(run,))
    must_reject(db,lambda:call(db))
    with db.cursor() as cur:
        cur.execute("delete from public.factory_tool_usage where estimated_cost is null")
        cur.execute("""select prosecdef from pg_proc where
          oid='public.factory_approve_v2_contract_test_path_once(uuid,bigint,text,text)'::regprocedure""")
        assert cur.fetchone()[0] is False
        for role,allowed in (("anon",False),("authenticated",False),("service_role",True)):
            cur.execute("""select has_function_privilege(%s,
              'public.factory_approve_v2_contract_test_path_once(uuid,bigint,text,text)','EXECUTE')""",
              (role,))
            assert cur.fetchone()[0] is allowed,role

    receipt=call(db)
    assert receipt["requeued"] is True and receipt["attempt_count"]==6
    assert receipt["new_test_path"]==new_path
    assert receipt["release_authorized"] is False
    replay=call(db)
    assert replay["requeued"] is False and replay["attempt_count"]==6
    with db.cursor() as cur:
        cur.execute("""select status,attempt_count,metadata from public.factory_runs where id=%s""",(run,))
        state,attempts,meta=cur.fetchone()
        assert (state,attempts)==("queued",6)
        assert meta["v2_contract_test_path_approved_once"]=="v2-contract-test-path-41570692508-20261103-v1"
        cur.execute("select status,scope_keys,acceptance_criteria from public.factory_tasks where id=%s",(task,))
        status,new_scopes,new_criteria=cur.fetchone()
        assert status=="queued_execution"
        assert new_scopes==[scopes[0],scopes[1],new_path,scopes[3]]
        assert new_criteria[12]==old_rule.replace(old_path,new_path)
        cur.execute("select plan from public.factory_execution_team_plans where id=%s",(plan,))
        new_plan=cur.fetchone()[0]
        assert new_plan["task_assignments"][0]["scope_keys"]==new_scopes
        assert new_plan["task_assignments"][0]["context_paths"]==context
        assert new_plan["operator_test_path_amendment"]["new_test_path"]==new_path
        cur.execute("select status from public.factory_change_sets where id=%s",(cs,))
        assert cur.fetchone()[0]=="building"
        cur.execute("select status from public.factory_change_set_work_units where id=%s",(unit,))
        assert cur.fetchone()[0]=="queued"
        cur.execute("""select count(*) from public.factory_audit_events
          where event_type='journey.v2.exact_test_path_requeued'""")
        assert cur.fetchone()[0]==1
        cur.execute("select sum(estimated_cost) from public.factory_tool_usage where run_id=%s",(run,))
        assert cur.fetchone()[0]==Decimal("0.035042")
print("V2_CONTRACT_TEST_PATH_POSTGRES_PASS")
