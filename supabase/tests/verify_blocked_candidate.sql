-- Execute ONLY in disposable PostgreSQL 17 following bootstrap + actual migration.
\set ON_ERROR_STOP on
do $guard$
begin
 if has_function_privilege('anon','public.factory_reconcile_policy_blocked_candidate_v1(uuid,uuid,integer,text,text,jsonb)','EXECUTE') then
  raise exception 'anon must not execute recovery RPC'; end if;
 if has_function_privilege('authenticated','public.factory_reconcile_policy_blocked_candidate_v1(uuid,uuid,integer,text,text,jsonb)','EXECUTE') then
  raise exception 'authenticated must not execute recovery RPC'; end if;
 if not has_function_privilege('service_role','public.factory_reconcile_policy_blocked_candidate_v1(uuid,uuid,integer,text,text,jsonb)','EXECUTE') then
  raise exception 'service role must execute recovery RPC'; end if;
 if exists(select 1 from pg_proc where oid=
   'public.factory_reconcile_policy_blocked_candidate_v1(uuid,uuid,integer,text,text,jsonb)'::regprocedure
   and prosecdef) then raise exception 'RPC must be SECURITY INVOKER'; end if;
end
$guard$;
set role service_role;
create temporary table candidate_test_evidence(e jsonb);
insert into candidate_test_evidence values (
 jsonb_build_object(
 'old_sha',repeat('a',40),'new_sha',repeat('b',40),
 'pr_number','42','repository','owner/product',
 'branch','factory/change-set-33333333',
 'compare_status','ahead','behind_by','0','ahead_by','3',
 'changed_files',jsonb_build_array('app/server.js','src/module.ts'),
 'ci_state','success','reason','verified_exact_sha_native_tests',
 'release_authorized',false
 ));
do $negative$
declare ev jsonb;
begin
 select e into ev from candidate_test_evidence;
 begin
  update public.factory_runs set status='awaiting_release'
  where id='44444444-4444-4444-4444-444444444444';
  perform public.factory_reconcile_policy_blocked_candidate_v1(
    '33333333-3333-3333-3333-333333333333',
    '44444444-4444-4444-4444-444444444444',42,
    repeat('a',40),repeat('b',40),ev);
  raise exception 'awaiting_release run was inappropriately reconciled';
 exception when sqlstate 'PT409' then null;
 end;
 begin
  update public.factory_project_execution_controls set state='paused'
  where project_id='11111111-1111-1111-1111-111111111111';
  perform public.factory_reconcile_policy_blocked_candidate_v1(
    '33333333-3333-3333-3333-333333333333',
    '44444444-4444-4444-4444-444444444444',42,
    repeat('a',40),repeat('b',40),ev);
  raise exception 'paused project was inappropriately reconciled';
 exception when sqlstate 'PT409' then null;
 end;
 begin
  update public.factory_release_reports set status='ready_for_human_release'
  where run_id='44444444-4444-4444-4444-444444444444';
  perform public.factory_reconcile_policy_blocked_candidate_v1(
    '33333333-3333-3333-3333-333333333333',
    '44444444-4444-4444-4444-444444444444',42,
    repeat('a',40),repeat('b',40),ev);
  raise exception 'ready human release was inappropriately reconciled';
 exception when sqlstate 'PT409' then null;
 end;
 begin
  delete from public.factory_tool_usage where operation='create_pr';
  perform public.factory_reconcile_policy_blocked_candidate_v1(
    '33333333-3333-3333-3333-333333333333',
    '44444444-4444-4444-4444-444444444444',42,
    repeat('a',40),repeat('b',40),ev);
  raise exception 'missing original PR receipt was accepted';
 exception when sqlstate 'PT409' then null;
 end;
 begin
  perform public.factory_reconcile_policy_blocked_candidate_v1(
    '33333333-3333-3333-3333-333333333333',
    '44444444-4444-4444-4444-444444444444',42,
    repeat('a',40),repeat('b',40),
    jsonb_set(ev,'{behind_by}','"1"'::jsonb));
  raise exception 'diverged GitHub history was accepted';
 exception when sqlstate 'PT400' then null;
 end;
 begin
  perform public.factory_reconcile_policy_blocked_candidate_v1(
    '33333333-3333-3333-3333-333333333333',
    '44444444-4444-4444-4444-444444444444',42,
    repeat('a',40),repeat('b',40),
    jsonb_set(ev,'{changed_files}','["../secret"]'::jsonb));
  raise exception 'unsafe changed-files path was accepted';
 exception when sqlstate 'PT400' then null;
 end;
 if (select status from public.factory_runs where id='44444444-4444-4444-4444-444444444444')
    is distinct from 'release_policy_blocked' then
  raise exception 'negative attempts changed original blocked run'; end if;
