-- Synthetic, isolated PostgreSQL 17 only; never run against a hosted Control Plane.
\set ON_ERROR_STOP on
create role anon nologin;
create role authenticated nologin;
create role service_role nologin;
create table public.factory_projects(
 id uuid primary key, project_kind text, repository text, is_active boolean);
create table public.factory_project_execution_controls(
 project_id uuid primary key,state text,generation bigint);
create table public.factory_tasks(
 id uuid primary key,project_id uuid,status text,updated_at timestamptz default now());
create table public.factory_runs(
 id uuid primary key,task_id uuid,status text,candidate_commit text,
 branch_name text,lease_owner text,lease_expires_at timestamptz,
 metadata jsonb,last_error text,attempt_count int,source_commit text);
create table public.factory_change_sets(
 id uuid primary key,project_id uuid,root_task_id uuid,release_run_id uuid,
 status text,candidate_commit text,source_commit text,integration_branch text,
 current_wave int,lease_owner text,lease_expires_at timestamptz,
 metadata jsonb,updated_at timestamptz default now());
create table public.factory_change_set_work_units(
 id uuid primary key,change_set_id uuid,task_id uuid,run_id uuid,
 status text,plan_task_key text,agent_key text,wave int,
 base_commit text,output_commit text,changed_files jsonb,
 updated_at timestamptz default now());
create table public.factory_repair_jobs(
 id uuid primary key,project_id uuid,change_set_id uuid,source_run_id uuid,
 work_unit_id uuid,task_id uuid,source_role text,status text,
 candidate_commit text,cycle int,owner_agent_key text,
 write_scopes jsonb,finding jsonb,updated_at timestamptz default now());
create table public.factory_tool_usage(
 id bigserial primary key,run_id uuid,tool_family text,operation text,
 usage_units int,estimated_cost numeric,metadata jsonb,
 created_at timestamptz default now());
create table public.factory_audit_events(
 project_id uuid,task_id uuid,run_id uuid,
 actor_type text,actor_ref text,event_type text,payload jsonb);
grant usage on schema public to service_role;
grant select,insert,update,delete on all tables in schema public to service_role;
grant usage,select on all sequences in schema public to service_role;

insert into public.factory_projects values(
 '11111111-1111-1111-1111-111111111111','greenfield','owner/studio',true);
insert into public.factory_project_execution_controls values(
 '11111111-1111-1111-1111-111111111111','running',1);
insert into public.factory_tasks(id,project_id,status) values(
 '22222222-2222-2222-2222-222222222222','11111111-1111-1111-1111-111111111111','completed'),
 ('99999999-9999-9999-9999-999999999999','11111111-1111-1111-1111-111111111111','blocked');
insert into public.factory_runs(
 id,task_id,status,candidate_commit,branch_name,metadata,last_error,attempt_count
) values(
 '44444444-4444-4444-4444-444444444444','22222222-2222-2222-2222-222222222222',
 'specialist_review_failed',repeat('a',40),'factory/change-set-33333333',
 '{"source":"change-set","change_set_id":"33333333-3333-3333-3333-333333333333","execution_generation":1}',null,1),
 ('66666666-6666-6666-6666-666666666666','99999999-9999-9999-9999-999999999999',
 'blocked',null,null,'{"source":"change-set","change_set_id":"33333333-3333-3333-3333-333333333333","execution_generation":1}',
 'PermissionError: editable repository context contains redacted secret: src/a.test.ts',1);
insert into public.factory_change_sets(
 id,project_id,root_task_id,release_run_id,status,candidate_commit,
 source_commit,integration_branch,current_wave,metadata
) values(
 '33333333-3333-3333-3333-333333333333',
 '11111111-1111-1111-1111-111111111111',
 '22222222-2222-2222-2222-222222222222',null,'blocked',
 repeat('a',40),repeat('f',40),'factory/change-set-33333333',2,
 jsonb_build_object(
  'blocker',jsonb_build_object(
   'type','implementation_preflight_error',
   'reason','PermissionError: editable repository context contains redacted secret: src/a.test.ts',
   'work_unit_id','77777777-7777-7777-7777-777777777777',
   'run_id','66666666-6666-6666-6666-666666666666'),
  'integration_release_request',jsonb_build_object('candidate_commit',repeat('a',40),
   'pr_number',2,'branch','factory/change-set-33333333'),
  'integration_epoch_receipt',jsonb_build_object('candidate_commit',repeat('a',40),
   'generation',1,'project_id','11111111-1111-1111-1111-111111111111')));
insert into public.factory_change_set_work_units(
 id,change_set_id,task_id,run_id,status,plan_task_key,agent_key,
 wave,base_commit,changed_files
) values(
 '77777777-7777-7777-7777-777777777777',
 '33333333-3333-3333-3333-333333333333',
 '99999999-9999-9999-9999-999999999999',
 '66666666-6666-6666-6666-666666666666',
 'blocked','repair-security-1','development',2,repeat('a',40),'[]'::jsonb);
insert into public.factory_repair_jobs(
 id,project_id,change_set_id,source_run_id,
 work_unit_id,task_id,source_role,status,candidate_commit,
 cycle,owner_agent_key,write_scopes,finding
) values(
 '88888888-8888-8888-8888-888888888888',
 '11111111-1111-1111-1111-111111111111',
 '33333333-3333-3333-3333-333333333333',
 '44444444-4444-4444-4444-444444444444',
 '77777777-7777-7777-7777-777777777777',
 '99999999-9999-9999-9999-999999999999',
 'security','queued',repeat('a',40),1,'development',
 '["src/a.test.ts"]'::jsonb,
 '{"path":"src/a.test.ts","kind":"secret_scan","code":"supabase_secret"}'::jsonb);
insert into public.factory_tool_usage(
 run_id,tool_family,operation,usage_units,estimated_cost,metadata
) values(
 '44444444-4444-4444-4444-444444444444','github','create_pr',1,0,
 jsonb_build_object('pr','2','head_sha',repeat('a',40),
 'change_set_id','33333333-3333-3333-3333-333333333333'));
