"""Disposable PostgreSQL verification for Journey V2 safe supersession.

Never call against a real Factory project. The DSN is deliberately fixed to the
isolated GitHub Actions PostgreSQL service, and all values are synthetic.
"""
import hashlib
import os
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb

DSN = os.environ.get("FACTORY_JOURNEY_SUPERSESSION_TEST_DSN", "")
if "localhost:5432/journey_supersession_test" not in DSN:
    raise SystemExit("REFUSING_NON_ISOLATED_SUPERSESSION_DATABASE")
ROOT = Path(__file__).resolve().parents[1]
previous = (ROOT / "scripts/verify_journey_delivery_binding_postgres.py").read_text().split(
    "with psycopg.connect", 1)[0]
os.environ.setdefault("FACTORY_JOURNEY_BINDING_TEST_DSN", DSN)
namespace = {"__file__": str(ROOT / "scripts/verify_journey_delivery_binding_postgres.py")}
exec(previous, namespace)
BASE = namespace["BASE"]
V2 = namespace["MIGRATION"]
MIGRATION = (ROOT / "supabase/migrations/20261101130000_journey_v2_safe_supersession.sql").read_text()
PROJECT = "e2ea3201-e9a3-489f-bf14-916aecc7de09"
REQUEST = "d49060c4-69a0-c58d-4254-54a40003f607"
OPERATOR = "7d08460c-8cae-4f96-aaa4-89104d53dcfa"
COMMAND = "8d17b4de-8f05-49ac-94e2-ea4d93d56adb"
OLD_SHA, NEW_SHA, POLICY, PROOF = "a"*40, "b"*40, "c"*64, "d"*64
PREVIEW = "preview/crm209-delivery-v3"

def call(cur, name, *args):
    cur.execute("select public." + name + "(" + ",".join(["%s"]*len(args)) + ")", args)
    return cur.fetchone()[0]

def blocked(db, fn, *args):
    try:
        with db.transaction():
            with db.cursor() as cur:
                fn(cur, *args)
    except psycopg.Error:
        return
    raise AssertionError("unsafe transition was accepted")

