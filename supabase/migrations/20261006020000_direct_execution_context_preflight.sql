create or replace function public.factory_block_change_set_work_unit(
  p_run_id uuid,
  p_reason text,
  p_blocker_type text default 'implementation_blocked'
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_unit public.factory_change_set_work_units%rowtype;
  v_set public.factory_change_sets%rowtype;
  v_task public.factory_tasks%rowtype;
  v_reason text;
  v_blocker_type text;
begin
  v_reason:=left(btrim(coalesce(p_reason,'')),1000);
  v_blocker_type:=left(btrim(coalesce(p_blocker_type,'')),120);
  if v_reason='' then raise exception 'blocker reason is required'; end if;
  if v_blocker_type='' then raise exception 'blocker type is required'; end if;

  select * into v_unit
  from public.factory_change_set_work_units
  where run_id=p_run_id
  for update;
  if not found then raise exception 'change-set work unit not found'; end if;

  select * into v_set
  from public.factory_change_sets
  where id=v_unit.change_set_id
  for update;
  if not found then raise exception 'change set not found'; end if;

  select * into v_task
  from public.factory_tasks
  where id=v_unit.task_id
  for update;
  if not found then raise exception 'task not found'; end if;

  update public.factory_change_set_work_units
  set status='blocked',updated_at=now()
  where id=v_unit.id
    and status in ('pending','queued','running','failed');

  update public.factory_runs
  set status='blocked',
      finished_at=coalesce(finished_at,now()),
      last_error=v_reason,
      lease_owner=null,
      lease_expires_at=null,
      metadata=metadata||jsonb_build_object(
        'implementation_blocked',true,
        'blocker_type',v_blocker_type,
        'blocker_reason',v_reason
      )
  where id=p_run_id
    and status not in ('completed','cancelled');

  update public.factory_tasks
  set status='blocked',updated_at=now()
  where id=v_task.id
    and status not in ('completed','cancelled');

  update public.factory_change_sets
  set status='blocked',
      lease_owner=null,
      lease_expires_at=null,
      metadata=metadata||jsonb_build_object(
        'blocker',jsonb_build_object(
          'type',v_blocker_type,
          'reason',v_reason,
          'run_id',p_run_id,
          'work_unit_id',v_unit.id,
          'recorded_at',now()
        )
      ),
      updated_at=now()
  where id=v_set.id
    and status not in ('completed','superseded');

  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  )
  values(
    v_set.project_id,v_task.id,p_run_id,
    'system','change-set-builder','change_set.work_unit.blocked',
    jsonb_build_object(
      'change_set_id',v_set.id,
      'work_unit_id',v_unit.id,
      'blocker_type',v_blocker_type,
      'reason',v_reason
    )
  );

  return jsonb_build_object(
    'change_set_id',v_set.id,
    'work_unit_id',v_unit.id,
    'run_id',p_run_id,
    'status','blocked',
    'blocker_type',v_blocker_type,
    'reason',v_reason
  );
end;
$$;

revoke all on function public.factory_block_change_set_work_unit(uuid,text,text)
from public,anon,authenticated;
grant execute on function public.factory_block_change_set_work_unit(uuid,text,text)
to service_role;


create or replace function public.factory_recover_change_sets(p_max_attempts integer default 3)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_requeued integer:=0;
  v_stale_direct_requeued integer:=0;
  v_blocked integer:=0;
  v_integrators integer:=0;
  v_blocked_integrations integer:=0;
  v_row record;
begin
  if p_max_attempts<1 or p_max_attempts>10 then raise exception 'invalid max attempts'; end if;

  for v_row in
    select
      u.id as work_unit_id,
      u.task_id,
      u.change_set_id,
      r.id as run_id,
      t.project_id
    from public.factory_change_set_work_units u
    join public.factory_runs r on r.id=u.run_id
    join public.factory_tasks t on t.id=u.task_id
    where u.status='running'
      and r.status='implementing'
      and r.lease_expires_at<=now()
      and r.attempt_count<p_max_attempts
    order by r.lease_expires_at,u.id
    for update of u
  loop
    update public.factory_runs
    set status='queued',
        lease_owner=null,
        lease_expires_at=null,
        metadata=metadata||jsonb_build_object(
          'execution_recovered',true,
          'execution_recovered_at',now(),
          'execution_recovery_reason','expired_implementing_lease'
        )
    where id=v_row.run_id
      and status='implementing';

    update public.factory_tasks
    set status='queued_execution',updated_at=now()
    where id=v_row.task_id
      and status='implementing';

    update public.factory_change_set_work_units
    set status='queued',updated_at=now()
    where id=v_row.work_unit_id
      and status='running';

    insert into public.factory_audit_events(
      project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
    )
    values(
      v_row.project_id,v_row.task_id,v_row.run_id,
      'system','change-set-recovery','execution.direct.requeued_after_expired_lease',
      jsonb_build_object(
        'change_set_id',v_row.change_set_id,
        'work_unit_id',v_row.work_unit_id,
        'reason','expired_implementing_lease'
      )
    );
    v_stale_direct_requeued:=v_stale_direct_requeued+1;
  end loop;

  update public.factory_change_set_work_units u
  set status='queued',updated_at=now()
  from public.factory_runs r
  where u.run_id=r.id and u.status='running' and r.status='queued';
  get diagnostics v_requeued=row_count;

  update public.factory_change_set_work_units u
  set status='failed',updated_at=now()
  from public.factory_runs r
  where u.run_id=r.id and u.status in ('running','queued') and r.status='failed';

  update public.factory_change_sets s
  set status='blocked',lease_owner=null,lease_expires_at=null,updated_at=now(),
      metadata=metadata||jsonb_build_object('blocker','builder_retry_exhausted')
  where s.status in ('planned','building','integrating')
    and exists(
      select 1 from public.factory_change_set_work_units u
      where u.change_set_id=s.id and u.status in ('failed','blocked')
    );
  get diagnostics v_blocked=row_count;

  update public.factory_change_sets
  set status='building',lease_owner=null,lease_expires_at=null,updated_at=now()
  where status='integrating' and lease_expires_at<=now() and attempt_count<p_max_attempts;
  get diagnostics v_integrators=row_count;

  update public.factory_change_sets
  set status='blocked',lease_owner=null,lease_expires_at=null,updated_at=now(),
      metadata=metadata||jsonb_build_object('blocker','integration_retry_exhausted')
  where status='integrating' and lease_expires_at<=now() and attempt_count>=p_max_attempts;
  get diagnostics v_blocked_integrations=row_count;
  v_blocked:=v_blocked+v_blocked_integrations;

  return jsonb_build_object(
    'work_units_requeued',v_requeued,
    'stale_direct_requeued',v_stale_direct_requeued,
    'integrations_requeued',v_integrators,
    'blocked',v_blocked
  );
end;
$$;

revoke all on function public.factory_recover_change_sets(integer)
from public,anon,authenticated;
grant execute on function public.factory_recover_change_sets(integer)
to service_role;
