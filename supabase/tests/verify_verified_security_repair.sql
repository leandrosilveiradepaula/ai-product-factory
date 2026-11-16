-- Synthetic PostgreSQL 17 invariant test.
\set ON_ERROR_STOP on
do $permissions$
begin
 if has_function_privilege('anon',
  'public.factory_settle_verified_blocked_security_repair_v1(uuid,uuid,uuid,text,text,integer,jsonb)',
  'EXECUTE') or has_function_privilege('authenticated',
  'public.factory_settle_verified_blocked_security_repair_v1(uuid,uuid,uuid,text,text,integer,jsonb)',
  'EXECUTE') then raise exception 'unsafe user EXECUTE'; end if;
 if not has_function_privilege('service_role',
  'public.factory_settle_verified_blocked_security_repair_v1(uuid,uuid,uuid,text,text,integer,jsonb)',
  'EXECUTE') then raise exception 'service_role must execute'; end if;
 if exists(select 1 from pg_proc where oid=
  'public.factory_settle_verified_blocked_security_repair_v1(uuid,uuid,uuid,text,text,integer,jsonb)'::regprocedure
  and prosecdef) then raise exception 'SECURITY DEFINER unauthorized'; end if;
end
$permissions$;
set role service_role;
create temporary table fixture(proof jsonb);
insert into fixture values(jsonb_build_object(
 'old_sha',repeat('a',40),'new_sha',repeat('b',40),
 'pr_number','2','compare_status','ahead','behind_by','0',
 'ahead_by','1','ci_conclusion','success','security_secret_scan','clean',
 'changed_files_count','1','changed_files',jsonb_build_array('src/a.test.ts'),
 'branch','factory/change-set-33333333',
 'repository','owner/studio','release_authorized',false));
do $adversarial$
declare e jsonb;
begin
 select proof into e from fixture;
 begin
  perform public.factory_settle_verified_blocked_security_repair_v1(
   '33333333-3333-3333-3333-333333333333',
   '44444444-4444-4444-4444-444444444444',
   '88888888-8888-8888-8888-888888888888',
   repeat('a',40),repeat('b',40),2,
   jsonb_set(e,'{ci_conclusion}','"failure"'::jsonb));
  raise exception 'FAILED CI accepted';
 exception when sqlstate 'PT400' then null;
 end;
 begin
  perform public.factory_settle_verified_blocked_security_repair_v1(
   '33333333-3333-3333-3333-333333333333',
   '44444444-4444-4444-4444-444444444444',
   '88888888-8888-8888-8888-888888888888',
   repeat('a',40),repeat('b',40),2,
   jsonb_set(e,'{changed_files}','["src/other.ts"]'::jsonb));
  raise exception 'out of scope path accepted';
 exception when sqlstate 'PT409' then null;
 end;
 begin
  update public.factory_project_execution_controls
   set state='paused' where project_id='11111111-1111-1111-1111-111111111111';
  perform public.factory_settle_verified_blocked_security_repair_v1(
   '33333333-3333-3333-3333-333333333333',
   '44444444-4444-4444-4444-444444444444',
   '88888888-8888-8888-8888-888888888888',
   repeat('a',40),repeat('b',40),2,e);
  raise exception 'paused project accepted';
 exception when sqlstate 'PT409' then null;
 end;
 begin
  update public.factory_repair_jobs set status='passed'
    where id='88888888-8888-8888-8888-888888888888';
  perform public.factory_settle_verified_blocked_security_repair_v1(
   '33333333-3333-3333-3333-333333333333',
   '44444444-4444-4444-4444-444444444444',
   '88888888-8888-8888-8888-888888888888',
   repeat('a',40),repeat('b',40),2,e);
  raise exception 'already completed repair accepted';
 exception when sqlstate 'PT409' then null;
 end;
 if (select status from public.factory_change_sets
  where id='33333333-3333-3333-3333-333333333333') <> 'blocked'
 then raise exception 'negative probes mutated source'; end if;
end
$adversarial$;
do $success$
declare e jsonb;result jsonb;
begin
 select proof into e from fixture;
 result=public.factory_settle_verified_blocked_security_repair_v1(
   '33333333-3333-3333-3333-333333333333',
   '44444444-4444-4444-4444-444444444444',
   '88888888-8888-8888-8888-888888888888',
   repeat('a',40),repeat('b',40),2,e);
 if result->>'status'<>'ci_pending'
  or result->>'candidate_commit'<>repeat('b',40)
  or result->'release_authorized'<>'false'::jsonb
 then raise exception 'invalid settlement result'; end if;
 if not exists(select 1 from public.factory_change_sets
  where id='33333333-3333-3333-3333-333333333333'
  and status='ci_pending' and candidate_commit=repeat('b',40)
  and release_run_id='44444444-4444-4444-4444-444444444444'
  and metadata->>'blocker' is null
  and metadata#>>'{integration_release_request,candidate_commit}'=repeat('b',40))
 then raise exception 'change set not atomically rebound'; end if;
 if not exists(select 1 from public.factory_runs
   where id='44444444-4444-4444-4444-444444444444'
     and status='ci_pending' and candidate_commit=repeat('b',40))
 then raise exception 'root run not rebound for exact SHA'; end if;
 if not exists(select 1 from public.factory_change_set_work_units
  where id='77777777-7777-7777-7777-777777777777'
   and status='integrated' and output_commit=repeat('b',40)
   and changed_files='["src/a.test.ts"]'::jsonb)
 then raise exception 'verified external fix absent from lineage'; end if;
 if not exists(select 1 from public.factory_repair_jobs
  where id='88888888-8888-8888-8888-888888888888'
  and status='integrated' and candidate_commit=repeat('b',40))
 then raise exception 'repair not integrated'; end if;
 if not exists(select 1 from public.factory_runs
   where id='66666666-6666-6666-6666-666666666666'
   and status='blocked' and candidate_commit is null
   and last_error like 'PermissionError:%')
 then raise exception 'blocked run history was overwritten'; end if;
 if (select count(*) from public.factory_tool_usage
    where run_id='44444444-4444-4444-4444-444444444444'
    and operation='reconcile_pr_candidate'
    and metadata->>'previous_commit'=repeat('a',40)
    and metadata->>'candidate_commit'=repeat('b',40))<>1
 then raise exception 'CI queue durable receipt missing'; end if;
 if not exists(select 1 from public.factory_audit_events
   where event_type='change_set.security_repair.exact_sha_integrated'
   and payload->'release_authorized'='false'::jsonb
   and payload->'new_specialist_review_required'='true'::jsonb)
 then raise exception 'independent exact SHA audit missing'; end if;
 begin
  perform public.factory_settle_verified_blocked_security_repair_v1(
   '33333333-3333-3333-3333-333333333333',
   '44444444-4444-4444-4444-444444444444',
   '88888888-8888-8888-8888-888888888888',
   repeat('a',40),repeat('b',40),2,e);
  raise exception 'duplicate succeeded';
 exception when sqlstate 'PT409' then null;
 end;
end
$success$;
reset role;
select 'VERIFIED_SECURITY_REPAIR_PG17=PASS' as result;
