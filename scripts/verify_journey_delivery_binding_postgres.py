"""Disposable PostgreSQL QA for Journey Delivery Binding v2; never production."""
import os
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb

DSN=os.environ["FACTORY_JOURNEY_BINDING_TEST_DSN"]
ROOT=Path(__file__).resolve().parents[1]
MIGRATION=(ROOT/"supabase/migrations/20261030150000_journey_delivery_binding_v2.sql").read_text()
PROJECT="e2ea3201-e9a3-489f-bf14-916aecc7de09"
REQUEST="d49060c4-69a0-c58d-4254-54a40003f607"
SHA="a"*40
POLICY="b"*64
PROOF="c"*64

BASE="""
create schema extensions; create extension pgcrypto with schema extensions;
create table public.factory_projects(id uuid primary key,project_key text unique,repository text,manifest jsonb,is_active boolean,project_kind text);
create table public.factory_project_execution_controls(project_id uuid primary key,state text,generation bigint,version bigint);
create table public.factory_tasks(id uuid primary key default extensions.gen_random_uuid(),project_id uuid,parent_task_id uuid,journey_id uuid,external_key text,title text,description text,status text,complexity text,risk jsonb,acceptance_criteria jsonb,depends_on jsonb,scope_keys jsonb,required_capabilities jsonb,agent_role text);
create table public.factory_runs(id uuid primary key default extensions.gen_random_uuid(),task_id uuid,journey_id uuid,status text,execution_route text,source_commit text,branch_name text,metadata jsonb,created_at timestamptz default now());
create table public.factory_change_sets(id uuid primary key default extensions.gen_random_uuid(),root_task_id uuid,journey_id uuid,source_commit text);
create table public.factory_audit_events(id bigint generated always as identity primary key,project_id uuid,task_id uuid,run_id uuid,actor_type text,actor_ref text,event_type text,payload jsonb);
create role service_role; create role authenticated; create role anon;
"""

def call(cur, name, params):
    cur.execute("select public."+name+"("+",".join(["%s"]*len(params))+")",params)
    return cur.fetchone()[0]

with psycopg.connect(DSN,autocommit=True) as db:
    with db.cursor() as cur:
        cur.execute(BASE)
        cur.execute(MIGRATION)
        policy={"enabled":True,"version":2,"digest":POLICY,"source_mode":"main_snapshot","preview_base_ref":"preview/crm171-contracts","release_base_ref":"main"}
        cur.execute("insert into factory_projects values(%s,'crm-infodive','leandrosilveiradepaula/crm-infodive',%s,true,'existing')",(PROJECT,Jsonb({"journey_delivery_binding_v2":policy})))
        cur.execute("insert into factory_project_execution_controls values(%s,'running',17,1)",(PROJECT,))
        intake=call(cur,"factory_enqueue_journey_intake_v2",("crm-infodive","CRM #171",REQUEST,"github-owner","github-owner","123",__import__('hashlib').sha256(b"CRM #171").hexdigest(),"leandrosilveiradepaula/ai-product-factory",1055))
        assert intake["state"]=="awaiting_source"
        # Replay is idempotent, but changed provenance is rejected.
        assert call(cur,"factory_enqueue_journey_intake_v2",("crm-infodive","CRM #171",REQUEST,"github-owner","github-owner","123",__import__('hashlib').sha256(b"CRM #171").hexdigest(),"leandrosilveiradepaula/ai-product-factory",1055))["created"] is False
        journey=intake["journey_id"]
        call(cur,"factory_record_journey_source_evidence_v2",(journey,"leandrosilveiradepaula/crm-infodive","main",SHA,POLICY,PROOF,17))
        binding={"journey_id":journey,"project_id":PROJECT,"request_id":REQUEST,"execution_generation":17,"policy_version":2,"policy_digest":POLICY,"repository":"leandrosilveiradepaula/crm-infodive","source_repository":"leandrosilveiradepaula/crm-infodive","source_commit":SHA,"source_ref":"main","source_mode":"main_snapshot","integration_branch":"factory/journey-"+journey,"preview_branch_prefix":"preview/journey-"+journey[:8],"preview_base_ref":"preview/crm171-contracts","release_base_ref":"main","binding_version":2,"source_proof_digest":PROOF}
        bound=call(cur,"factory_bind_journey_source_v2",("crm-infodive",REQUEST,17,2,Jsonb(binding)))
        assert bound["state"]=="source_bound"
        cur.execute("select journey_id from factory_runs where id=%s",(bound["run_id"],)); assert str(cur.fetchone()[0])==journey
        cur.execute("set role authenticated")
        try:
            cur.execute("select public.factory_enqueue_journey_intake_v2('crm-infodive','x',%s,'github-owner','github-owner','9',%s,'leandrosilveiradepaula/ai-product-factory',1055)",(REQUEST,"d"*64))
        except psycopg.Error: pass
        else: raise AssertionError("authenticated role reached service-only RPC")
        finally: cur.execute("reset role")
print("journey_delivery_binding_postgres_qa=passed")
