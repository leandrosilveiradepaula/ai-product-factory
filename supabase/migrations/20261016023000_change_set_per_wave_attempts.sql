-- Change Set integration attempts are PER WAVE, never a lifetime 3-wave ceiling.
-- A failed integration retains its attempt counter and remains fail-closed.
-- An integration that advanced successfully stores the observed attempt count
-- and opens a fresh bounded (three-attempt) window for the next wave.
-- The narrow incident repair below is independently guarded and audited.
--
-- Production rollout: administrator-applied migration only after reviewed PR,
-- green CI, and human approval. Never invoked by the Factory runtime.
create or replace function public.factory_complete_change_set_integration(
  p_change_set_id uuid, p_candidate_commit text, p_changed_files jsonb
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  v_set public.factory_change_sets%rowtype;
  v_next_wave integer;
  v_status text;
  v_attempts_by_wave jsonb;
  v_metadata jsonb;
begin
  if nullif(btrim(p_candidate_commit),'') is null then
    raise exception 'candidate commit required';
  end if;
  select * into v_set
  from public.factory_change_sets
  where id=p_change_set_id
  for update;
  if not found then raise exception 'change set not found'; end if;
  if v_set.status<>'integrating' then raise exception 'change set is not integrating'; end if;
  if v_set.attempt_count<1 then
    raise exception 'successful integration must have a recorded claim attempt';
  end if;

  update public.factory_change_set_work_units
  set status='integrated',updated_at=now()
  where change_set_id=v_set.id and wave=v_set.current_wave and status='completed';

  update public.factory_tasks t
  set status='integrated',updated_at=now()
  where exists(
    select 1 from public.factory_change_set_work_units u
    where u.change_set_id=v_set.id and u.wave=v_set.current_wave
      and u.task_id=t.id and u.status='integrated'
  );

  select min(wave) into v_next_wave
  from public.factory_change_set_work_units
  where change_set_id=v_set.id and status='pending';

  if v_next_wave is not null and v_next_wave<=v_set.current_wave then
    raise exception 'next integration wave cannot move backwards';
  end if;

  v_attempts_by_wave:=coalesce(v_set.metadata->'integration_attempts_by_wave','{}'::jsonb);
  if jsonb_typeof(v_attempts_by_wave)<>'object' then
    raise exception 'invalid stored integration attempt history';
  end if;
  v_attempts_by_wave:=v_attempts_by_wave||
    jsonb_build_object(v_set.current_wave::text,v_set.attempt_count);
  v_metadata:=jsonb_set(
    coalesce(v_set.metadata,'{}'::jsonb),
    '{integration_attempts_by_wave}',v_attempts_by_wave,true
  );

  if v_next_wave is null then
    v_status:='review_ready';
    update public.factory_change_sets
    set status=v_status,candidate_commit=p_candidate_commit,
      lease_owner=null,lease_expires_at=null,
      metadata=v_metadata||jsonb_build_object(
        'integrated_files',coalesce(p_changed_files,'[]'::jsonb)
      ),
      updated_at=now()
    where id=v_set.id;
  else
    v_status:='building';
    update public.factory_change_sets
    set status=v_status,candidate_commit=p_candidate_commit,
      current_wave=v_next_wave,
      attempt_count=0,
      lease_owner=null,lease_expires_at=null,
      metadata=v_metadata,
      updated_at=now()
    where id=v_set.id;
  end if;

  return jsonb_build_object(
    'change_set_id',v_set.id,'status',v_status,
    'candidate_commit',p_candidate_commit,
    'current_wave',coalesce(v_next_wave,v_set.current_wave)
  );
end;
$function$;

revoke all on function public.factory_complete_change_set_integration(uuid,text,jsonb)
  from public,anon,authenticated;
grant execute on function public.factory_complete_change_set_integration(uuid,text,jsonb)
  to service_role;

-- Incident-specific recovery after three successful previous waves used
-- the old cumulative counter. No-op in clean DBs, already advanced sets or
-- previously recovered sets. It NEVER grants another retry to a failed
-- integration in the CURRENT wave.
do $repair$
declare
  v_set public.factory_change_sets%rowtype;
  v_target constant uuid := 'effc36be-212c-42f2-928b-97381b6d8a28';
  v_current_run constant uuid := '28497089-9415-43e8-b8e4-06bf754b5607';
  v_current_task uuid;
  v_prior_units integer;
  v_prior_waves integer;
  v_current_units integer;
  v_later_changed integer;
begin
  select * into v_set
  from public.factory_change_sets where id=v_target for update;
  if not found then return; end if;

  if exists (
    select 1 from public.factory_audit_events
    where run_id=v_current_run
      and event_type='change_set.integration.attempt_counter_rebased'
  ) then
    if v_set.attempt_count=0 or v_set.current_wave>4 then return; end if;
    raise exception 'integration repair audit exists but state differs';
  end if;

  if v_set.current_wave>4
     or v_set.status in ('review_ready','ci_pending','awaiting_release','completed')
     or (v_set.status='building' and v_set.current_wave=4 and v_set.attempt_count=0)
  then return; end if;

  if v_set.project_id<>'70515123-ecbb-4f4b-a38f-75c54250af56'::uuid
     or v_set.status<>'building'
     or v_set.current_wave<>4
     or v_set.attempt_count<>3
     or v_set.lease_owner is not null
     or v_set.lease_expires_at is not null
     or v_set.candidate_commit<>'5c6c4d6c8a23ab1a68c2487dcc32f38aa3d563af'
     or v_set.integration_branch<>'factory/change-set-effc36be'
  then
    raise exception 'integration repair aborted: unexpected project/state/lease/source';
  end if;

  select count(*),count(distinct wave)
    into v_prior_units,v_prior_waves
  from public.factory_change_set_work_units
  where change_set_id=v_target and wave<4 and status='integrated';

  if v_prior_units<>4 or v_prior_waves<>3 or exists (
    select 1 from public.factory_change_set_work_units
    where change_set_id=v_target and wave<4 and status<>'integrated'
  ) then
    raise exception 'integration repair aborted: prior integrations inconsistent';
  end if;

  select count(*),min(task_id::text)::uuid into v_current_units,v_current_task
  from public.factory_change_set_work_units
  where change_set_id=v_target and wave=4
    and run_id=v_current_run and status='completed'
    and plan_task_key='knowledge-base'
    and output_commit='dc044aaaf23f64ca6a3df818430ec1e2a1fa3df5';
  if v_current_units<>1 or
    (select count(*) from public.factory_change_set_work_units
       where change_set_id=v_target and wave=4)<>1 or
    (select status from public.factory_runs where id=v_current_run)<>'completed'
  then
    raise exception 'integration repair aborted: current wave output differs';
  end if;

  select count(*) into v_later_changed
  from public.factory_change_set_work_units
  where change_set_id=v_target and wave>4
    and (status<>'pending' or run_id is not null or output_commit is not null);
  if v_later_changed<>0 then
    raise exception 'integration repair aborted: later waves changed';
  end if;

  update public.factory_change_sets
  set attempt_count=0,updated_at=now(),
      metadata=metadata||jsonb_build_object(
        'integration_attempt_counter_repair',
        jsonb_build_object(
          'wave',4,'previous_counter',v_set.attempt_count,
          'basis','three successfully integrated prior waves',
          'recovered_at',now()
        )
      )
  where id=v_target and status='building' and current_wave=4 and attempt_count=3;
  if not found then
    raise exception 'integration repair aborted: conditional update not applied';
  end if;

  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  ) values (
    v_set.project_id,v_current_task,v_current_run,
    'system','operator-applied-versioned-migration',
    'change_set.integration.attempt_counter_rebased',
    jsonb_build_object(
      'change_set_id',v_target,'wave',4,
      'previous_attempt_count',3,'new_attempt_count',0,
      'prior_integrated_waves',3,'prior_integrated_units',4,
      'candidate_commit',v_set.candidate_commit,
      'output_commit','dc044aaaf23f64ca6a3df818430ec1e2a1fa3df5',
      'future_waves_untouched',true,'schema_fix','per_wave_counter'
    )
  );
end;
$repair$;
