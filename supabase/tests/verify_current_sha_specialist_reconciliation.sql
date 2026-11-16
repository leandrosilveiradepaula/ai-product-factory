-- Disposable real PostgreSQL 17 proof, no production modifications.
\set ON_ERROR_STOP on
do $permissions$
begin
  if has_function_privilege('anon',
    'public.factory_reconcile_passed_current_sha_specialists_v1(uuid,text)','EXECUTE')
   or has_function_privilege('authenticated',
    'public.factory_reconcile_passed_current_sha_specialists_v1(uuid,text)','EXECUTE')
   or not has_function_privilege('service_role',
    'public.factory_reconcile_passed_current_sha_specialists_v1(uuid,text)','EXECUTE')
  then raise exception 'security boundary must be service_role only'; end if;
  if exists(select 1 from pg_proc where oid=
    'public.factory_reconcile_passed_current_sha_specialists_v1(uuid,text)'::regprocedure
    and prosecdef)
  then raise exception 'SECURITY DEFINER prohibited'; end if;
end $permissions$;
set role service_role;

-- Verify the ordinary completion path *ignores an older SHA failure*.
do $normal$
declare v jsonb;
begin
  v:=public.factory_complete_specialist_lane(
    '55555555-5555-5555-5555-555555555554',
    'passed','[]'::jsonb,'{"_factory_claim_token":"synthetic-claim"}'::jsonb);
  if v->>'status'<>'passed' or v->>'run_status'<>'preview_ready'
    or (select status from public.factory_runs where id=
      '33333333-3333-3333-3333-333333333333')<>'preview_ready'
  then raise exception 'old SHA failure contaminated current SHA completion'; end if;
  if not exists(select 1 from public.factory_specialist_lane_jobs
    where role='security' and candidate_commit=repeat('a',40) and status='failed')
  then raise exception 'historical failed evidence disappeared'; end if;
end $normal$;

-- Emulate the already-completed historic bug: the three PASS rows exist,
-- while the run status still references a failure belonging to old SHA.
update public.factory_runs set status='specialist_review_failed'
 where id='33333333-3333-3333-3333-333333333333';

do $deny$
declare original_status text;
begin
  -- Different SHA can never be reconciled.
  begin
    perform public.factory_reconcile_passed_current_sha_specialists_v1(
      '33333333-3333-3333-3333-333333333333',repeat('a',40));
    raise exception 'stale SHA accepted';
  exception when sqlstate 'PT409' then null; end;

  -- Stop/Pause blocks any write to run or audit.
  begin
    update public.factory_project_execution_controls set state='paused'
      where project_id='11111111-1111-1111-1111-111111111111';
    perform public.factory_reconcile_passed_current_sha_specialists_v1(
      '33333333-3333-3333-3333-333333333333',repeat('b',40));
    raise exception 'paused project accepted';
  exception when sqlstate 'PT409' then null; end;

  -- Missing QA proof must fail closed.
  begin
    update public.factory_specialist_lane_jobs set status='failed'
     where id='55555555-5555-5555-5555-555555555552';
    perform public.factory_reconcile_passed_current_sha_specialists_v1(
      '33333333-3333-3333-3333-333333333333',repeat('b',40));
    raise exception 'failed current SHA accepted';
  exception when sqlstate 'PT409' then null; end;

  -- A fabricated PASS without durable completion is not valid.
  begin
    update public.factory_specialist_lane_jobs set completed_at=null
     where id='55555555-5555-5555-5555-555555555553';
    perform public.factory_reconcile_passed_current_sha_specialists_v1(
      '33333333-3333-3333-3333-333333333333',repeat('b',40));
    raise exception 'no completion timestamp accepted';
  exception when sqlstate 'PT409' then null; end;

  -- An unfinished repair cannot be skipped.
  begin
    insert into public.factory_repair_jobs values(
      '66666666-6666-6666-6666-666666666666',
      '33333333-3333-3333-3333-333333333333','queued');
    perform public.factory_reconcile_passed_current_sha_specialists_v1(
      '33333333-3333-3333-3333-333333333333',repeat('b',40));
    raise exception 'unfinished repair accepted';
  exception when sqlstate 'PT409' then null; end;

  if (select status from public.factory_runs where id=
     '33333333-3333-3333-3333-333333333333')<>'specialist_review_failed'
  then raise exception 'adversarial attempts mutated run'; end if;
end $deny$;

do $settle$
declare proof jsonb;
begin
  proof:=public.factory_reconcile_passed_current_sha_specialists_v1(
    '33333333-3333-3333-3333-333333333333',repeat('b',40));
  if proof->>'status'<>'preview_ready'
     or proof->>'candidate_commit'<>repeat('b',40)
     or proof->'release_authorized'<>'false'::jsonb
     or proof->'new_preview_required'<>'true'::jsonb
  then raise exception 'unsafe or incomplete reconciliation receipt'; end if;
  if (select status from public.factory_runs where id=
     '33333333-3333-3333-3333-333333333333')<>'preview_ready'
  then raise exception 'run status was not reconciled'; end if;
  if not exists(select 1 from public.factory_audit_events
      where event_type='specialist.current_sha_passed.reconciled'
      and payload->>'candidate_sha'=repeat('b',40)
      and payload->'production_merge_permitted'='false'::jsonb
      and payload->'old_evidence_preserved'='true'::jsonb)
  then raise exception 'exact SHA durable audit missing'; end if;
  if not exists(select 1 from public.factory_specialist_lane_jobs
    where candidate_commit=repeat('a',40) and status='failed')
  then raise exception 'past failed evidence deleted'; end if;
  begin
    perform public.factory_reconcile_passed_current_sha_specialists_v1(
      '33333333-3333-3333-3333-333333333333',repeat('b',40));
    raise exception 'duplicate reconciliation accepted';
  exception when sqlstate 'PT409' then null; end;
end $settle$;
reset role;
select 'CURRENT_SHA_SPECIALISTS_PG17=PASS' as result;
