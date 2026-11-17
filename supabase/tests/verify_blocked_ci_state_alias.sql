\set ON_ERROR_STOP on
-- Append-only synthetic receipts: legacy ci_conclusion and guarded
-- failed-Preview ci_state must both work, but forged aliases must fail.
-- Runs exclusively after bootstrap, original migration, v2 compatibility
-- migration and original strict PostgreSQL verification.
do $prepare$
begin
 if not exists(select 1 from public.factory_runs
   where id='44444444-4444-4444-4444-444444444444'
   and status='ci_pending' and candidate_commit=repeat('c',40)) then
  raise exception 'original QA must complete before legacy witness tests';
 end if;
end $prepare$;
update public.factory_runs
set status='release_policy_blocked',candidate_commit=repeat('b',40)
where id='44444444-4444-4444-4444-444444444444';
update public.factory_change_sets
set status='ci_pending',candidate_commit=repeat('b',40),
    metadata=jsonb_set(
      jsonb_set(metadata,'{integration_release_request,candidate_commit}',
        to_jsonb(repeat('b',40)),false),
      '{integration_epoch_receipt,candidate_commit}',to_jsonb(repeat('b',40)),false)
where id='33333333-3333-3333-3333-333333333333';
do $alias_negative$
declare
 base jsonb;
 tampered jsonb;
 new_evidence jsonb;
begin
 base=jsonb_build_object(
   'change_set_id','33333333-3333-3333-3333-333333333333',
   'pr_number','42','previous_commit',repeat('a',40),
   'old_sha',repeat('a',40),'new_sha',repeat('b',40),
   'candidate_commit',repeat('b',40),
   'compare_status','ahead','behind_by','0',
   'ci_state','success',
   'source','github_actions_exact_sha',
   'recovery_source','failed_preview',
   'ci_source','github_actions_checks',
   'native_checks','2','native_workflows','1',
   'browser_snapshot_id','2ebdda68-9daa-46b4-a194-8c742c4e9886',
   'browser_run_id','44088733294',
   'verifier_factory_sha',repeat('f',40),
   'new_specialist_approval_required',true,
   'recheck_dod_required',true,
   'release_authorized',false,
   'repository','owner/product',
   'branch','factory/change-set-33333333'
 );
 new_evidence=jsonb_build_object(
   'old_sha',repeat('b',40),'new_sha',repeat('d',40),
   'pr_number','42','repository','owner/product',
   'branch','factory/change-set-33333333',
   'compare_status','ahead','behind_by','0',
   'ahead_by','1','changed_files',jsonb_build_array('src/safe.ts'),
   'ci_state','success','reason','bounded_native_ci_reconciliation',
   'release_authorized',false
 );
 for tampered in select value from jsonb_array_elements(jsonb_build_array(
   jsonb_set(base,'{source}','"unverified_source"'::jsonb),
   jsonb_set(base,'{ci_source}','"vercel_status_only"'::jsonb),
   jsonb_set(base,'{release_authorized}','true'::jsonb),
   jsonb_set(base,'{browser_run_id}','"not_a_run"'::jsonb),
   base-'browser_snapshot_id',
   base-'recheck_dod_required',
   base-'native_checks',
   base-'recovery_source'
 )) loop
   insert into public.factory_tool_usage(
    run_id,tool_family,operation,usage_units,estimated_cost,metadata)
   values('44444444-4444-4444-4444-444444444444','github',
     'reconcile_pr_candidate',1,0,tampered);
   begin
     perform public.factory_reconcile_policy_blocked_candidate_v1(
       '33333333-3333-3333-3333-333333333333',
       '44444444-4444-4444-4444-444444444444',42,
       repeat('b',40),repeat('d',40),new_evidence);
     raise exception 'forged alias receipt was accepted';
   exception when sqlstate 'PT409' then null;
   end;
 end loop;
 if not exists(select 1 from public.factory_runs
   where id='44444444-4444-4444-4444-444444444444'
   and status='release_policy_blocked'
   and candidate_commit=repeat('b',40)) then
  raise exception 'negative alias test mutated live run';
 end if;
 insert into public.factory_tool_usage(
   run_id,tool_family,operation,usage_units,estimated_cost,metadata)
 values('44444444-4444-4444-4444-444444444444','github',
   'reconcile_pr_candidate',1,0,base);
end $alias_negative$;
do $alias_positive$
declare evidence jsonb; result jsonb;
begin
 evidence=jsonb_build_object(
   'old_sha',repeat('b',40),'new_sha',repeat('d',40),
   'pr_number','42','repository','owner/product',
   'branch','factory/change-set-33333333',
   'compare_status','ahead','behind_by','0',
   'ahead_by','1','changed_files',jsonb_build_array('src/safe.ts'),
   'ci_state','success','reason','bounded_native_ci_reconciliation',
   'release_authorized',false
 );
 result=public.factory_reconcile_policy_blocked_candidate_v1(
   '33333333-3333-3333-3333-333333333333',
   '44444444-4444-4444-4444-444444444444',42,
   repeat('b',40),repeat('d',40),evidence);
 if result->>'status' is distinct from 'ci_pending'
    or result->>'candidate_commit' is distinct from repeat('d',40)
    or result->>'release_authorized' is distinct from 'false'
    or result->>'old_evidence_preserved' is distinct from 'true'
 then raise exception 'bounded alias recovery receipt invalid';end if;
 if not exists(select 1 from public.factory_runs
   where id='44444444-4444-4444-4444-444444444444'
   and status='ci_pending' and candidate_commit=repeat('d',40)) then
   raise exception 'new candidate was not rebound';
 end if;
 if not exists(select 1 from public.factory_release_reports
   where run_id='44444444-4444-4444-4444-444444444444'
     and status='blocked' and candidate_commit=repeat('b',40))
 then raise exception 'historical release denial was overwritten';end if;
 begin
   perform public.factory_reconcile_policy_blocked_candidate_v1(
     '33333333-3333-3333-3333-333333333333',
     '44444444-4444-4444-4444-444444444444',42,
     repeat('b',40),repeat('d',40),evidence);
   raise exception 'replayed legacy reconciliation was accepted';
 exception when sqlstate 'PT409' then null;
 end;
end $alias_positive$;
select 'BLOCKED_CANDIDATE_VERIFIED_CI_STATE_ALIAS_PG17=PASS' as result;
