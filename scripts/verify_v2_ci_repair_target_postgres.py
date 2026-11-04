#!/usr/bin/env python3
"""Isolated PostgreSQL proof: V2 CI repair recovery is exact, atomic and one-shot."""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict

dsn=os.environ.get("FACTORY_V2_REPAIR_TEST_DSN","")
config=conninfo_to_dict(dsn)
if (os.environ.get("FACTORY_V2_REPAIR_TEST_ISOLATED")!="true"
    or config.get("host") not in ("127.0.0.1","localhost")
    or config.get("dbname")!="factory_v2_repair_test"
    or config.get("user")!="factory_ci"):
    raise SystemExit("REFUSING_NON_ISOLATED_V2_REPAIR_DATABASE")

migration=(
    Path(__file__).resolve().parents[1] / "supabase/migrations/"
    "20261104011200_resume_blocked_v2_ci_repair_target.sql"
).read_text()

schema="""
create role anon nologin;
create role authenticated nologin;
create role service_role nologin;
create table public.factory_projects (
 id uuid primary key, project_key text, repository text, project_kind text,
 is_active boolean, manifest jsonb
);
create table public.factory_project_execution_controls (
 project_id uuid primary key, state text, generation bigint
);
create table public.factory_tasks (
 id uuid primary key, project_id uuid, parent_task_id uuid, status text,
 scope_keys jsonb, updated_at timestamptz
);
create table public.factory_runs (
 id uuid primary key, task_id uuid, journey_id uuid, status text,
 execution_route text, candidate_commit text, branch_name text, metadata jsonb,
 attempt_count integer, lease_owner text, lease_expires_at timestamptz,
 last_error text
);
create table public.factory_change_sets (
 id uuid primary key, project_id uuid, root_task_id uuid, status text,
 source_commit text, candidate_commit text, integration_branch text,
 current_wave integer, release_run_id uuid, lease_owner text,
 lease_expires_at timestamptz, metadata jsonb, updated_at timestamptz
);
create table public.factory_change_set_work_units (
 id uuid primary key, change_set_id uuid, task_id uuid, run_id uuid,
 status text, base_commit text, output_commit text, changed_files jsonb,
 wave integer, plan_task_key text, updated_at timestamptz
);
create table public.factory_ci_repair_requests (
 id uuid primary key, project_id uuid, change_set_id uuid, source_run_id uuid,
 work_unit_id uuid, repository text, pr_number integer, branch text,
 original_candidate_commit text, execution_generation bigint,
 attempt integer, max_attempts integer, failure_class text, failures jsonb,
 write_scopes jsonb, status text, blocker_reason text, lease_owner text,
 lease_expires_at timestamptz, updated_at timestamptz
);
create table public.factory_journeys (
 id uuid primary key, project_id uuid, request_id uuid,
 state text, binding jsonb
);
create table public.factory_audit_events (
 id bigint generated always as identity primary key,
 project_id uuid, task_id uuid, run_id uuid,
 actor_type text, actor_ref text, event_type text, payload jsonb
);
"""

p,root,task,journey,request,src,run,cs,original,repair,rr=(
    uuid4() for _ in range(11)
)
source_sha="a"*40
candidate="b"*40
branch="factory/journey-"+str(journey)
preview="preview/real-candidate"
scopes=["src/services/ContractService.ts","test/contract-access.test.ts"]
reason="PermissionError: CI repair requires the existing project's verified target"
binding={
    "binding_version":2,"source_mode":"main_snapshot",
    "repository":"owner/crm","source_commit":source_sha,
    "integration_branch":branch,"preview_base_ref":preview,
    "release_base_ref":"main","execution_generation":19,
}
blocker={
    "type":"implementation_preflight_error","reason":reason,
    "run_id":str(run),"work_unit_id":str(repair),
}
cs_meta={
    "blocker":blocker,"ci_repair_request_id":str(rr),
    "integration_release_request":{"pr_number":212,"candidate_commit":candidate},
}
run_meta={
    "change_set_id":str(cs),"execution_generation":19,
    "blocker_type":"implementation_preflight_error",
}
source_meta={
    "change_set_id":str(cs),"ci_repair_request_id":str(rr),
}
failures=[{
    "name":"native-ci/tests","failure_class":"code","conclusion":"failure",
}]
rr_blocker=json.dumps({"type":"implementation_preflight_error","reason":reason})
rpc="public.factory_resume_blocked_v2_ci_repair_target_once"

