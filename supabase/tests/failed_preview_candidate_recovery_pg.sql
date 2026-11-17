\set ON_ERROR_STOP on
-- Disposable PostgreSQL 17 only: direct proof of guarded one-shot recovery.
create role anon nologin;
create role authenticated nologin;
create role service_role nologin;
create table public.factory_projects(id uuid primary key,is_active boolean,project_kind text,repository text,manifest jsonb);
create table public.factory_project_execution_controls(project_id uuid,state text,generation bigint);
create table public.factory_change_sets(id uuid primary key,project_id uuid,root_task_id uuid,release_run_id uuid,status text,candidate_commit text,integration_branch text,lease_owner text,lease_expires_at timestamptz,metadata jsonb,updated_at timestamptz);
create table public.factory_runs(id uuid primary key,task_id uuid,status text,candidate_commit text,branch_name text,lease_owner text,lease_expires_at timestamptz,last_error text,metadata jsonb);
create table public.factory_tasks(id uuid primary key,project_id uuid,status text,updated_at timestamptz);
create table public.factory_release_reports(id uuid default gen_random_uuid(),run_id uuid,project_id uuid,status text,report jsonb);
create table public.factory_human_gates(run_id uuid,status text);
create table public.factory_evaluations(id uuid default gen_random_uuid(),run_id uuid,eval_type text,status text,created_at timestamptz,result jsonb);
create table public.factory_project_state_snapshots(id uuid primary key,project_id uuid,run_id uuid,observed_stage text,created_at timestamptz,evidence jsonb,source_status jsonb);
create table public.factory_tool_usage(id uuid default gen_random_uuid(),run_id uuid,tool_family text,operation text,usage_units integer,estimated_cost numeric,metadata jsonb,created_at timestamptz default now());
create table public.factory_audit_events(id uuid default gen_random_uuid(),project_id uuid,task_id uuid,run_id uuid,actor_type text,actor_ref text,event_type text,payload jsonb,created_at timestamptz default now());
\i supabase/migrations/20261117133000_failed_preview_candidate_recovery.sql
insert into public.factory_projects values(
'19f0f200-3777-46c6-969a-acf0d3426ff1',true,'greenfield',
'leandrosilveiradepaula/dark-channel-studio','{"preview":{"required":true}}');
insert into public.factory_project_execution_controls values(
'19f0f200-3777-46c6-969a-acf0d3426ff1','running',1);
insert into public.factory_change_sets values(
'0bccb423-cacb-49fa-b238-c8baba27e372',
'19f0f200-3777-46c6-969a-acf0d3426ff1',
'62fa220a-565e-4932-a05a-8c318add316d',
'3e747d9d-2440-4e78-8db0-55461753954e','ci_pending',
'41e26b1fbaa80d44ff0e43f4d019af8ce2226ea6',
'factory/change-set-0bccb423',null,null,
'{"integration_release_request":{"pr_number":2,"branch":"factory/change-set-0bccb423","candidate_commit":"41e26b1fbaa80d44ff0e43f4d019af8ce2226ea6"},"integration_epoch_receipt":{"generation":1,"project_id":"19f0f200-3777-46c6-969a-acf0d3426ff1","candidate_commit":"41e26b1fbaa80d44ff0e43f4d019af8ce2226ea6"}}',
now());
insert into public.factory_tasks values(
'62fa220a-565e-4932-a05a-8c318add316d',
'19f0f200-3777-46c6-969a-acf0d3426ff1','failed',now());
insert into public.factory_runs values(
'3e747d9d-2440-4e78-8db0-55461753954e',
'62fa220a-565e-4932-a05a-8c318add316d','failed',
'41e26b1fbaa80d44ff0e43f4d019af8ce2226ea6',
'factory/change-set-0bccb423',null,null,null,
'{"source":"change-set","change_set_id":"0bccb423-cacb-49fa-b238-c8baba27e372","execution_generation":"1"}');
insert into public.factory_release_reports(run_id,project_id,status,report) values(
'3e747d9d-2440-4e78-8db0-55461753954e',
'19f0f200-3777-46c6-969a-acf0d3426ff1','blocked',
'{"release_state":"blocked","definition_of_done":{"missing":[{"key":"migration_validation","human_only":false},{"key":"human_release","human_only":true}]}}');
insert into public.factory_evaluations(run_id,eval_type,status,created_at,result) values(
'3e747d9d-2440-4e78-8db0-55461753954e','browser_e2e','failure',
'2026-11-17T03:02:12+00','{"detail":"preview returned HTTP 500"}');
insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload) values(
'19f0f200-3777-46c6-969a-acf0d3426ff1',
'62fa220a-565e-4932-a05a-8c318add316d',
'3e747d9d-2440-4e78-8db0-55461753954e','system','browser','preview.failed','{}');
insert into public.factory_project_state_snapshots values(
'2ebdda68-9daa-46b4-a194-8c742c4e9886',
'19f0f200-3777-46c6-969a-acf0d3426ff1',
null,'verification','2026-11-17T13:02:43+00',
'{"candidate_commit":"9290634e647a381712b4b1b5bbd1ba0159969ff1","target_repository":"leandrosilveiradepaula/dark-channel-studio","preview":{"status":"browser_verified","provider":"vercel","url":"https://dark-channel-studio-git-facto-431794-leandros-projects-102e32ab.vercel.app","browser_verifier_run_id":44088733294,"verifier_factory_commit":"b773d0869354ade2a37526057fb5db162566d5ed"}}',
'{"github_target":"verified","vercel_preview":"resolved","browser_visual_validation":"success"}');
insert into public.factory_tool_usage(run_id,tool_family,operation,usage_units,estimated_cost,metadata) values(
'3e747d9d-2440-4e78-8db0-55461753954e','github','create_pr',1,0,
'{"pr":"2","head_sha":"223f2bc6e27dbb2e18fbbacaf8f675ceebb2e09f","change_set_id":"0bccb423-cacb-49fa-b238-c8baba27e372"}');
insert into public.factory_tool_usage(run_id,tool_family,operation,usage_units,estimated_cost,metadata) values(
'3e747d9d-2440-4e78-8db0-55461753954e','github','reconcile_pr_candidate',1,0,
'{"previous_commit":"223f2bc6e27dbb2e18fbbacaf8f675ceebb2e09f","candidate_commit":"41e26b1fbaa80d44ff0e43f4d019af8ce2226ea6","new_sha":"41e26b1fbaa80d44ff0e43f4d019af8ce2226ea6","pr_number":"2"}');