with psycopg.connect(DSN, autocommit=True) as db:
    with db.cursor() as cur:
        cur.execute("drop schema public cascade; create schema public")
        cur.execute(BASE)
        # Model the production-only tables and columns used by the new CAS.
        cur.execute("""
            alter table public.factory_projects add column updated_at timestamptz default now();
            alter table public.factory_project_execution_controls add column updated_at timestamptz default now();
            alter table public.factory_runs add column lease_owner text;
            alter table public.factory_runs add column lease_expires_at timestamptz;
            alter table public.factory_change_sets add column lease_owner text;
            alter table public.factory_change_sets add column lease_expires_at timestamptz;
            create table public.factory_change_set_work_units(
                id uuid primary key default gen_random_uuid(), change_set_id uuid,
                status text, output_commit text);
            create table public.factory_human_gates(id uuid primary key default gen_random_uuid(),run_id uuid);
            create table public.factory_console_operators(user_id uuid primary key,role text,is_active boolean);
            create function public.factory_control_quiescent(p_project_id uuid) returns boolean
            language sql stable security invoker set search_path='' as $fn$
            select not exists(select 1 from public.factory_runs r
              join public.factory_tasks t on t.id=r.task_id
              where t.project_id=p_project_id and r.lease_owner is not null
                and (r.lease_expires_at is null or r.lease_expires_at>now())
                and r.status not in ('completed','cancelled','failed','merged','blocked','superseded'))
              and not exists(select 1 from public.factory_change_sets cs
                where cs.project_id=p_project_id and cs.lease_owner is not null
                and (cs.lease_expires_at is null or cs.lease_expires_at>now())
                and cs.status not in ('completed','cancelled','failed','merged','blocked','superseded'))
            $fn$;
        """)
        cur.execute(V2)
        cur.execute(MIGRATION)
        cur.execute("insert into factory_console_operators values(%s,'admin',true)", (OPERATOR,))
        manifest={"journey_delivery_binding_v2":{"enabled":True,"version":2,"digest":POLICY,
                  "source_mode":"main_snapshot","preview_base_ref":"preview/crm171-delivery-v2",
                  "release_base_ref":"main"}}
        cur.execute("""insert into factory_projects(id,project_key,repository,manifest,is_active,project_kind)
            values(%s,'crm-infodive','leandrosilveiradepaula/crm-infodive',%s,true,'existing')""",
            (PROJECT,Jsonb(manifest)))
        cur.execute("""insert into factory_project_execution_controls(project_id,state,generation,version)
            values(%s,'running',16,15)""", (PROJECT,))
        request_text="CRM #171 old blocked run"
        digest=hashlib.sha256(request_text.encode()).hexdigest()
        intake=call(cur,"factory_enqueue_journey_intake_v2","crm-infodive",request_text,
            REQUEST,"github-owner","github-owner","123",digest,
            "leandrosilveiradepaula/ai-product-factory",1055)
        journey=intake["journey_id"]
        call(cur,"factory_record_journey_source_evidence_v2",
            journey,"leandrosilveiradepaula/crm-infodive","main",OLD_SHA,POLICY,PROOF,16)
        binding={"journey_id":journey,"project_id":PROJECT,"request_id":REQUEST,
                 "execution_generation":16,"policy_version":2,"policy_digest":POLICY,
                 "repository":"leandrosilveiradepaula/crm-infodive",
                 "source_repository":"leandrosilveiradepaula/crm-infodive",
                 "source_commit":OLD_SHA,"source_ref":"main","source_mode":"main_snapshot",
                 "integration_branch":"factory/journey-"+journey,
                 "preview_branch_prefix":"preview/journey-"+journey[:8],
                 "preview_base_ref":"preview/crm171-delivery-v2","release_base_ref":"main",
                 "binding_version":2,"source_proof_digest":PROOF}
        bound=call(cur,"factory_bind_journey_source_v2","crm-infodive",REQUEST,16,2,Jsonb(binding))
        cur.execute("update factory_runs set status='completed' where id=%s",(bound["run_id"],))
        cur.execute("update factory_tasks set status='completed' where id=%s",(bound["task_id"],))
        cur.execute("select state from factory_journeys where id=%s",(journey,))
        assert cur.fetchone()[0]=="executing"
        cur.execute("""insert into factory_tasks(project_id,journey_id,parent_task_id,title,
            status,complexity,risk,acceptance_criteria,depends_on)
            values(%s,%s,%s,'Blocked direct implementation','blocked','medium','{}','[]','[]')
            returning id""",(PROJECT,journey,bound["task_id"]))
        direct_task=cur.fetchone()[0]
        cur.execute("""insert into factory_runs(task_id,journey_id,status,execution_route,source_commit,branch_name,
            metadata) values(%s,%s,'blocked','direct',%s,%s,%s)""",
            (direct_task,journey,OLD_SHA,binding["integration_branch"],Jsonb({"execution_generation":16})))
        cur.execute("""insert into factory_change_sets(project_id,root_task_id,source_commit,
            integration_branch,candidate_commit,status,metadata) values(%s,%s,%s,%s,%s,'blocked','{}') returning id""",
            (PROJECT,bound["task_id"],OLD_SHA,binding["integration_branch"],OLD_SHA))
        change_set=cur.fetchone()[0]
        cur.execute("insert into factory_change_set_work_units(change_set_id,status) values(%s,'blocked')",(change_set,))

    args=("crm-infodive",journey,COMMAND,OPERATOR,16,15,OLD_SHA,PREVIEW,NEW_SHA,NEW_SHA)
    blocked(db,lambda cur:call(cur,"factory_supersede_inactive_journey_v2",*args[:4],16,14,*args[6:]))
    blocked(db,lambda cur:call(cur,"factory_supersede_inactive_journey_v2",*args[:4],16,15,*args[6:-1],OLD_SHA))
    blocked(db,lambda cur:call(cur,"factory_supersede_inactive_journey_v2",args[0],args[1],args[2],
        "88888888-8888-4888-8888-888888888888",*args[4:]))
    with db.cursor() as cur:
        # A second new Start is forbidden while the blocked V2 journey remains.
        blocked(db,lambda c:call(c,"factory_enqueue_journey_intake_v2",
            "crm-infodive","new request","11111111-1111-4111-8111-111111111111",
            "github-owner","github-owner","125",hashlib.sha256(b"new request").hexdigest(),
            "leandrosilveiradepaula/ai-product-factory",1055))
        cur.execute("set role authenticated")
        blocked(db,lambda c:call(c,"factory_supersede_inactive_journey_v2",*args))
        cur.execute("reset role")
        cur.execute("insert into factory_human_gates(run_id) values(%s)",(bound["run_id"],))
    blocked(db,lambda c:call(c,"factory_supersede_inactive_journey_v2",*args))
    with db.cursor() as cur:
        cur.execute("delete from factory_human_gates where run_id=%s",(bound["run_id"],))
        cur.execute("update factory_change_sets set lease_owner='test' where id=%s",(change_set,))
    blocked(db,lambda c:call(c,"factory_supersede_inactive_journey_v2",*args))
    with db.cursor() as cur:
        cur.execute("update factory_change_sets set lease_owner=null where id=%s",(change_set,))
        receipt=call(cur,"factory_supersede_inactive_journey_v2",*args)
        assert receipt["status"]=="superseded" and receipt["generation"]==17
        assert receipt["new_preview_ref"]==PREVIEW and not receipt["production_release_authorized"]
        replay=call(cur,"factory_supersede_inactive_journey_v2",*args)
        assert replay==receipt
        cur.execute("select state from factory_journeys where id=%s",(journey,))
        assert cur.fetchone()[0]=="superseded"
        cur.execute("select state,generation,version from factory_project_execution_controls where project_id=%s",(PROJECT,))
        assert cur.fetchone()==("running",17,16)
        cur.execute("select manifest->'journey_delivery_binding_v2' from factory_projects where id=%s",(PROJECT,))
        policy=cur.fetchone()[0]
        assert policy["version"]==3 and policy["preview_base_ref"]==PREVIEW
        assert policy["source_commit_pin"]==NEW_SHA and policy["preview_base_source_sha"]==NEW_SHA
        cur.execute("select status from factory_change_sets where id=%s",(change_set,))
        assert cur.fetchone()[0]=="blocked", "historical change set must remain untouched"
        cur.execute("select count(*) from factory_audit_events where event_type='journey.superseded'")
        assert cur.fetchone()[0]==1
        new_text="CRM #209 authorized continuation"
        req2="11111111-1111-4111-8111-111111111111"
        intake2=call(cur,"factory_enqueue_journey_intake_v2","crm-infodive",new_text,req2,
            "github-owner","github-owner","125",hashlib.sha256(new_text.encode()).hexdigest(),
            "leandrosilveiradepaula/ai-product-factory",1055)
        assert intake2["created"] is True and intake2["state"]=="awaiting_source"
        blocked(db,lambda c:call(c,"factory_enqueue_journey_intake_v2","crm-infodive",
            "other request","22222222-2222-4222-8222-222222222222","github-owner",
            "github-owner","126",hashlib.sha256(b"other request").hexdigest(),
            "leandrosilveiradepaula/ai-product-factory",1055))
        blocked(db,lambda c:call(c,"factory_supersede_inactive_journey_v2",*args[:2],
            "33333333-3333-4333-8333-333333333333",*args[3:]))
print("JOURNEY_V2_SAFE_SUPERSESSION_POSTGRES_PASS")
