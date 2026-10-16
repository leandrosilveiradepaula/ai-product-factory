-- Reconcile a single historical OpenAI Responses call rejected by HTTP 429
-- BEFORE it returned a Response/usage. The original ledger event is retained
-- verbatim in audit and metadata. Production execution requires an explicit
-- human-admin migration approval (not scheduler, not runtime).
-- This classification is ONLY for the exact recorded provider refusal.
do $credit_reconciliation$
declare
  u public.factory_tool_usage%rowtype;
  r public.factory_runs%rowtype;
  w public.factory_change_set_work_units%rowtype;
  s public.factory_change_sets%rowtype;
  v_request constant text := 'req_c83153187db74f209bf372a1f42d4f5b';
  v_when timestamptz := clock_timestamp();
  v_unknowns int;
begin
  perform pg_advisory_xact_lock(hashtext('factory-openai-credit-denial-reconcile-117'));

  select * into u from public.factory_tool_usage where id=117 for update;
  if not found then
    -- Idempotent in a clean database (no historical pilot data).
    return;
  end if;

  select * into r from public.factory_runs
    where id='fffee538-9781-4905-a69d-f3427d6f66b3'::uuid for update;
  select * into w from public.factory_change_set_work_units
    where id='ab1cb363-3716-4cd6-af12-18d856e16fd4'::uuid for update;
  select * into s from public.factory_change_sets
    where id='effc36be-212c-42f2-928b-97381b6d8a28'::uuid for update;
  if r.id is null or w.id is null or s.id is null then
    raise exception 'credit reconciliation abort: required original run, work unit or change set missing';
  end if;

  if exists(
    select 1 from public.factory_audit_events
     where run_id=r.id and event_type='model.usage.credit_rejection_reconciled'
  ) then
    if u.operation='model_call_rejected_credit_exhausted'
      and u.estimated_cost=0 and u.metadata->'credit_reconciliation'->>'request_id'=v_request
    then
      return;
    end if;
    raise exception 'credit reconciliation abort: prior audit conflicts with ledger row';
  end if;

  if u.run_id<>r.id or u.tool_family<>'openai'
     or u.operation<>'model_call_cost_unknown'
     or u.estimated_cost is not null
     or coalesce(u.usage_units,0)<>0
     or u.metadata->>'status'<>'cost_unknown'
     or u.metadata->>'failure_type'<>'RuntimeError'
     or u.metadata->>'reserve_usd'<>'0.50'
     or u.metadata->>'auth_kind'<>'openai_api_key' then
    raise exception 'credit reconciliation abort: original paid usage evidence differs';
  end if;

  if r.status<>'blocked' or r.attempt_count<>1 or r.execution_route<>'direct'
     or r.task_id<>'1eb2b649-c56c-4f4c-a5cf-e706d03e2c0b'::uuid
     or r.lease_owner is not null or r.lease_expires_at is not null
     or r.candidate_commit is not null or r.source_commit is not null
     or r.branch_name is not null
     or r.metadata->>'blocker_type'<>'implementation_producer_error'
     or r.metadata->>'work_unit_id'<>w.id::text
     or r.metadata->>'change_set_id'<>s.id::text then
    raise exception 'credit reconciliation abort: original run state differs';
  end if;

  if r.last_error is null
     or position('HTTP 429; type=insufficient_quota; code=credit_balance_exhausted;' in r.last_error)=0
     or position('request_id='||v_request in r.last_error)=0
     or r.metadata->>'blocker_reason'<>r.last_error
     or s.metadata->'blocker'->>'reason'<>r.last_error
  then
    raise exception 'credit reconciliation abort: provider refusal evidence differs';
  end if;

  if w.status<>'blocked' or w.run_id<>r.id or w.task_id<>r.task_id
     or w.change_set_id<>s.id or w.wave<>7
     or w.plan_task_key<>'integration-api-webhooks'
     or w.output_commit is not null or w.changed_files<>'[]'::jsonb
     or w.base_commit<>'0d621323eb1ecaea43c64610d54803ed0a81a625'
     or w.branch_name<>'factory/cs-effc36be/integration-api-webhooks' then
    raise exception 'credit reconciliation abort: work unit has changed';
  end if;

  if s.project_id<>'70515123-ecbb-4f4b-a38f-75c54250af56'::uuid
     or s.status<>'blocked' or s.current_wave<>7 or s.attempt_count<>0
     or s.candidate_commit<>w.base_commit or s.release_run_id is not null
     or s.lease_owner is not null or s.lease_expires_at is not null
     or s.metadata->'blocker'->>'run_id'<>r.id::text
     or s.metadata->'blocker'->>'work_unit_id'<>w.id::text
     or s.metadata->'blocker'->>'type'<>'implementation_producer_error' then
    raise exception 'credit reconciliation abort: change set or blocker has changed';
  end if;

  select count(*) into v_unknowns from public.factory_tool_usage
   where tool_family in ('openai','model','llm','paid_provider') and estimated_cost is null;
  if v_unknowns<>1 then
    raise exception 'credit reconciliation abort: unrelated unknown-cost paid events present';
  end if;

  -- Historical refused-request receipt and prior unknown assessment are
  -- preserved in metadata and append-only audit before the paid gate can reopen.
  update public.factory_tool_usage
     set operation='model_call_rejected_credit_exhausted',
         estimated_cost=0,
         metadata=u.metadata || jsonb_build_object(
           'credit_reconciliation',jsonb_build_object(
             'reconciled_at',v_when,
             'request_id',v_request,
             'http_status',429,
             'error_code','credit_balance_exhausted',
             'previous_operation',u.operation,
             'previous_status',u.metadata->>'status',
             'previous_estimated_cost','unknown',
             'basis','structured provider refusal; no Response ID or token usage returned',
             'approval','human-gated-versioned-production-migration'
           ),
           'status','provider_rejected_before_response')
   where id=u.id and estimated_cost is null and operation='model_call_cost_unknown';
  if not found then
    raise exception 'credit reconciliation abort: original usage row changed concurrently';
  end if;

  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  ) values (
    s.project_id,r.task_id,r.id,'system',
    'operator-applied-gated-credit-reconciliation',
    'model.usage.credit_rejection_reconciled',
    jsonb_build_object(
      'usage_id',u.id,'change_set_id',s.id,'work_unit_id',w.id,
      'provider','openai','request_id',v_request,
      'provider_http_status',429,'provider_error_code','credit_balance_exhausted',
      'previous_usage',to_jsonb(u),
      'basis','structured provider rejection before Responses result',
      'classified_usd',0,'reconciled_at',v_when,
      'run_unblocked',false,'automatic_retry',false,
      'model_called',false
    )
  );
end
$credit_reconciliation$;
