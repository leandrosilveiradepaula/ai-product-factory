\set ON_ERROR_STOP on
-- Disposable PostgreSQL 17 ONLY. No production data or credentials.
create role anon nologin;
create role authenticated nologin;
create role service_role nologin;
create table public.factory_projects(id uuid primary key,is_active boolean,project_kind text,repository text);
create table public.factory_project_execution_controls(project_id uuid,state text,generation bigint);
create table public.factory_tasks(id uuid primary key,project_id uuid,status text);
create table public.factory_runs(id uuid primary key,task_id uuid,status text,candidate_commit text,
  branch_name text,metadata jsonb,lease_owner text,lease_expires_at timestamptz,finished_at timestamptz);
create table public.factory_change_sets(id uuid primary key,project_id uuid,root_task_id uuid,status text,
  release_run_id uuid,candidate_commit text,integration_branch text,metadata jsonb,
  lease_owner text,lease_expires_at timestamptz,updated_at timestamptz);
create table public.factory_specialist_lane_jobs(id uuid primary key,run_id uuid,project_id uuid,
  role text,status text,required boolean,candidate_commit text,evidence jsonb,findings jsonb,
  lease_owner text,lease_expires_at timestamptz,attempt_count int,completed_at timestamptz,
  updated_at timestamptz,unique(run_id,role,candidate_commit));
create table public.factory_evaluations(run_id uuid,eval_type text,status text,baseline_ref text);
create table public.factory_repair_jobs(id uuid primary key,specialist_job_id uuid,source_run_id uuid,
  candidate_commit text,source_role text,status text,work_unit_id uuid,updated_at timestamptz);
create table public.factory_change_set_work_units(id uuid primary key,status text,base_commit text,
  output_commit text,run_id uuid);
create table public.factory_audit_events(id bigint generated always as identity,project_id uuid,task_id uuid,
  run_id uuid,actor_type text,actor_ref text,event_type text,payload jsonb,created_at timestamptz default now());
create table public.factory_release_reports(run_id uuid,status text);
create table public.factory_human_gates(run_id uuid,status text);
\i supabase/migrations/20261117154000_verified_invoker_security_recheck.sql
insert into factory_projects values(
  '33333333-3333-4333-8333-333333333333',true,'greenfield','fixture-owner/fixture-product');
insert into factory_project_execution_controls values(
  '33333333-3333-4333-8333-333333333333','running',1);
insert into factory_tasks values(
  '44444444-4444-4444-8444-444444444444',
  '33333333-3333-4333-8333-333333333333','integrated');
insert into factory_runs values(
  '11111111-1111-4111-8111-111111111111',
  '44444444-4444-4444-8444-444444444444',
  'specialist_review_failed',repeat('a',40),'factory/change-set-22222222',
  '{"source":"change-set","change_set_id":"22222222-2222-4222-8222-222222222222","execution_generation":"1"}',
  null,null,null);
insert into factory_change_sets values(
  '22222222-2222-4222-8222-222222222222',
  '33333333-3333-4333-8333-333333333333',
  '44444444-4444-4444-8444-444444444444',
  'blocked',null,repeat('a',40),'factory/change-set-22222222',
  jsonb_build_object('integration_release_request',
    jsonb_build_object('pr_number',17,'candidate_commit',repeat('a',40),
      'branch','factory/change-set-22222222')),null,null,now());
insert into factory_specialist_lane_jobs values
  ('55555555-5555-4555-8555-555555555555',
   '11111111-1111-4111-8111-111111111111',
   '33333333-3333-4333-8333-333333333333','security','failed',true,
   repeat('a',40),'{"_factory_epoch":1}',
   '[{"code":"permissive_public_grant","severity":"error","kind":"database_security",
      "path":"supabase/migrations/strict.sql","source":"architecture_guardian_v1"}]',
   'previous-reviewer',null,1,now(),now()),
  ('66666666-6666-4666-8666-666666666666',
   '11111111-1111-4111-8111-111111111111',
   '33333333-3333-4333-8333-333333333333','qa','passed',true,
   repeat('a',40),'{"_factory_epoch":1}','[]',null,null,1,now(),now()),
  ('77777777-7777-4777-8777-777777777777',
   '11111111-1111-4111-8111-111111111111',
   '33333333-3333-4333-8333-333333333333','operations','passed',true,
   repeat('a',40),'{"_factory_epoch":1}','[]',null,null,1,now(),now());
insert into factory_evaluations values(
 '11111111-1111-4111-8111-111111111111',
 'specialist_security','failed',repeat('a',40));