create temporary table recovery_facts as
select jsonb_build_object(
  'source','github_actions_exact_sha',
  'repository','leandrosilveiradepaula/dark-channel-studio',
  'branch','factory/change-set-0bccb423',
  'old_sha','41e26b1fbaa80d44ff0e43f4d019af8ce2226ea6',
  'new_sha','9290634e647a381712b4b1b5bbd1ba0159969ff1',
  'pr_number','2','compare_status','ahead','ahead_by','4',
  'behind_by','0','changed_files',jsonb_build_array('app/server.js','app/editorial.js'),
  'ci_state','success','ci_source','github_actions_checks','native_checks',2,
  'native_workflows',1,'browser_run_id','44088733294',
  'browser_snapshot_id','2ebdda68-9daa-46b4-a194-8c742c4e9886',
  'verifier_factory_sha','b773d0869354ade2a37526057fb5db162566d5ed',
  'preview_url','https://dark-channel-studio-git-facto-431794-leandros-projects-102e32ab.vercel.app',
  'release_authorized',false,'new_specialist_approval_required',true,
  'recheck_dod_required',true
) evidence;

do $neg$
declare e jsonb;args jsonb;
begin
 select evidence into e from recovery_facts;
 for args in select value from jsonb_array_elements(jsonb_build_array(
  jsonb_set(e,'{ci_state}','"failure"'::jsonb),
  jsonb_set(e,'{browser_snapshot_id}',to_jsonb('11111111-1111-1111-1111-111111111111'::text)),
  jsonb_set(e,'{release_authorized}','true'::jsonb),
  jsonb_set(e,'{compare_status}','"diverged"'::jsonb),
  jsonb_set(e,'{changed_files}','["../unsafe"]'::jsonb),
  jsonb_set(e,'{native_checks}','1'::jsonb)
 )) loop
   begin
     perform public.factory_reconcile_failed_preview_candidate_v1(
       '0bccb423-cacb-49fa-b238-c8baba27e372',
       '3e747d9d-2440-4e78-8db0-55461753954e',2,
       '41e26b1fbaa80d44ff0e43f4d019af8ce2226ea6',
       '9290634e647a381712b4b1b5bbd1ba0159969ff1',args);
     raise exception 'untrusted witness was accepted';
   exception when sqlstate 'PT400' or sqlstate 'PT409' then null;
   end;
 end loop;
 if (select status from public.factory_runs
    where id='3e747d9d-2440-4e78-8db0-55461753954e')<>'failed'
 then raise exception 'negative probes changed original failed run';end if;
