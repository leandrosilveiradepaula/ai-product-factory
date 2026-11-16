-- PostgreSQL 17 local-only fixture; never execute against Supabase production.
\set ON_ERROR_STOP on
create role anon nologin;
create role authenticated nologin;
create role service_role nologin;
create table public.factory_projects (
 id uuid primary key, project_kind text, repository text, is_active boolean
);
create table public.factory_project_execution_controls (
 project_id uuid primary key, state text, generation bigint
);
create table public.factory_tasks (
 id uuid primary key, project_id uuid, status text
);
create table public.factory_change_sets (
 id uuid primary key, project_id uuid, root_task_id uuid, release_run_id uuid,
 status text, candidate_commit text, integration_branch text,
 lease_owner text, lease_expires_at timestamptz, metadata jsonb,
 updated_at timestamptz default now()
);
create table public.factory_runs (
 id uuid primary key, task_id uuid, status text, candidate_commit text,
 branch_name text, lease_owner text, lease_expires_at timestamptz,
 metadata jsonb, last_error text
);
create table public.factory_release_reports (
 id uuid primary key, project_id uuid, run_id uuid,
 status text, candidate_commit text, report jsonb
);
create table public.factory_tool_usage (
 id bigserial primary key, created_at timestamptz not null default now(),
 run_id uuid, tool_family text, operation text, usage_units int,
 estimated_cost numeric, metadata jsonb
);
create table public.factory_audit_events (
 project_id uuid, task_id uuid, run_id uuid, actor_type text, actor_ref text,
 event_type text, payload jsonb
);
grant usage on schema public to service_role;
grant select,insert,update,delete on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to service_role;
insert into public.factory_projects(id,project_kind,repository,is_active) values
 ('11111111-1111-1111-1111-111111111111','greenfield','owner/product',true);
insert into public.factory_project_execution_controls(project_id,state,generation) values
 ('11111111-1111-1111-1111-111111111111','running',1);
insert into public.factory_tasks(id,project_id,status) values
 ('22222222-2222-2222-2222-222222222222',
  '11111111-1111-1111-1111-111111111111','integrated');
insert into public.factory_change_sets(
 id,project_id,root_task_id,release_run_id,status,candidate_commit,
 integration_branch,metadata
) values (
 '33333333-3333-3333-3333-333333333333',
 '11111111-1111-1111-1111-111111111111',
 '22222222-2222-2222-2222-222222222222',
 '44444444-4444-4444-4444-444444444444',
 'ci_pending',repeat('a',40),'factory/change-set-33333333',
 jsonb_build_object('integration_release_request',jsonb_build_object(
     'candidate_commit',repeat('a',40),'pr_number',42,
     'branch','factory/change-set-33333333'),
     'integration_epoch_receipt',jsonb_build_object(
     'candidate_commit',repeat('a',40),'generation',1,
     'project_id','11111111-1111-1111-1111-111111111111'))
);
insert into public.factory_runs(id,task_id,status,candidate_commit,branch_name,metadata) values
 ('44444444-4444-4444-4444-444444444444',
  '22222222-2222-2222-2222-222222222222',
  'release_policy_blocked',repeat('a',40),'factory/change-set-33333333',
  '{"source":"change-set","change_set_id":"33333333-3333-3333-3333-333333333333","execution_generation":1}');
insert into public.factory_release_reports(
 id,project_id,run_id,status,candidate_commit,report
) values (
 '55555555-5555-5555-5555-555555555555',
 '11111111-1111-1111-1111-111111111111',
 '44444444-4444-4444-4444-444444444444',
 'blocked',repeat('a',40),
 jsonb_build_object('candidate_commit',repeat('a',40),
 'release_state','blocked','definition_of_done',jsonb_build_object(
 'missing',jsonb_build_array(
 jsonb_build_object('key','migration_validation','human_only',false),
 jsonb_build_object('key','rollback_analysis','human_only',false),
 jsonb_build_object('key','human_release','human_only',true))))
);
insert into public.factory_tool_usage(run_id,tool_family,operation,usage_units,estimated_cost,metadata)
values('44444444-4444-4444-4444-444444444444',
'github','create_pr',1,0,
jsonb_build_object('pr','42','head_sha',repeat('a',40),
'change_set_id','33333333-3333-3333-3333-333333333333'));