insert into factory_runs values(
 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','blocked',null,null,'{}',null,null,now());
insert into factory_repair_jobs values(
 '88888888-8888-4888-8888-888888888888',
 '55555555-5555-4555-8555-555555555555',
 '11111111-1111-4111-8111-111111111111',
 repeat('a',40),'security','running',
 '99999999-9999-4999-8999-999999999999',now());
insert into factory_change_set_work_units values(
 '99999999-9999-4999-8999-999999999999',
 'blocked',repeat('a',40),null,'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa');
insert into factory_release_reports values('11111111-1111-4111-8111-111111111111','blocked');
create temporary table verified_proof as select jsonb_build_object(
 'source','github_native_ci_full_pr_scanner','guardian','architecture_guardian_v1',
 'repository','fixture-owner/fixture-product',
 'candidate_commit',repeat('a',40),'pr_number','17','blockers','0',
 'files_reviewed','4','diff_sha256',repeat('d',64),
 'factory_main_sha',repeat('b',40),'factory_main_ci','success',
 'native_ci_state','success','native_checks','2',
 'release_authorized',false,'model_called',false) as payload;

do $negative$
declare sample jsonb; row jsonb;
begin
 select payload into sample from verified_proof;
 for row in select value from jsonb_array_elements(jsonb_build_array(
   jsonb_set(sample,'{blockers}','"3"'::jsonb),
   jsonb_set(sample,'{release_authorized}','true'::jsonb),
   jsonb_set(sample,'{model_called}','true'::jsonb),
   jsonb_set(sample,'{factory_main_ci}','"failure"'::jsonb),
   jsonb_set(sample,'{native_checks}','"0"'::jsonb),
   jsonb_set(sample,'{diff_sha256}','"bogus"'::jsonb),
   jsonb_set(sample,'{candidate_commit}',to_jsonb(repeat('c',40)))
 )) loop
  begin
   perform public.factory_requeue_verified_invoker_security_once_v1(
    '11111111-1111-4111-8111-111111111111',17,repeat('a',40),
    '55555555-5555-4555-8555-555555555555',row);
   raise exception 'unverified recheck payload was accepted';
  exception when sqlstate 'PT400' then null;
  end;
 end loop;
 if (select status from factory_runs where id='11111111-1111-4111-8111-111111111111')
    <> 'specialist_review_failed' then
    raise exception 'negative probes changed original review'; end if;
end $negative$;

do $positive$
declare sample jsonb; result jsonb;
begin
 select payload into sample from verified_proof;
 result:=public.factory_requeue_verified_invoker_security_once_v1(
   '11111111-1111-4111-8111-111111111111',17,repeat('a',40),
   '55555555-5555-4555-8555-555555555555',sample);
 if result->>'status' <> 'specialist_review_pending'
    or result->>'release_authorized'<>'false'
    or result->>'previous_failure_preserved'<>'true'
 then raise exception 'recovery receipt incorrect'; end if;
 if (select status from factory_specialist_lane_jobs where
     id='55555555-5555-4555-8555-555555555555')<>'queued'
 or (select status from factory_repair_jobs where
     id='88888888-8888-4888-8888-888888888888')<>'blocked'
 or (select status from factory_change_sets where
     id='22222222-2222-4222-8222-222222222222')<>'ci_pending'
 or (select release_run_id from factory_change_sets where
     id='22222222-2222-4222-8222-222222222222')
     <> '11111111-1111-4111-8111-111111111111'
 then raise exception 'original one-shot lineage not restored';end if;
 if (select count(*) from factory_evaluations where
   run_id='11111111-1111-4111-8111-111111111111'
   and eval_type='specialist_security' and status='failed') <> 1
 or not exists(select 1 from factory_audit_events where
   event_type='specialist.auth_invoker_recheck.queued'
   and jsonb_array_length(payload->'original_findings')=1)
 then raise exception 'original failure findings not preserved';end if;
 if (select status from factory_release_reports where
   run_id='11111111-1111-4111-8111-111111111111')<>'blocked'
 then raise exception 'production release was forged';end if;
 begin
  perform public.factory_requeue_verified_invoker_security_once_v1(
    '11111111-1111-4111-8111-111111111111',17,repeat('a',40),
    '55555555-5555-4555-8555-555555555555',sample);
  raise exception 'replay was accepted';
 exception when sqlstate 'PT409' then null;
 end;
end $positive$;
do $acl$
declare n int;
begin
 select count(*) into n from pg_proc p join pg_namespace s on s.oid=p.pronamespace
 where s.nspname='public' and p.proname='factory_requeue_verified_invoker_security_once_v1'
   and p.prosecdef=false
   and has_function_privilege('service_role',p.oid,'EXECUTE')
   and not has_function_privilege('anon',p.oid,'EXECUTE')
   and not has_function_privilege('authenticated',p.oid,'EXECUTE');
 if n<>1 then raise exception 'service-role-only invocation is broken';end if;
end $acl$;
select 'SCOPED_INVOKER_SECURITY_RECHECK_PG=PASS' as result;