with psycopg.connect(dsn,autocommit=True) as db:
    db.execute(schema)
    db.execute(migration)
    acl=db.execute("""
        select prosecdef, has_function_privilege('service_role',oid,'execute'),
        has_function_privilege('anon',oid,'execute'),
        has_function_privilege('authenticated',oid,'execute')
        from pg_proc where proname='factory_resume_blocked_v2_ci_repair_target_once'
    """).fetchone()
    assert acl==(False,True,False,False),acl
    db.execute("insert into factory_projects values (%s,'crm','owner/crm','existing',true,'{}'::jsonb)",(p,))
    db.execute("insert into factory_project_execution_controls values (%s,'running',19)",(p,))
    db.execute("insert into factory_tasks values (%s,%s,null,'completed','[]'::jsonb,null)",(root,p))
    db.execute("insert into factory_tasks values (%s,%s,%s,'blocked',%s::jsonb,null)",
               (task,p,root,json.dumps(scopes)))
    db.execute("""insert into factory_journeys values (%s,%s,%s,'executing',%s::jsonb)""",
               (journey,p,request,json.dumps(binding)))
    db.execute("""insert into factory_runs values (%s,%s,%s,'repair_pending','direct',%s,%s,%s::jsonb,1,null,null,null)""",
               (src,root,journey,candidate,branch,json.dumps(source_meta)))
    db.execute("""insert into factory_runs values (%s,%s,%s,'blocked','direct',null,null,%s::jsonb,1,null,null,%s)""",
               (run,task,journey,json.dumps(run_meta),reason))
    db.execute("""insert into factory_change_sets values (%s,%s,%s,'blocked',%s,%s,%s,2,null,null,null,%s::jsonb,null)""",
               (cs,p,root,source_sha,candidate,branch,json.dumps(cs_meta)))
    db.execute("""insert into factory_change_set_work_units values (%s,%s,%s,%s,'integrated',%s,%s,%s::jsonb,1,'implementation',null)""",
               (original,cs,root,src,source_sha,candidate,json.dumps(scopes)))
    db.execute("""insert into factory_change_set_work_units values (%s,%s,%s,%s,'blocked',%s,null,'[]'::jsonb,2,'ci-repair-1',null)""",
               (repair,cs,task,run,candidate))
    db.execute("""insert into factory_ci_repair_requests values
        (%s,%s,%s,%s,%s,'owner/crm',212,%s,%s,19,1,3,'code',
         %s::jsonb,%s::jsonb,'failed_gate',%s,null,null,null)""",
        (rr,p,cs,src,repair,branch,candidate,json.dumps(failures),
         json.dumps(scopes),rr_blocker))

    def invoke(candidate_sha=candidate,generation=19,request_id=request,run_id=run):
        return db.execute(
            "select "+rpc+"(%s,%s,%s,%s)",
            (run_id,candidate_sha,generation,request_id),
        ).fetchone()[0]

    def idle():
        result=invoke()
        assert result["status"]=="idle" and result["requeued"] is False,result
        assert db.execute("select status from factory_runs where id=%s",(run,)).fetchone()[0]=="blocked"

    for actual in (
        invoke(candidate_sha="c"*40),
        invoke(generation=20),
        invoke(request_id=uuid4()),
        invoke(run_id=uuid4()),
    ):
        assert actual["status"]=="idle" and not actual["requeued"],actual

    db.execute("update factory_project_execution_controls set generation=20 where project_id=%s",(p,))
    idle()
    db.execute("update factory_project_execution_controls set generation=19 where project_id=%s",(p,))

    db.execute("update factory_journeys set binding=jsonb_set(binding,'{preview_base_ref}',to_jsonb('main'::text)) where id=%s",(journey,))
    idle()
    db.execute("update factory_journeys set binding=%s::jsonb where id=%s",(json.dumps(binding),journey))

    db.execute("update factory_runs set lease_owner='another-worker' where id=%s",(run,))
    idle()
    db.execute("update factory_runs set lease_owner=null where id=%s",(run,))

    receipt=invoke()
    assert receipt["status"]=="requeued" and receipt["requeued"] is True,receipt
    assert receipt["release_authorized"] is False and receipt["paid_model_calls"]==0,receipt
    assert receipt["repair_request_id"]==str(rr) and receipt["candidate_commit"]==candidate,receipt
    actual=db.execute("""
        select rr.status,r.status,t.status,u.status,cs.status,src.status
        from factory_ci_repair_requests rr
        join factory_change_set_work_units u on u.id=rr.work_unit_id
        join factory_tasks t on t.id=u.task_id
        join factory_runs r on r.id=u.run_id
        join factory_change_sets cs on cs.id=rr.change_set_id
        join factory_runs src on src.id=rr.source_run_id
        where rr.id=%s
    """,(rr,)).fetchone()
    assert actual==("queued","queued","queued_execution","queued","building","repair_pending"),actual
    audit=db.execute("""
        select payload from factory_audit_events
        where run_id=%s and event_type='journey.v2.ci_repair_target_requeued'
    """,(run,)).fetchall()
    assert len(audit)==1 and audit[0][0]["paid_model_calls"]==0,audit
    second=invoke()
    assert second["status"]=="idle" and second["requeued"] is False,second
    print("V2_CI_REPAIR_TARGET_QA=PASS")
    print("REQUEUED=1 REPLAYED=0 RELEASE_AUTHORIZED=false PAID_MODEL_CALLS=0")
