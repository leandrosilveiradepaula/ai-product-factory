"""Adversarial, disposable PostgreSQL QA for Journey V2 task lineage identity.

Uses only a locally isolated postgres service. Never opens the real Control Plane.
"""
import hashlib
import os
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb

DSN = os.environ.get("FACTORY_V2_TASK_IDENTITY_QA_DSN", "")
if "localhost:5432/v2_task_identity_qa" not in DSN:
    raise SystemExit("REFUSING_NON_ISOLATED_TASK_IDENTITY_DB")
MIGRATION = (Path(__file__).resolve().parents[1] /
             "supabase/migrations/20261101161000_v2_planned_task_lineage_scope.sql").read_text()
PROJECT = "11111111-1111-4111-8111-111111111111"
J1 = "22222222-2222-4222-8222-222222222222"
J2 = "33333333-3333-4333-8333-333333333333"
J3 = "44444444-4444-4444-8444-444444444444"
ROOT1 = "55555555-5555-4555-8555-555555555555"
ROOT2 = "66666666-6666-4666-8666-666666666666"
ROOT3 = "77777777-7777-4777-8777-777777777777"
RUN2 = "88888888-8888-4888-8888-888888888888"
RUN3 = "99999999-9999-4999-8999-999999999999"
PREV1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PREV2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
TEAM2 = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
TEAM3 = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
ACTOR = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
CMD = "ffffffff-ffff-4fff-8fff-ffffffffffff"
SHA = "a" * 40
DIGEST = "b" * 64
TITLE = "Corrigir leitura isolada e paginada de contratos"
TASK = {"title": TITLE, "task_key": "issue209-contracts-isolated-read",
        "description": "Isolar por owner e tenant", "depends_on": [],
        "scope_keys": ["src/services/ContractService.ts"],
        "required_capabilities": ["implementation"],
        "acceptance_criteria": ["tenant checked", "owner checked"]}
PLAN = {"tasks": [TASK], "decisions_needed": []}
ASSIGNMENT = {"title": TITLE, "task_key": TASK["task_key"],
              "execution_lane": "builder", "agent_key": "development", "wave": 1}
TEAM_PLAN = {"task_assignments": [ASSIGNMENT], "status": "ready"}
def legacy_key(title):
    return "plan-" + hashlib.md5(title.encode()).hexdigest()[:16]
def scoped_key(title, jid):
    return "plan-" + hashlib.md5((title + ":journey:" + jid).encode()).hexdigest()[:16]
def binding(jid):
    return {"journey_id": jid, "source_commit": SHA, "execution_generation": 19,
            "integration_branch": "factory/journey-" + jid}
def recover(cur, *vals):
    cur.execute("select public.factory_recover_v2_plan_task_collision_once(" +
                ",".join(["%s"] * 8) + ")", vals)
    return cur.fetchone()[0]
ARGS = (J3, RUN3, TEAM3, CMD, ACTOR, 19, 19, SHA)
def rejects(db, args):
    try:
        with db.transaction():
            with db.cursor() as cur:
                recover(cur, *args)
    except psycopg.Error:
        return
    raise AssertionError("unsafe recovery unexpectedly succeeded")
