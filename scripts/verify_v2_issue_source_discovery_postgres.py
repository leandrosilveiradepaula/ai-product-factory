"""Fail-closed disposable PostgreSQL QA for V2 issue-source read recovery."""
import os
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb

dsn=os.environ.get("FACTORY_V2_SOURCE_DISCOVERY_TEST_DSN","")
if "localhost:5432/v2_source_discovery_test" not in dsn:
    raise SystemExit("REFUSING_NON_ISOLATED_SOURCE_DISCOVERY_DB")
sql=(Path(__file__).resolve().parents[1]/"supabase/migrations/20261101153000_v2_issue_source_discovery_recovery.sql").read_text()
P="11111111-1111-4111-8111-111111111111"
J="22222222-2222-4222-8222-222222222222"
T="33333333-3333-4333-8333-333333333333"
S="44444444-4444-4444-8444-444444444444"
OLD="55555555-5555-4555-8555-555555555555"
A="66666666-6666-4666-8666-666666666666"
CMD="77777777-7777-4777-8777-777777777777"
SHA="a"*40
D="b"*64
BRANCH="factory/journey-"+J
binding={"journey_id":J,"project_id":P,"repository":"leandrosilveiradepaula/crm-infodive",
 "request_id":"88888888-8888-4888-8888-888888888888",
 "source_commit":SHA,"execution_generation":19,"integration_branch":BRANCH}
callargs=(J,S,OLD,CMD,A,19,19,SHA)
def call(cur, values=callargs):
    cur.execute("select public.factory_requeue_v2_issue_discovery_once("+",".join(["%s"]*8)+")",values)
    return cur.fetchone()[0]
def rejects(conn, values=callargs):
    try:
        with conn.transaction():
            with conn.cursor() as c: call(c, values)
    except psycopg.Error: return
    raise AssertionError("unsafe recovery was accepted")

