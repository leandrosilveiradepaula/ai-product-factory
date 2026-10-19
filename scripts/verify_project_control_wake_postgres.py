#!/usr/bin/env python3
"""Exact SQL regression with disposable localhost PostgreSQL only."""
import os,json,uuid
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict
dsn=os.getenv("FACTORY_WAKE_TEST_DSN","")
conf=conninfo_to_dict(dsn)
if os.getenv("FACTORY_WAKE_TEST_ISOLATED")!="true" or conf.get("host") not in ("127.0.0.1","localhost") or conf.get("dbname")!="factory_wake_test":
 raise SystemExit("refusing non-isolated PostgreSQL")
sql=(Path(__file__).resolve().parents[1]/"supabase/migrations/20261019002000_project_control_wake_outbox.sql").read_text()
setup="""create role service_role nologin;create role anon nologin;create role authenticated nologin;
create table public.factory_projects(id uuid primary key,is_active boolean default true);
create table public.factory_project_execution_controls(project_id uuid primary key,state text,version bigint,generation bigint);
create table public.factory_project_execution_commands(project_id uuid,command_id uuid,command text,expected_version bigint,actor_id uuid,result jsonb,primary key(project_id,command_id));
create table public.factory_audit_events(project_id uuid,actor_type text,actor_ref text,event_type text,payload jsonb);"""
p,c1,c2,actor=uuid.uuid4(),uuid.uuid4(),uuid.uuid4(),uuid.uuid4()
def rpc(db,name,*args):return db.execute("select public."+name+"("+",".join(["%s"]*len(args))+")",args).fetchone()[0]
with psycopg.connect(dsn,autocommit=True) as db:
 db.execute(setup);db.execute(sql)
 perm=db.execute("""select p.prosecdef,has_function_privilege('service_role',p.oid,'execute'),
 has_function_privilege('anon',p.oid,'execute'),has_function_privilege('authenticated',p.oid,'execute')
 from pg_proc p where p.proname='factory_claim_project_control_wake'""").fetchone()
 assert perm==(False,True,False,False),perm
 obsperm=db.execute("""select p.prosecdef,has_function_privilege('service_role',p.oid,'execute'),has_function_privilege('anon',p.oid,'execute'),has_function_privilege('authenticated',p.oid,'execute') from pg_proc p where p.proname='factory_observe_project_control_wakes'""").fetchone()
 assert obsperm==(False,True,False,False),obsperm
 db.execute("insert into public.factory_projects(id) values(%s)",(p,))
 db.execute("insert into public.factory_project_execution_controls values(%s,'draft',0,0)",(p,))
 assert db.execute("select count(*) from public.factory_project_control_wakes").fetchone()[0]==0
 db.execute("update public.factory_project_execution_controls set state='running',version=1,generation=1")
 db.execute("insert into public.factory_project_execution_commands values (%s,%s,'start',0,%s,%s::jsonb)",(p,c1,actor,json.dumps({"command":"start","state":"running","version":1,"generation":1})))
 assert db.execute("select count(*) from public.factory_project_control_wakes").fetchone()[0]==1
 w=rpc(db,"factory_claim_project_control_wake","gha-one",c1)
 assert w["status"]=="claimed" and w["attempt"]==1,w
 assert rpc(db,"factory_claim_project_control_wake","gha-two",c1) is None
 try:
  with db.transaction():rpc(db,"factory_ack_project_control_wake",w["id"],"gha-two","observed")
 except psycopg.Error:pass
 else:raise AssertionError("foreign claimant acknowledged wake")
 assert rpc(db,"factory_ack_project_control_wake",w["id"],"gha-one","dispatched")["status"]=="dispatched"
 assert rpc(db,"factory_claim_project_control_wake","gha-one",c1) is None
 assert rpc(db,"factory_observe_project_control_wakes","gha-observer",16)=={"observed":1,"suppressed":0}
 assert db.execute("select status,attempts from public.factory_project_control_wakes where command_id=%s",(c1,)).fetchone()==("observed",1)
 assert rpc(db,"factory_observe_project_control_wakes","gha-observer",16)=={"observed":0,"suppressed":0}
 db.execute("update public.factory_project_execution_controls set state='running',version=3,generation=2")
 db.execute("insert into public.factory_project_execution_commands values (%s,%s,'resume',2,%s,%s::jsonb)",(p,c2,actor,json.dumps({"command":"resume","state":"running","version":3,"generation":2})))
 w=rpc(db,"factory_claim_project_control_wake","gha-one",c2)
 db.execute("update public.factory_project_execution_controls set state='paused',version=4")
 assert rpc(db,"factory_ack_project_control_wake",w["id"],"gha-one","observed")["status"]=="suppressed"
 assert db.execute("select count(*) from public.factory_project_control_wakes").fetchone()[0]==2
 # A failed immediate GitHub wake stays pending, but the runner can observe it.
 c3=uuid.uuid4()
 db.execute("update public.factory_project_execution_controls set state='running',version=5,generation=3")
 db.execute("insert into public.factory_project_execution_commands values (%s,%s,'restart',4,%s,%s::jsonb)",(p,c3,actor,json.dumps({"command":"restart","state":"running","version":5,"generation":3})))
 claim=rpc(db,"factory_claim_project_control_wake","console-retry",c3)
 assert claim["status"]=="claimed",claim
 assert rpc(db,"factory_ack_project_control_wake",claim["id"],"console-retry","failed")["status"]=="pending"
 assert rpc(db,"factory_observe_project_control_wakes","gha-observer",16)=={"observed":1,"suppressed":0}
 assert db.execute("select status,attempts from public.factory_project_control_wakes where command_id=%s",(c3,)).fetchone()==("observed",1)
 assert rpc(db,"factory_observe_project_control_wakes","gha-observer",16)=={"observed":0,"suppressed":0}
print("WAKE_OUTBOX_POSTGRES_PASS")