with psycopg.connect(DSN, autocommit=True) as db:
    with db.cursor() as c:
        c.execute("drop schema public cascade; create schema public;")
        c.execute("""
            create role service_role;
            create role anon;
            create role authenticated;
            create table public.factory_projects(
              id uuid primary key, project_key text, is_active boolean,
              project_kind text, repository text, manifest jsonb,
              lifecycle_stage text,updated_at timestamptz default now());
            create table public.factory_console_operators(
              user_id uuid,role text,is_active boolean);
            create table public.factory_project_execution_controls(
              project_id uuid,state text,generation bigint,version bigint);
            create table public.factory_journeys(
              id uuid primary key,project_id uuid,state text,execution_generation bigint,
              source_commit text,binding jsonb,policy_digest text,
              project_policy_version integer,request_snapshot jsonb,
              candidate_commit text,work_unit_output_commit text,
              preview_merge_sha text,production_release_sha text);
            create table public.factory_tasks(
              id uuid primary key default gen_random_uuid(),project_id uuid,
              parent_task_id uuid,journey_id uuid,external_key text,title text,
              description text,status text,complexity text,risk jsonb,
              acceptance_criteria jsonb,depends_on jsonb,agent_role text,
              required_capabilities jsonb,scope_keys jsonb,
              updated_at timestamptz default now(),created_at timestamptz default now());
            create table public.factory_runs(
              id uuid primary key default gen_random_uuid(),task_id uuid,journey_id uuid,
              status text,execution_route text,source_commit text,branch_name text,
              metadata jsonb,lease_owner text,candidate_commit text,
              created_at timestamptz default now());
            create table public.factory_execution_team_plans(
              id uuid primary key,project_id uuid,source_run_id uuid,
              version integer,status text,plan jsonb);
            create table public.factory_change_sets(
              id uuid primary key default gen_random_uuid(),project_id uuid,
              team_plan_id uuid unique,root_task_id uuid,journey_id uuid,status text,
              metadata jsonb,source_commit text,integration_branch text,
              updated_at timestamptz default now());
            create table public.factory_change_set_work_units(
              id uuid primary key default gen_random_uuid(),change_set_id uuid,
              task_id uuid,plan_task_key text,agent_key text,wave integer,status text);
            create table public.factory_human_gates(run_id uuid);
            create table public.factory_deployments(run_id uuid);
            create table public.factory_release_reports(run_id uuid);
            create table public.factory_evaluations(run_id uuid);
            create table public.factory_audit_events(
              id bigint generated always as identity,project_id uuid,
              task_id uuid,run_id uuid,actor_type text,actor_ref text,
              event_type text,payload jsonb);
            create function public.factory_control_quiescent(p_id uuid)
            returns boolean language sql stable security invoker
            set search_path='' as $f$ select true $f$;
            create function public.qa_inherit_journey()
            returns trigger language plpgsql set search_path='' as $f$
            begin
              if tg_table_name='factory_tasks' and new.parent_task_id is not null
              then
                select journey_id into new.journey_id from public.factory_tasks
                  where id=new.parent_task_id;
              elsif tg_table_name='factory_change_sets' then
                select journey_id into new.journey_id from public.factory_tasks
                  where id=new.root_task_id;
              end if;
              return new;
            end $f$;
            create trigger qa_task_journey before insert on public.factory_tasks
              for each row execute function public.qa_inherit_journey();
            create trigger qa_cs_journey before insert on public.factory_change_sets
              for each row execute function public.qa_inherit_journey();
        """)
        c.execute(MIGRATION)
        c.execute("insert into public.factory_console_operators values(%s,'admin',true)", (ACTOR,))
        c.execute("""insert into public.factory_projects(
          id,project_key,is_active,project_kind,repository,manifest)
          values (%s,'crm-infodive',true,'existing',
          'leandrosilveiradepaula/crm-infodive',%s)""",
          (PROJECT, Jsonb({"journey_delivery_binding_v2":{"digest":DIGEST},
                           "engineering_plan":PLAN})))
        c.execute("insert into public.factory_project_execution_controls values(%s,'running',19,19)",(PROJECT,))
        for jid in (J1,J2,J3):
            c.execute("""insert into public.factory_journeys values(
              %s,%s,'executing',19,%s,%s,%s,4,%s,null,null,null,null)""",
              (jid,PROJECT,SHA,Jsonb(binding(jid)),DIGEST,
               Jsonb({"text":"Implementar issue #209 leandrosilveiradepaula/crm-infodive"})))
        for tid,jid,status in ((ROOT1,J1,"completed"),(ROOT2,J2,"running"),(ROOT3,J3,"failed")):
            c.execute("""insert into public.factory_tasks(
              id,project_id,journey_id,title,status) values (%s,%s,%s,'Root task',%s)""",
              (tid,PROJECT,jid,status))
        # Historical task from J1 is terminal and used the obsolete title-only ID.
        c.execute("""insert into public.factory_tasks(
          project_id,parent_task_id,journey_id,title,external_key,status)
          values (%s,%s,%s,%s,%s,'blocked')""",
          (PROJECT,ROOT1,J1,TITLE,legacy_key(TITLE)))
        c.execute("""insert into public.factory_runs(
          id,task_id,journey_id,status,source_commit,branch_name)
          values (%s,%s,%s,'completed',%s,%s)""",
          (RUN2,ROOT2,J2,SHA,binding(J2)["integration_branch"]))
        c.execute("""insert into public.factory_execution_team_plans values
          (%s,%s,%s,18,'ready',%s)""",
          (TEAM2,PROJECT,RUN2,Jsonb(TEAM_PLAN)))
        c.execute("select public.factory_persist_product_stage(%s,'planning',%s)",
                  (RUN2,Jsonb(PLAN)))
        c.execute("""select id,external_key from public.factory_tasks
          where journey_id=%s and parent_task_id=%s""",(J2,ROOT2))
        tid2,key2=c.fetchone()
        assert key2==scoped_key(TITLE,J2) and key2!=legacy_key(TITLE)
        c.execute("select public.factory_materialize_change_set(%s)",(TEAM2,))
        first=c.fetchone()[0]
        assert first["builder_work_units"]==1 and first["status"]=="planned"
        c.execute("""select source_commit,integration_branch,journey_id from
          public.factory_change_sets where id=%s""",(first["change_set_id"],))
        assert c.fetchone()==(SHA,binding(J2)["integration_branch"],J2)
        # Current real incident: two earlier failures and the materialization
        # failure on a third run, but the engineering/team plans were recorded.
        for ident in (PREV1,PREV2):
            c.execute("""insert into public.factory_runs(
              id,task_id,journey_id,status,source_commit)
              values (%s,%s,%s,'failed',%s)""",(ident,ROOT3,J3,SHA))
        meta={"error":"control-plane RPC failed: factory_materialize_change_set (400)",
              "stages":["reconciliation","gap_analysis","planning"],
              "journey_binding_v2":binding(J3),"execution_generation":19}
        c.execute("""insert into public.factory_runs(
          id,task_id,journey_id,status,execution_route,source_commit,
          branch_name,metadata) values(%s,%s,%s,'failed','direct',%s,%s,%s)""",
          (RUN3,ROOT3,J3,SHA,binding(J3)["integration_branch"],Jsonb(meta)))
        c.execute("""insert into public.factory_execution_team_plans values
          (%s,%s,%s,19,'ready',%s)""",
          (TEAM3,PROJECT,RUN3,Jsonb(TEAM_PLAN)))
        for event,pl in (
          ("product.stage.persisted",{"stage":"planning","created_tasks":0}),
          ("team.plan.recorded",{"team_plan_id":TEAM3,"status":"ready"})):
            c.execute("""insert into public.factory_audit_events(
              project_id,task_id,run_id,event_type,payload) values(%s,%s,%s,%s,%s)""",
              (PROJECT,ROOT3,RUN3,event,Jsonb(pl)))
    rejects(db, ARGS[:5]+(19,18,SHA))
    rejects(db, ARGS[:5]+(20,19,SHA))
    rejects(db, ARGS[:-1]+("f"*40,))
    rejects(db, (J3,RUN3,TEAM3,CMD,"12345678-1234-4234-8234-123456789012",19,19,SHA))
    with db.cursor() as c:
        c.execute("update public.factory_project_execution_controls set state='paused'")
    rejects(db, ARGS)
    with db.cursor() as c:
        c.execute("update public.factory_project_execution_controls set state='running'")
        c.execute("insert into public.factory_human_gates values (%s)",(RUN3,))
    rejects(db, ARGS)
    with db.cursor() as c:
        c.execute("delete from public.factory_human_gates")
        receipt=recover(c,*ARGS)
        assert receipt["status"]=="recovered" and receipt["paid_calls"]==0
        assert receipt["release_authorized"] is False and receipt["generation"]==19
        assert receipt["source_commit"]==SHA
        assert recover(c,*ARGS)==receipt, "same command replay must be idempotent"
        c.execute("select external_key,journey_id,status from public.factory_tasks where id=%s",
                  (receipt["task_id"],))
        assert c.fetchone()==(scoped_key(TITLE,J3),J3,"queued")
        c.execute("select status,journey_id,source_commit,integration_branch from public.factory_change_sets where id=%s",
                  (receipt["change_set_id"],))
        assert c.fetchone()==("planned",J3,SHA,binding(J3)["integration_branch"])
        c.execute("select count(*) from public.factory_change_set_work_units where change_set_id=%s and status='pending'",
                  (receipt["change_set_id"],))
        assert c.fetchone()[0]==1
        c.execute("select status from public.factory_runs where id=%s",(RUN3,))
        assert c.fetchone()[0]=="failed", "failure evidence cannot be rewritten"
        c.execute("select count(*) from public.factory_audit_events where event_type='journey.v2.plan_task_collision_recovered'")
        assert c.fetchone()[0]==1
    rejects(db,(J3,RUN3,TEAM3,CMD,ACTOR,19,19,"f"*40))
    rejects(db,(J3,RUN3,TEAM3,"12345678-1234-4234-8234-123456789012",ACTOR,19,19,SHA))
print("V2_JOURNEY_TASK_IDENTITY_POSTGRES_PASS")