with psycopg.connect(dsn,autocommit=True) as db:
    with db.cursor() as c:
        c.execute("drop schema public cascade; create schema public;")
        c.execute("""
          create role service_role; create role anon; create role authenticated;
          create table public.factory_projects(id uuid primary key,project_key text,
            repository text,is_active boolean,project_kind text,manifest jsonb);
          create table public.factory_project_execution_controls(project_id uuid,state text,
            generation bigint,version bigint);
          create table public.factory_console_operators(user_id uuid,is_active boolean,role text);
          create table public.factory_journeys(id uuid,project_id uuid,state text,
            execution_generation bigint,source_commit text,binding jsonb,
            project_policy_version integer,policy_digest text,request_snapshot jsonb,
            candidate_commit text,work_unit_output_commit text,preview_merge_sha text,
            production_release_sha text);
          create table public.factory_tasks(id uuid,project_id uuid,journey_id uuid,status text,
            parent_task_id uuid,updated_at timestamptz default now());
          create table public.factory_runs(id uuid default gen_random_uuid(),
            task_id uuid,journey_id uuid,status text,execution_route text,
            source_commit text,branch_name text,metadata jsonb,
            lease_owner text,candidate_commit text,created_at timestamptz default now());
          create table public.factory_change_sets(journey_id uuid);
          create table public.factory_human_gates(run_id uuid);
          create table public.factory_deployments(run_id uuid);
          create table public.factory_release_reports(run_id uuid);
          create table public.factory_evaluations(run_id uuid);
          create table public.factory_audit_events(id bigint generated always as identity,
            project_id uuid,task_id uuid,run_id uuid,actor_type text,actor_ref text,
            event_type text,payload jsonb);
          create function public.factory_control_quiescent(p_id uuid) returns boolean
            language sql stable security invoker set search_path='' as $f$
            select true $f$;
        """)
        c.execute(sql)
        c.execute("insert into public.factory_projects values(%s,'crm-infodive',%s,true,'existing',%s)",
                  (P,"leandrosilveiradepaula/crm-infodive",Jsonb({"journey_delivery_binding_v2":{"digest":D}})))
        c.execute("insert into public.factory_project_execution_controls values(%s,'running',19,19)",(P,))
        c.execute("insert into public.factory_console_operators values(%s,true,'admin')",(A,))
        c.execute("""insert into public.factory_journeys values(
          %s,%s,'executing',19,%s,%s,4,%s,%s,null,null,null,null)""",
          (J,P,SHA,Jsonb(binding),D,Jsonb({"text":"Implementar issue #209 em leandrosilveiradepaula/crm-infodive"})))
        c.execute("insert into public.factory_tasks(id,project_id,journey_id,status) values(%s,%s,%s,'failed')",(T,P,J))
        source={"error":"planning has no actionable tasks or decisions",
          "stages":["reconciliation","gap_analysis","planning"],
          "journey_binding_v2":binding,"execution_generation":19,
          "stage_evidence":{"reconciliation":{"output":{"summary":"observed"}},
            "gap_analysis":{"output":{"recommended_next_work":[{"work":"inspect source"}]}}},
          "worker_id":"old"}
        retry={"error":"planning has no actionable tasks or decisions","stages":["planning"],
          "journey_binding_v2":binding,"execution_generation":19,
          "resume_checkpoint":{"schema":"journey_v2_planning_recovery_v1","source_run_id":S},
          "stage_evidence":{"planning":{"status":"failed","output":{"reason_code":"planning_non_actionable"}}}}
        for ident,metadata in ((S,source),(OLD,retry)):
            c.execute("""insert into public.factory_runs(id,task_id,journey_id,status,
              execution_route,source_commit,branch_name,metadata)
              values(%s,%s,%s,'failed','direct',%s,%s,%s)""",
              (ident,T,J,SHA,BRANCH,Jsonb(metadata)))
    rejects(db,callargs[:5]+(19,18,SHA))
    rejects(db,callargs[:5]+(20,19,SHA))
    rejects(db,callargs[:-1]+("f"*40,))
    rejects(db,(J,S,OLD,CMD,"99999999-9999-4999-8999-999999999999",19,19,SHA))
    with db.cursor() as c:
        c.execute("update public.factory_project_execution_controls set state='paused'")
    rejects(db)
    with db.cursor() as c:
        c.execute("update public.factory_project_execution_controls set state='running'")
        c.execute("insert into public.factory_human_gates values(%s)",(OLD,))
    rejects(db)
    with db.cursor() as c:
        c.execute("delete from public.factory_human_gates")
        c.execute("update public.factory_runs set lease_owner='worker' where id=%s",(S,))
    rejects(db)
    with db.cursor() as c:
        c.execute("update public.factory_runs set lease_owner=null where id=%s",(S,))
        result=call(c)
        assert result["status"]=="requeued_new_source_inspection"
        assert result["generation"]==19 and result["release_authorized"] is False
        new=result["run_id"]
        assert call(c)==result, "exact replay must be idempotent"
        c.execute("select status,metadata from public.factory_runs where id=%s",(new,))
        state,metadata=c.fetchone()
        assert state=="queued" and metadata["stages"]==["reconciliation","gap_analysis","planning"]
        assert "stage_evidence" not in metadata
        assert metadata["issue_source_discovery_recovery"]["source_run_id"]==S
        c.execute("select status from public.factory_tasks where id=%s",(T,))
        assert c.fetchone()[0]=="queued"
        c.execute("select count(*) from public.factory_audit_events where event_type='journey.v2.issue_source_discovery_requeued'")
        assert c.fetchone()[0]==1
        c.execute("select count(*) from public.factory_runs where journey_id=%s",(J,))
        assert c.fetchone()[0]==3
        c.execute("select status from public.factory_runs where id in (%s,%s)",(S,OLD))
        assert all(row[0]=="failed" for row in c.fetchall())
    rejects(db,(J,S,OLD,CMD,A,19,19,"f"*40))
    rejects(db,(J,S,OLD,"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",A,19,19,SHA))
print("V2_SOURCE_DISCOVERY_RECOVERY_POSTGRES_PASS")
