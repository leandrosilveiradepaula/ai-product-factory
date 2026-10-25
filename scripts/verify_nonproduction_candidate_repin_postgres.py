#!/usr/bin/env python3
"""Run the committed re-pin migration only against disposable local PostgreSQL."""
import json
import os
import uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

dsn=os.getenv("FACTORY_REPIN_TEST_DSN","")
cfg=conninfo_to_dict(dsn)
if (os.getenv("FACTORY_REPIN_TEST_ISOLATED")!="true"
    or cfg.get("host") not in {"localhost","127.0.0.1"}
    or cfg.get("dbname")!="factory_repin_test"):
    raise SystemExit("refusing non-isolated database")

setup="""
create role service_role nologin;
create role anon nologin;
create role authenticated nologin;
create table public.factory_projects(
 id uuid primary key,project_key text unique,repository text,project_kind text,
 is_active boolean,manifest jsonb not null,updated_at timestamptz default now());
create table public.factory_project_execution_controls(
 project_id uuid primary key,state text,generation bigint,version bigint,
 updated_at timestamptz default now());
create table public.factory_tasks(id uuid primary key,project_id uuid,status text);
create table public.factory_runs(
 id uuid primary key,task_id uuid,status text,lease_owner text,
 lease_expires_at timestamptz,metadata jsonb not null default '{}'::jsonb);
create table public.factory_change_sets(
 id uuid primary key,project_id uuid,status text,lease_owner text,
 lease_expires_at timestamptz,root_task_id uuid);
create table public.factory_audit_events(
 id bigint generated always as identity primary key,project_id uuid,
 actor_type text,actor_ref text,event_type text,payload jsonb);
create function public.factory_control_quiescent(p_project_id uuid)
returns boolean language sql stable as $$
select not exists(
 select 1 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
 where t.project_id=p_project_id and r.lease_owner is not null
 and (r.lease_expires_at is null or r.lease_expires_at>now())
 and r.status not in ('completed','blocked','cancelled')
) and not exists(
 select 1 from public.factory_change_sets cs where cs.project_id=p_project_id
 and cs.lease_owner is not null
 and (cs.lease_expires_at is null or cs.lease_expires_at>now())
 and cs.status not in ('completed','blocked','cancelled')
)$$;
"""
project_id=uuid.uuid4()
old="a"*40
new="b"*40
target={"schema_version":1,"mode":"open_pr_candidate",
        "repository":"leandrosilveiradepaula/crm-infodive",
        "branch":"preview/hardening-release-candidate",
        "sha":old,"candidate_pr_number":56}
evidence={
 "source":"github_actions_exact_sha","repository":target["repository"],
 "branch":target["branch"],"pr_number":"56","pr_head_sha":new,
 "branch_head_sha":new,"expected_sha":old,"new_sha":new,
 "pr_base":"main","pr_state":"open","compare_status":"ahead",
 "ahead_by":705,"behind_by":0,"ci_conclusion":"success",
 "ci_sha":new,"ci_run_id":39189959689,
}
migration=(Path(__file__).resolve().parents[1]/
 "supabase/migrations/20261019031000_repin_nonproduction_target.sql").read_text()
terminal_migration=(Path(__file__).resolve().parents[1]/
 "supabase/migrations/20261025214000_repin_terminal_repair_history.sql").read_text()