end
$negative$;
do $success$
declare ev jsonb; receipt jsonb;
begin
 select e into ev from candidate_test_evidence;
 receipt:=public.factory_reconcile_policy_blocked_candidate_v1(
    '33333333-3333-3333-3333-333333333333',
    '44444444-4444-4444-4444-444444444444',42,
    repeat('a',40),repeat('b',40),ev);
 if receipt->>'status'<>'ci_pending' or
    receipt->>'candidate_commit'<>repeat('b',40) or
    receipt->'release_authorized'<>'false'::jsonb then
  raise exception 'invalid atomic recovery receipt'; end if;
 if not exists(select 1 from public.factory_runs
   where id='44444444-4444-4444-4444-444444444444'
   and status='ci_pending' and candidate_commit=repeat('b',40)
   and metadata#>>'{policy_blocked_candidate_recovery,previous_status}'='release_policy_blocked'
 ) then raise exception 'CI candidate not rebound atomically'; end if;
 if not exists(select 1 from public.factory_change_sets
   where id='33333333-3333-3333-3333-333333333333'
   and status='ci_pending' and candidate_commit=repeat('b',40)
   and metadata#>>'{integration_release_request,candidate_commit}'=repeat('b',40)
   and metadata#>>'{integration_epoch_receipt,candidate_commit}'=repeat('b',40)
 ) then raise exception 'change-set identity not updated atomically'; end if;
 if not exists(select 1 from public.factory_release_reports
   where run_id='44444444-4444-4444-4444-444444444444'
   and status='blocked' and candidate_commit=repeat('a',40)
 ) then raise exception 'historical denied release report changed'; end if;
 if (select count(*) from public.factory_tool_usage
   where operation='reconcile_pr_candidate'
     and run_id='44444444-4444-4444-4444-444444444444'
     and metadata->>'candidate_commit'=repeat('b',40))<>1 then
  raise exception 'exact candidate reconciliation receipt not persisted'; end if;
 if not exists(select 1 from public.factory_audit_events
   where event_type='change_set.blocked_release_candidate.reconciled'
     and payload->'release_authorized'='false'::jsonb
     and payload->>'candidate_commit'=repeat('b',40))
 then raise exception 'immutable fail-closed audit missing'; end if;
 begin
  perform public.factory_reconcile_policy_blocked_candidate_v1(
    '33333333-3333-3333-3333-333333333333',
    '44444444-4444-4444-4444-444444444444',42,
    repeat('a',40),repeat('b',40),ev);
  raise exception 'duplicate recovery incorrectly succeeded';
 exception when sqlstate 'PT409' then null;
 end;
end
$success$;
-- A real run has original PR (A), already reconciled CI candidate (B),
-- and a second source correction (C). Requiring create_pr SHA==B is WRONG.
-- Keep the original issuance and prior CI receipt independently checked.
update public.factory_runs
set status='release_policy_blocked'
where id='44444444-4444-4444-4444-444444444444'
  and status='ci_pending' and candidate_commit=repeat('b',40);
update public.factory_release_reports
set candidate_commit=repeat('b',40),
    report=jsonb_set(report,'{candidate_commit}',to_jsonb(repeat('b',40)),false)
where run_id='44444444-4444-4444-4444-444444444444'
  and status='blocked' and candidate_commit=repeat('a',40);
-- Previous initial recovery record (A->B) deliberately lacks historical
-- CI metadata in this synthetic fixture; it must fail closed.
do $prior_missing$
declare proof jsonb;
begin
 select e into proof from candidate_test_evidence;
 proof=jsonb_set(jsonb_set(proof,'{old_sha}',to_jsonb(repeat('b',40)),false),
                '{new_sha}',to_jsonb(repeat('c',40)),false);
 begin
  perform public.factory_reconcile_policy_blocked_candidate_v1(
    '33333333-3333-3333-3333-333333333333',
    '44444444-4444-4444-4444-444444444444',42,
    repeat('b',40),repeat('c',40),proof);
  raise exception 'unverified intermediate candidate was accepted';
 exception when sqlstate 'PT409' then null;
 end;
end
$prior_missing$;
-- Synthetic immutable, independent historical GitHub CI reconciliation
-- issuance A -> B, equivalent to the actual existing Control Plane trail.
insert into public.factory_tool_usage(
  run_id,tool_family,operation,usage_units,estimated_cost,metadata
) values(
  '44444444-4444-4444-4444-444444444444',
  'github','reconcile_pr_candidate',1,0,
  jsonb_build_object(
    'change_set_id','33333333-3333-3333-3333-333333333333',
    'pr_number',42,'previous_commit',repeat('a',40),
    'old_sha',repeat('a',40),'new_sha',repeat('b',40),
    'candidate_commit',repeat('b',40),
    'compare_status','ahead','behind_by',0,
    'ci_conclusion','success','repository','owner/product',
    'branch','factory/change-set-33333333'
  )
);
do $prior_verified$
declare proof jsonb;result jsonb;
begin
 select e into proof from candidate_test_evidence;
 proof=jsonb_set(jsonb_set(proof,'{old_sha}',to_jsonb(repeat('b',40)),false),
                '{new_sha}',to_jsonb(repeat('c',40)),false);
 result=public.factory_reconcile_policy_blocked_candidate_v1(
    '33333333-3333-3333-3333-333333333333',
    '44444444-4444-4444-4444-444444444444',42,
    repeat('b',40),repeat('c',40),proof);
 if result->>'status' <> 'ci_pending'
   or result->>'candidate_commit' <> repeat('c',40)
   or result->'release_authorized' <> 'false'::jsonb
 then raise exception 'two-step recovery receipt malformed'; end if;
 if not exists(select 1 from public.factory_tool_usage
   where operation='reconcile_pr_candidate'
     and metadata->>'previous_commit'=repeat('a',40)
     and metadata->>'prior_candidate_commit'=repeat('b',40)
     and metadata->>'candidate_commit'=repeat('c',40)
     and metadata->>'original_head_sha'=repeat('a',40))
 then raise exception 'latest recovery broke durable CI followup lineage'; end if;
 if not exists(select 1 from public.factory_release_reports
    where run_id='44444444-4444-4444-4444-444444444444'
    and status='blocked' and candidate_commit=repeat('b',40))
 then raise exception 'historical denied release report was overwritten'; end if;
end
$prior_verified$;

reset role;
select 'BLOCKED_CANDIDATE_RECOVERY_PG17=PASS' as result;
