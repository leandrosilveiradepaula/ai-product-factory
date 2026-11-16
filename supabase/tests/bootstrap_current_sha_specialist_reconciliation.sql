-- Disposable, synthetic PostgreSQL 17. No external database connections.
\set ON_ERROR_STOP on
create role anon nologin;
create role authenticated nologin;
create role service_role nologin;
create table public.factory_projects(
 id uuid primary key,is_active boolean not null);
create table public.factory_project_execution_controls(
 project_id uuid primary key,state text not null,generation bigint not null);
create table public.factory_tasks(
 id uuid primary key,project_id uuid not null);
create table public.factory_runs(
 id uuid primary key,task_id uuid not null,status text not null,
 candidate_commit text,branch_name text,metadata jsonb not null,
 lease_owner text,lease_expires_at timestamptz);
create table public.factory_change_sets(
 id uuid primary key,project_id uuid not null,release_run_id uuid,
 status text not null,candidate_commit text,integration_branch text,
 lease_owner text,lease_expires_at timestamptz);
create table public.factory_specialist_lane_jobs(
 id uuid primary key,run_id uuid not null,project_id uuid not null,
 role text not null,required boolean not null,candidate_commit text not null,
 status text not null,findings jsonb not null default '[]'::jsonb,
 evidence jsonb not null default '{}'::jsonb,
 lease_owner text,lease_expires_at timestamptz,completed_at timestamptz,
 updated_at timestamptz default now());
create table public.factory_repair_jobs(
 id uuid primary key,source_run_id uuid not null,status text not null);
create table public.factory_evaluations(
 run_id uuid not null,eval_type text,status text,baseline_ref text,result jsonb);
create table public.factory_audit_events(
 project_id uuid,task_id uuid,run_id uuid,actor_type text,
 actor_ref text,event_type text,payload jsonb);
grant usage on schema public to service_role;
grant select,insert,update,delete on all tables in schema public to service_role;

insert into public.factory_projects values('11111111-1111-1111-1111-111111111111',true);
insert into public.factory_project_execution_controls values('11111111-1111-1111-1111-111111111111','running',1);
insert into public.factory_tasks values('22222222-2222-2222-2222-222222222222','11111111-1111-1111-1111-111111111111');
insert into public.factory_runs values(
 '33333333-3333-3333-3333-333333333333',
 '22222222-2222-2222-2222-222222222222',
 'specialist_review_failed',repeat('b',40),
 'factory/change-set-44444444',
 jsonb_build_object('source','change-set',
 'change_set_id','44444444-4444-4444-4444-444444444444',
 'execution_generation',1,
 'specialist_lanes',jsonb_build_object('required',true,
  'candidate_commit',repeat('b',40),
  'roles',jsonb_build_array('operations','qa','security'))),
 null,null);
insert into public.factory_change_sets values(
 '44444444-4444-4444-4444-444444444444',
 '11111111-1111-1111-1111-111111111111',
 '33333333-3333-3333-3333-333333333333',
 'ci_pending',repeat('b',40),'factory/change-set-44444444',null,null);
insert into public.factory_specialist_lane_jobs(
 id,run_id,project_id,role,required,candidate_commit,status,
 evidence,lease_owner,lease_expires_at,completed_at)
 values
 ('55555555-5555-5555-5555-555555555551',
  '33333333-3333-3333-3333-333333333333',
  '11111111-1111-1111-1111-111111111111','security',true,
  repeat('a',40),'failed','{"_factory_epoch":1}',null,null,now()),
 ('55555555-5555-5555-5555-555555555552',
  '33333333-3333-3333-3333-333333333333',
  '11111111-1111-1111-1111-111111111111','qa',true,
  repeat('b',40),'passed','{"_factory_epoch":1}',null,null,now()),
 ('55555555-5555-5555-5555-555555555553',
  '33333333-3333-3333-3333-333333333333',
  '11111111-1111-1111-1111-111111111111','security',true,
  repeat('b',40),'passed','{"_factory_epoch":1}',null,null,now()),
 ('55555555-5555-5555-5555-555555555554',
  '33333333-3333-3333-3333-333333333333',
  '11111111-1111-1111-1111-111111111111','operations',true,
  repeat('b',40),'claimed',
  '{"_factory_epoch":1,"_factory_claim_token":"synthetic-claim"}',
  'synthetic-worker',now()+interval '2 minutes',null);