end
$neg$;

do $positive$
declare result jsonb;ev jsonb;
begin
 select evidence into ev from recovery_facts;
 result:=public.factory_reconcile_failed_preview_candidate_v1(
   '0bccb423-cacb-49fa-b238-c8baba27e372',
   '3e747d9d-2440-4e78-8db0-55461753954e',2,
   '41e26b1fbaa80d44ff0e43f4d019af8ce2226ea6',
   '9290634e647a381712b4b1b5bbd1ba0159969ff1',ev);
 if result->>'status'<>'ci_pending'
    or result->>'release_authorized'<>'false'
    or result->>'old_evidence_preserved'<>'true'
 then raise exception 'invalid atomic recovery receipt';end if;
 if (select status from public.factory_tasks where id=
   '62fa220a-565e-4932-a05a-8c318add316d')<>'completed'
 then raise exception 'original integration task not restored';end if;
 if (select candidate_commit from public.factory_change_sets where id=
   '0bccb423-cacb-49fa-b238-c8baba27e372')<>'9290634e647a381712b4b1b5bbd1ba0159969ff1'
 then raise exception 'change set SHA not reconciled';end if;
 if (select status from public.factory_release_reports where run_id=
   '3e747d9d-2440-4e78-8db0-55461753954e')<>'blocked'
 then raise exception 'historical release block was overwritten';end if;
 if (select count(*) from public.factory_evaluations where run_id=
   '3e747d9d-2440-4e78-8db0-55461753954e' and status='failure')<>1
 then raise exception 'historical browser failure was destroyed';end if;
 begin
   perform public.factory_reconcile_failed_preview_candidate_v1(
     '0bccb423-cacb-49fa-b238-c8baba27e372',
     '3e747d9d-2440-4e78-8db0-55461753954e',2,
     '41e26b1fbaa80d44ff0e43f4d019af8ce2226ea6',
     '9290634e647a381712b4b1b5bbd1ba0159969ff1',ev);
   raise exception 'replayed recovery was allowed';
 exception when sqlstate 'PT409' then null;
 end;
end
$positive$;
do $acl$
declare n int;
begin
 select count(*) into n from pg_proc p join pg_namespace s on s.oid=p.pronamespace
 where s.nspname='public' and p.proname='factory_reconcile_failed_preview_candidate_v1'
 and p.prosecdef=false and has_function_privilege('service_role',p.oid,'EXECUTE')
 and not has_function_privilege('anon',p.oid,'EXECUTE')
 and not has_function_privilege('authenticated',p.oid,'EXECUTE');
 if n<>1 then raise exception 'service-role-only invoker grant violated';end if;
end
$acl$;
select 'FAILED_PREVIEW_CANDIDATE_PG=PASS' as result;
