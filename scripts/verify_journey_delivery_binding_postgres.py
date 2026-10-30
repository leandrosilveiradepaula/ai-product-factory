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
create table public.factory_runs(id uuid primary key default extensions.gen_random_uuid(),task_id uuid,journey_id uuid,status text,execution_route text,source_commit text,candidate_commit text,branch_name text,metadata jsonb,created_at timestamptz default now());
create table public.factory_change_sets(id uuid primary key default extensions.gen_random_uuid(),project_id uuid,root_task_id uuid,journey_id uuid,source_commit text,integration_branch text,candidate_commit text,release_run_id uuid,status text,metadata jsonb,updated_at timestamptz default now());
create table public.factory_evaluations(id uuid primary key default extensions.gen_random_uuid(),run_id uuid,eval_type text,status text,baseline_ref text,result jsonb);
create table public.factory_deployments(id uuid primary key default extensions.gen_random_uuid(),run_id uuid,environment text,status text,metadata jsonb,created_at timestamptz default now());
create table public.factory_tool_usage(id bigint generated always as identity primary key,run_id uuid,operation text,metadata jsonb);
create table public.factory_release_reports(id uuid primary key default extensions.gen_random_uuid(),project_id uuid,run_id uuid,status text,candidate_commit text,report jsonb,updated_at timestamptz default now());
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
        policy={"enabled":True,"version":2,"digest":POLICY,"source_mode":"main_snapshot","preview_base_ref":"main","release_base_ref":"main"}
        cur.execute("insert into factory_projects values(%s,'crm-infodive','leandrosilveiradepaula/crm-infodive',%s,true,'existing')",(PROJECT,Jsonb({"journey_delivery_binding_v2":policy})))
        cur.execute("insert into factory_project_execution_controls values(%s,'running',17,1)",(PROJECT,))
        intake=call(cur,"factory_enqueue_journey_intake_v2",("crm-infodive","CRM #171",REQUEST,"github-owner","github-owner","123",__import__('hashlib').sha256(b"CRM #171").hexdigest(),"leandrosilveiradepaula/ai-product-factory",1055))
        assert intake["state"]=="awaiting_source"
        cur.execute("select request_snapshot->>'text' from factory_journeys where id=%s",(intake["journey_id"],)); assert cur.fetchone()[0]=="CRM #171"
        # Replay is idempotent, but changed provenance is rejected.
        assert call(cur,"factory_enqueue_journey_intake_v2",("crm-infodive","CRM #171",REQUEST,"github-owner","github-owner","123",__import__('hashlib').sha256(b"CRM #171").hexdigest(),"leandrosilveiradepaula/ai-product-factory",1055))["created"] is False
        journey=intake["journey_id"]
        call(cur,"factory_record_journey_source_evidence_v2",(journey,"leandrosilveiradepaula/crm-infodive","main",SHA,POLICY,PROOF,17))
        binding={"journey_id":journey,"project_id":PROJECT,"request_id":REQUEST,"execution_generation":17,"policy_version":2,"policy_digest":POLICY,"repository":"leandrosilveiradepaula/crm-infodive","source_repository":"leandrosilveiradepaula/crm-infodive","source_commit":SHA,"source_ref":"main","source_mode":"main_snapshot","integration_branch":"factory/journey-"+journey,"preview_branch_prefix":"preview/journey-"+journey[:8],"preview_base_ref":"main","release_base_ref":"main","binding_version":2,"source_proof_digest":PROOF}
        bound=call(cur,"factory_bind_journey_source_v2",("crm-infodive",REQUEST,17,2,Jsonb(binding)))
        assert bound["state"]=="source_bound"
        cur.execute("select journey_id from factory_runs where id=%s",(bound["run_id"],)); assert str(cur.fetchone()[0])==journey
        cur.execute("set role authenticated")
        try:
            cur.execute("select public.factory_enqueue_journey_intake_v2('crm-infodive','x',%s,'github-owner','github-owner','9',%s,'leandrosilveiradepaula/ai-product-factory',1055)",(REQUEST,"d"*64))
        except psycopg.Error: pass
        else: raise AssertionError("authenticated role reached service-only RPC")
        finally: cur.execute("reset role")
        # Adversarial replay and invalid binding leave no partial descendants.
        try:
            call(cur,"factory_enqueue_journey_intake_v2",("crm-infodive","tampered",REQUEST,"github-owner","github-owner","123",__import__('hashlib').sha256(b"tampered").hexdigest(),"leandrosilveiradepaula/ai-product-factory",1055))
        except psycopg.Error: pass
        else: raise AssertionError("tampered replay accepted")
        request2="d49060c4-69a0-c58d-4254-54a40003f608"
        intake2=call(cur,"factory_enqueue_journey_intake_v2",("crm-infodive","CRM #171 followup",request2,"github-owner","github-owner","124",__import__('hashlib').sha256(b"CRM #171 followup").hexdigest(),"leandrosilveiradepaula/ai-product-factory",1055))
        call(cur,"factory_record_journey_source_evidence_v2",(intake2["journey_id"],"leandrosilveiradepaula/crm-infodive","main",SHA,POLICY,PROOF,17))
        bad={**binding,"journey_id":intake2["journey_id"],"request_id":request2,"preview_branch_prefix":None}
        try: call(cur,"factory_bind_journey_source_v2",("crm-infodive",request2,17,2,Jsonb(bad)))
        except psycopg.Error: pass
        else: raise AssertionError("incomplete binding accepted")
        cur.execute("select count(*) from factory_tasks"); assert cur.fetchone()[0]==1
        cur.execute("select count(*) from factory_runs"); assert cur.fetchone()[0]==1

        # Real PostgreSQL state machine: no fabricated CI/Preview/browser PASS.
        root=bound["run_id"]
        cur.execute("update factory_runs set status='completed' where id=%s",(root,))
        cur.execute("select state from factory_journeys where id=%s",(journey,))
        assert cur.fetchone()[0]=="executing"
        candidate="d"*40
        preview_url="https://crm171-preview.vercel.app"
        pr=217
        cur.execute("update factory_runs set status='preview_ready',candidate_commit=%s where id=%s",(candidate,root))
        release_request={"branch":binding["integration_branch"],"candidate_commit":candidate,"pr_number":pr}
        cur.execute("""insert into factory_change_sets(project_id,root_task_id,source_commit,integration_branch,
          candidate_commit,release_run_id,status,metadata)
          values(%s,%s,%s,%s,%s,%s,'ci_pending',%s)""",
          (PROJECT,bound["task_id"],SHA,binding["integration_branch"],candidate,root,
           Jsonb({"integration_release_request":release_request})))
        cur.execute("select id,journey_id from factory_change_sets where release_run_id=%s",(root,))
        change_set_id,change_set_journey=cur.fetchone()
        assert str(change_set_journey)==journey
        cur.execute("""insert into factory_evaluations(run_id,eval_type,status,baseline_ref,result)
          values(%s,'github_ci','success',%s,'{}'),(%s,'quality_gate','success',%s,'{"passed":true}')""",
          (root,candidate,root,candidate))
        cur.execute("""insert into factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
          values(%s,%s,'system','preview-followup','preview.promotion_completed',%s)""",
          (PROJECT,root,Jsonb({"branch":binding["preview_branch_prefix"]+"-"+str(change_set_id),
                               "candidate_commit":candidate,"pr_number":pr})))
        cur.execute("""insert into factory_deployments(run_id,environment,status,metadata)
          values(%s,'preview','success',%s)""",
          (root,Jsonb({"candidate_commit":candidate,"preview_url":preview_url})))
        cur.execute("""insert into factory_evaluations(run_id,eval_type,status,baseline_ref,result)
          values(%s,'browser_e2e','success',%s,'{}')""",(root,preview_url))
        cur.execute("select state,candidate_commit from factory_journeys where id=%s",(journey,))
        assert cur.fetchone()==("preview_verified",candidate)
        # Green browser alone never opens a production gate.
        cur.execute("""insert into factory_release_reports(project_id,run_id,status,candidate_commit,report)
          values(%s,%s,'blocked',%s,'{"blockers":["production policy blocked"]}')""",
          (PROJECT,root,candidate))
        cur.execute("update factory_runs set status='awaiting_release' where id=%s",(root,))
        cur.execute("select state from factory_journeys where id=%s",(journey,))
        assert cur.fetchone()[0]=="preview_verified"
        cur.execute("""insert into factory_tool_usage(run_id,operation,metadata)
          values(%s,'verified_preview_awaiting_human_merge',%s)""",
          (root,Jsonb({"head_sha":"e"*40,"pr":pr,"preview_url":preview_url})))
        cur.execute("""insert into factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
          values(%s,%s,'system','preview-followup','release.awaiting_human_merge',%s)""",
          (PROJECT,root,Jsonb({"head_sha":candidate,"pr":pr})))
        cur.execute("update factory_release_reports set status='ready_for_human_release',report='{\"blockers\":[]}' where run_id=%s",(root,))
        cur.execute("select state from factory_journeys where id=%s",(journey,))
        assert cur.fetchone()[0]=="preview_verified", "adulterated tool receipt opened release gate"
        cur.execute("""insert into factory_tool_usage(run_id,operation,metadata)
          values(%s,'verified_preview_awaiting_human_merge',%s)""",
          (root,Jsonb({"head_sha":candidate,"pr":pr,"preview_url":preview_url})))
        cur.execute("select state,candidate_commit from factory_journeys where id=%s",(journey,))
        assert cur.fetchone()==("awaiting_release",candidate)
        # A claimed merge is not enough: run/report and observed SHA must agree.
        merge="f"*40
        cur.execute("""insert into factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
          values(%s,%s,'system','release-followup','release.human_merge_observed',%s)""",
          (PROJECT,root,Jsonb({"candidate_commit":candidate,"merge_sha":merge})))
        cur.execute("select state from factory_journeys where id=%s",(journey,))
        assert cur.fetchone()[0]=="awaiting_release"
        cur.execute("update factory_runs set status='merged',candidate_commit=%s where id=%s",(merge,root))
        cur.execute("select state from factory_journeys where id=%s",(journey,))
        assert cur.fetchone()[0]=="awaiting_release"
        cur.execute("update factory_release_reports set status='released',report=%s where run_id=%s",
                    (Jsonb({"blockers":[],"merge_sha":merge}),root))
        cur.execute("select state,candidate_commit,production_release_sha from factory_journeys where id=%s",(journey,))
        assert cur.fetchone()==("released_observed",candidate,merge)
        cur.execute("select count(*) from factory_audit_events where event_type='journey.released_observed'")
        assert cur.fetchone()[0]==1
        assert call(cur,"factory_reconcile_journey_v2",(root,))["state"]=="released_observed"
        cur.execute("select count(*) from factory_audit_events where event_type='journey.released_observed'")
        assert cur.fetchone()[0]==1
        # Preview-only is a distinct human gate; no production release is inferred.
        request3="d49060c4-69a0-c58d-4254-54a40003f609"
        policy3={**policy,"preview_base_ref":"preview/crm171-contracts"}
        cur.execute("update factory_projects set manifest=%s where id=%s",
                    (Jsonb({"journey_delivery_binding_v2":policy3}),PROJECT))
        intake3=call(cur,"factory_enqueue_journey_intake_v2",
            ("crm-infodive","CRM #171 Preview",request3,"github-owner","github-owner","125",
             __import__('hashlib').sha256(b"CRM #171 Preview").hexdigest(),
             "leandrosilveiradepaula/ai-product-factory",1055))
        j3=intake3["journey_id"]
        call(cur,"factory_record_journey_source_evidence_v2",
             (j3,"leandrosilveiradepaula/crm-infodive","main",SHA,POLICY,PROOF,17))
        b3={**binding,"journey_id":j3,"request_id":request3,
            "integration_branch":"factory/journey-"+j3,
            "preview_branch_prefix":"preview/journey-"+j3[:8],
            "preview_base_ref":"preview/crm171-contracts"}
        bound3=call(cur,"factory_bind_journey_source_v2",
                    ("crm-infodive",request3,17,2,Jsonb(b3)))
        r3=bound3["run_id"]; candidate3="1"*40; pr3=218; merge3="2"*40
        cur.execute("update factory_runs set status='preview_ready',candidate_commit=%s where id=%s",
                    (candidate3,r3))
        cur.execute("""insert into factory_change_sets(project_id,root_task_id,source_commit,integration_branch,
          candidate_commit,release_run_id,status,metadata)
          values(%s,%s,%s,%s,%s,%s,'ci_pending',%s) returning id""",
          (PROJECT,bound3["task_id"],SHA,b3["integration_branch"],candidate3,r3,
           Jsonb({"integration_release_request":{"branch":b3["integration_branch"],
                   "candidate_commit":candidate3,"pr_number":pr3}})))
        cs3=cur.fetchone()[0]
        cur.execute("""insert into factory_evaluations(run_id,eval_type,status,baseline_ref,result)
          values(%s,'github_ci','success',%s,'{}'),(%s,'quality_gate','success',%s,'{"passed":true}')""",
          (r3,candidate3,r3,candidate3))
        cur.execute("""insert into factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
          values(%s,%s,'system','preview-followup','preview.promotion_completed',%s)""",
          (PROJECT,r3,Jsonb({"branch":b3["preview_branch_prefix"]+"-"+str(cs3),
                             "candidate_commit":candidate3,"pr_number":pr3})))
        cur.execute("""insert into factory_deployments(run_id,environment,status,metadata)
          values(%s,'preview','success',%s)""",
          (r3,Jsonb({"candidate_commit":candidate3,"preview_url":preview_url})))
        cur.execute("""insert into factory_evaluations(run_id,eval_type,status,baseline_ref,result)
          values(%s,'browser_e2e','success',%s,'{}')""",(r3,preview_url))
        cur.execute("select state from factory_journeys where id=%s",(j3,))
        assert cur.fetchone()[0]=="preview_verified"
        cur.execute("""insert into factory_release_reports(project_id,run_id,status,candidate_commit,report)
          values(%s,%s,'blocked',%s,%s)""",
          (PROJECT,r3,candidate3,Jsonb({"blockers":[
              "production requires a separate verified main-target release candidate"]})))
        cur.execute("update factory_runs set status='awaiting_release' where id=%s",(r3,))
        cur.execute("""insert into factory_tool_usage(run_id,operation,metadata)
          values(%s,'verified_preview_awaiting_human_merge',%s)""",
          (r3,Jsonb({"head_sha":candidate3,"pr":pr3,"preview_url":preview_url})))
        cur.execute("""insert into factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
          values(%s,%s,'system','preview-followup','release.awaiting_human_merge',%s)""",
          (PROJECT,r3,Jsonb({"head_sha":candidate3,"pr":pr3})))
        cur.execute("select state from factory_journeys where id=%s",(j3,))
        assert cur.fetchone()[0]=="awaiting_release"
        cur.execute("""insert into factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
          values(%s,%s,'system','nonproduction-observer','change_set.nonproduction_merge.observed',%s)""",
          (PROJECT,r3,Jsonb({"merge_sha":merge3,"candidate_commit":candidate3,
            "base_ref":b3["preview_base_ref"],"head_ref":b3["integration_branch"],
            "repository":b3["repository"],"pr_number":str(pr3),"environment":"preview",
            "merged":True,"merge_is_ancestor":True,"vercel_state":"success",
            "production_released":False,
            "evidence_source":"github_exact_pr_and_merge_commit_status"})))
        cur.execute("select state,preview_merge_sha,production_release_sha from factory_journeys where id=%s",(j3,))
        assert cur.fetchone()==("closed",merge3,None)
        assert call(cur,"factory_reconcile_journey_v2",(r3,))["state"]=="closed"
        cur.execute("select count(*) from factory_audit_events where event_type='journey.released_observed' and run_id=%s",(r3,))
        assert cur.fetchone()[0]==0
        try:
            cur.execute("update factory_projects set manifest='{}'::jsonb where id=%s",(PROJECT,))
        except psycopg.Error: pass
        else: raise AssertionError("V2 policy deletion accepted with persisted journeys")

        cur.execute("set role authenticated")
        try: call(cur,"factory_reconcile_journey_v2",(root,))
        except psycopg.Error: pass
        else: raise AssertionError("authenticated role reached journey settlement RPC")
        finally: cur.execute("reset role")

print("journey_delivery_binding_postgres_qa=passed")