with psycopg.connect(dsn,autocommit=True) as db:
 db.execute(setup)
 db.execute(migration)
 db.execute(terminal_migration)
 permissions=db.execute("""
 select prosecdef,
 has_function_privilege('service_role',oid,'execute'),
 has_function_privilege('anon',oid,'execute'),
 has_function_privilege('authenticated',oid,'execute')
 from pg_proc where proname='factory_repin_nonproduction_target_v1'
 """).fetchone()
 assert permissions==(False,True,False,False),permissions
 db.execute("""insert into public.factory_projects(
 id,project_key,repository,project_kind,is_active,manifest)
 values (%s,'crm-infodive',%s,'existing',true,%s::jsonb)""",
 (project_id,target["repository"],json.dumps({"delivery_target":target})))
 db.execute("""insert into public.factory_project_execution_controls(
 project_id,state,generation,version) values (%s,'running',1,0)""",(project_id,))

 def rpc(*,expected=old,generation=1,version=0,attestation=None):
  return db.execute("""select public.factory_repin_nonproduction_target_v1(
  'crm-infodive',%s,%s,%s,%s,%s::jsonb,'gha-repin')""",
  (expected,new,generation,version,json.dumps(
   evidence if attestation is None else attestation))).fetchone()[0]
 def rejected(**kw):
  try:
   with db.transaction():rpc(**kw)
  except psycopg.Error:
   return
  raise AssertionError("unsafe candidate re-pin accepted")
 def unchanged():
  value=db.execute("""select manifest->'delivery_target'->>'sha'
    from public.factory_projects where id=%s""",(project_id,)).fetchone()[0]
  assert value==old,value
  epoch=db.execute("""select generation,version from public.factory_project_execution_controls
  where project_id=%s""",(project_id,)).fetchone()
  assert epoch==(1,0),epoch
  count=db.execute("select count(*) from public.factory_audit_events").fetchone()[0]
  assert count==0,count

 rejected(expected="f"*40);unchanged()
 rejected(generation=2);unchanged()
 rejected(version=1);unchanged()
 for key in ("source","ci_sha","ci_conclusion","pr_head_sha","branch_head_sha",
             "branch","pr_number","compare_status","pr_base","ahead_by","behind_by",
             "ci_run_id"):
  forged=dict(evidence)
  forged.pop(key)
  rejected(attestation=forged)
  unchanged()
 for key,value in (
  ("ci_conclusion","failure"),("compare_status","diverged"),
  ("behind_by",1),("pr_base","preview"),("ci_sha",old)):
  forged={**evidence,key:value}
  rejected(attestation=forged)
  unchanged()
 run_id,task_id=uuid.uuid4(),uuid.uuid4()
 db.execute("insert into public.factory_tasks(id,project_id,status) values(%s,%s,'completed')",(task_id,project_id))
 db.execute("""insert into public.factory_runs(id,task_id,status,lease_owner,lease_expires_at) values (
 %s,%s,'running','worker',now()+interval '5 minutes')""",(run_id,task_id))
 rejected();unchanged()
 db.execute("delete from public.factory_runs where id=%s",(run_id,))
 cs_id=uuid.uuid4()
 db.execute("""insert into public.factory_change_sets(id,project_id,status,lease_owner,lease_expires_at) values (
 %s,%s,'running','worker',now()+interval '5 minutes')""",(cs_id,project_id))
 rejected();unchanged()
 db.execute("delete from public.factory_change_sets where id=%s",(cs_id,))

 # Reproduce the real completed CRM lineage. Historical repair_pending runs
 # stay immutable, but are no longer runnable when the root task and its
 # exact Change Set are completed and all leases are released.
 terminal_cs=uuid.uuid4()
 db.execute("""insert into public.factory_change_sets
 (id,project_id,status,lease_owner,lease_expires_at,root_task_id)
 values (%s,%s,'completed',null,null,%s)""",(terminal_cs,project_id,task_id))
 history_1=uuid.uuid4()
 history_2=uuid.uuid4()
 for history in (history_1,history_2):
  db.execute("""insert into public.factory_runs
  (id,task_id,status,lease_owner,lease_expires_at,metadata)
  values (%s,%s,'repair_pending',null,null,%s::jsonb)""",
  (history,task_id,json.dumps({"change_set_id":str(terminal_cs)})))

 # Every missing/mismatched provenance edge must still veto CAS.
 db.execute("""update public.factory_runs set metadata='{}'::jsonb
 where id=%s""",(history_1,))
 rejected();unchanged()
 db.execute("""update public.factory_runs set metadata=%s::jsonb
 where id=%s""",(json.dumps({"change_set_id":str(terminal_cs)}),history_1))
 db.execute("update public.factory_tasks set status='running' where id=%s",(task_id,))
 rejected();unchanged()
 db.execute("update public.factory_tasks set status='completed' where id=%s",(task_id,))
 db.execute("update public.factory_change_sets set status='running' where id=%s",(terminal_cs,))
 rejected();unchanged()
 db.execute("update public.factory_change_sets set status='completed' where id=%s",(terminal_cs,))
 db.execute("update public.factory_change_sets set root_task_id=%s where id=%s",
            (uuid.uuid4(),terminal_cs))
 rejected();unchanged()
 db.execute("update public.factory_change_sets set root_task_id=%s where id=%s",
            (task_id,terminal_cs))
 db.execute("""update public.factory_runs set lease_owner='worker',
  lease_expires_at=now()+interval '5 minutes' where id=%s""",(history_1,))
 rejected();unchanged()
 db.execute("""update public.factory_runs set lease_owner=null,
  lease_expires_at=null where id=%s""",(history_1,))
 db.execute("""update public.factory_change_sets set lease_owner='worker',
  lease_expires_at=now()+interval '5 minutes' where id=%s""",(terminal_cs,))
 rejected();unchanged()
 db.execute("""update public.factory_change_sets set lease_owner=null,
  lease_expires_at=null where id=%s""",(terminal_cs,))

 # No unrelated live runnable work is ever exempted, leased or not.
 competing=uuid.uuid4()
 db.execute("""insert into public.factory_runs
 (id,task_id,status,lease_owner,lease_expires_at)
 values (%s,%s,'ci_pending',null,null)""",(competing,task_id))
 rejected();unchanged()
 db.execute("delete from public.factory_runs where id=%s",(competing,))
 competing_cs=uuid.uuid4()
 db.execute("""insert into public.factory_change_sets
 (id,project_id,status,lease_owner,lease_expires_at,root_task_id)
 values (%s,%s,'review_pending',null,null,%s)""",(competing_cs,project_id,task_id))
 rejected();unchanged()
 db.execute("delete from public.factory_change_sets where id=%s",(competing_cs,))

 # Exact terminal provenance permits the one CAS, without touching history.
 receipt=rpc()
 assert receipt["status"]=="updated" and receipt["new_sha"]==new,receipt
 persisted=db.execute("""select p.manifest->'delivery_target'->>'sha',c.generation,c.version
 from public.factory_projects p join public.factory_project_execution_controls c
 on c.project_id=p.id where p.id=%s""",(project_id,)).fetchone()
 assert persisted==(new,2,1),persisted
 audit=db.execute("""select event_type,payload->>'old_sha',payload->>'new_sha',
 payload->>'ci_sha' from public.factory_audit_events""").fetchall()
 assert audit==[("project.delivery_target.reconciled",old,new,new)],audit
 rejected()
 assert db.execute("select count(*) from public.factory_audit_events").fetchone()[0]==1
 persisted_history=db.execute("""select status,lease_owner,lease_expires_at
  from public.factory_runs where id in (%s,%s) order by id""",(history_1,history_2)).fetchall()
 assert len(persisted_history)==2 and all(row==("repair_pending",None,None) for row in persisted_history),persisted_history
 print("REPIN_TERMINAL_REPAIR_HISTORY_POSTGRES_PASS")
print("NONPRODUCTION_CANDIDATE_REPIN_POSTGRES_PASS")
