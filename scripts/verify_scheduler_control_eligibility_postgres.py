#!/usr/bin/env python3
"""Exercise real selector SQL in isolated disposable PostgreSQL. No prod writes."""
import os
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict

cfg=conninfo_to_dict(os.environ.get("FACTORY_SCHEDULER_ELIGIBILITY_TEST_DSN",""))
if (os.environ.get("FACTORY_SCHEDULER_ELIGIBILITY_TEST_ISOLATED")!="true"
    or cfg.get("host") not in ("127.0.0.1","localhost")
    or cfg.get("dbname")!="factory_scheduler_eligibility_test"):
    raise SystemExit("refusing non-isolated database")
root=Path(__file__).resolve().parents[1]
sql=(root/"supabase/migrations/20261020181000_fence_scheduler_eligibility_manual_control.sql").read_text()
schema="""
create role service_role nologin;
create role anon nologin;
create role authenticated nologin;
create table public.factory_projects(id uuid primary key default gen_random_uuid(),
 project_key text unique not null,is_active boolean not null default true);
create table public.factory_project_execution_controls(project_id uuid primary key references public.factory_projects(id),
 state text not null,generation bigint not null);
create table public.factory_project_scheduling(project_id uuid primary key,priority text,deadline timestamptz,
 customer_impact int,max_active_workers int,paused bool);
create table public.factory_incidents(project_id uuid,severity text,status text);
create table public.factory_tasks(id uuid primary key default gen_random_uuid(),project_id uuid,
 status text,created_at timestamptz default now(),title text,description text,complexity text,
 risk jsonb,acceptance_criteria jsonb,depends_on jsonb);
create table public.factory_runs(id uuid primary key default gen_random_uuid(),
 task_id uuid,status text,metadata jsonb);
create table public.factory_execution_team_plans(id uuid primary key default gen_random_uuid(),
 project_id uuid,status text,version int);
create table public.factory_change_sets(id uuid primary key default gen_random_uuid(),
 project_id uuid,team_plan_id uuid,status text,current_wave int);
create table public.factory_change_set_work_units(id uuid primary key default gen_random_uuid(),
 task_id uuid,change_set_id uuid,wave int,status text,agent_key text,created_at timestamptz default now());
"""
with psycopg.connect(os.environ["FACTORY_SCHEDULER_ELIGIBILITY_TEST_DSN"],autocommit=True) as conn:
    conn.execute(schema)
    conn.execute(sql)
    for fn in ("factory_portfolio_candidates(integer)","factory_peek_planned_work(text,integer)"):
        acl=conn.execute("""select has_function_privilege('service_role',%s,'EXECUTE'),
            has_function_privilege('anon',%s,'EXECUTE'),
            has_function_privilege('authenticated',%s,'EXECUTE')""",(fn,fn,fn)).fetchone()
        assert acl==(True,False,False),(fn,acl)
    pid=conn.execute("insert into public.factory_projects(project_key) values('qa') returning id").fetchone()[0]
    conn.execute("insert into public.factory_project_execution_controls values(%s,'draft',0)",(pid,))
    team=conn.execute("insert into public.factory_execution_team_plans(project_id,status,version) values(%s,'ready',1) returning id",(pid,)).fetchone()[0]
    change=conn.execute("insert into public.factory_change_sets(project_id,team_plan_id,status,current_wave) values(%s,%s,'planned',1) returning id",(pid,team)).fetchone()[0]
    task=conn.execute("""insert into public.factory_tasks(project_id,status,title,description,complexity,risk,acceptance_criteria,depends_on)
    values(%s,'queued','test','test','medium','{}'::jsonb,'[]'::jsonb,'[]'::jsonb) returning id""",(pid,)).fetchone()[0]
    conn.execute("insert into public.factory_change_set_work_units(task_id,change_set_id,wave,status,agent_key) values(%s,%s,1,'pending','direct')",(task,change))
    def inspect():
        portfolio=conn.execute("select public.factory_portfolio_candidates(20)").fetchone()[0]
        planned=conn.execute("select public.factory_peek_planned_work('qa',100)").fetchone()[0]
        assert isinstance(portfolio,list) and isinstance(planned,list)
        return (len(portfolio),len(planned))
    assert inspect()==(0,0),"draft leaked eligibility"
    conn.execute("update public.factory_project_execution_controls set state='running',generation=1 where project_id=%s",(pid,))
    assert inspect()==(1,1),"authorized queued Work Unit absent"
    for state in ("pausing","paused","stopping","stopped"):
        conn.execute("update public.factory_project_execution_controls set state=%s where project_id=%s",(state,pid))
        assert inspect()==(0,0),f"{state} leaked eligibility"
    conn.execute("update public.factory_project_execution_controls set state='running',generation=2 where project_id=%s",(pid,))
    assert inspect()==(1,1),"resume did not restore existing work"
    conn.execute("insert into public.factory_runs(task_id,status) values(%s,'created')",(task,))
    assert inspect()==(0,0),"existing run admitted a duplicate"
    conn.execute("delete from public.factory_runs where task_id=%s",(task,))
    conn.execute("update public.factory_project_scheduling set paused=true where project_id=%s",(pid,))
    # No row in scheduling yet; create soft pause and retain underlying Work Unit.
    conn.execute("insert into public.factory_project_scheduling(project_id,paused) values(%s,true)",(pid,))
    assert inspect()==(0,1),"soft paused portfolio admitted a candidate"
    conn.execute("update public.factory_project_scheduling set paused=false where project_id=%s",(pid,))
    assert inspect()==(1,1),"soft resume did not restore eligible project"
    conn.execute("update public.factory_project_execution_controls set generation=0 where project_id=%s",(pid,))
    assert inspect()==(0,0),"generation zero admitted queued work"
print("SCHEDULER_CONTROL_ELIGIBILITY_POSTGRES_PASS=1")
