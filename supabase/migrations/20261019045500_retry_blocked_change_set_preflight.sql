-- Explicit operator-only recovery for a deterministic Direct preflight blocker.
-- No blanket retries, no changes to completed/integrated work units.
create or replace function public.factory_retry_blocked_change_set_preflight(
  p_change_set_id uuid,
  p_reason text
)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_set public.factory_change_sets%rowtype;
  v_unit public.factory_change_set_work_units%rowtype;
  v_run public.factory_runs%rowtype;
  v_task public.factory_tasks%rowtype;
  v_reason text := nullif(btrim(p_reason), '');
begin
  if v_reason is null or length(v_reason)>1000 then
    raise exception 'recovery reason required (max 1000 characters)';
  end if;
  select * into v_set from public.factory_change_sets
    where id=p_change_set_id for update;
  if not found or v_set.status<>'blocked'
     or v_set.metadata->'blocker'->>'type'<>'implementation_preflight_error'
     or coalesce(v_set.metadata->'blocker'->>'reason','') not like '%repository context file too large%' then
    raise exception 'change set is not eligible for preflight recovery';
  end if;
  select * into v_unit from public.factory_change_set_work_units
    where change_set_id=p_change_set_id and status='blocked' for update;
  if not found then raise exception 'blocked work unit missing'; end if;
  if (select count(*) from public.factory_change_set_work_units
      where change_set_id=p_change_set_id and status='blocked')<>1 then
    raise exception 'recovery requires exactly one blocked work unit';
  end if;
  if v_set.metadata->'blocker'->>'run_id' is distinct from v_unit.run_id::text
     or v_set.metadata->'blocker'->>'work_unit_id' is distinct from v_unit.id::text then
    raise exception 'blocker identity mismatch';
  end if;
  select * into v_run from public.factory_runs where id=v_unit.run_id for update;
  select * into v_task from public.factory_tasks where id=v_unit.task_id for update;
  if v_run.status<>'blocked' or v_task.status<>'blocked'
     or v_run.task_id<>v_unit.task_id or v_run.attempt_count>2
     or v_run.lease_owner is not null or v_run.lease_expires_at is not null then
    raise exception 'run/task state is not safe for recovery';
  end if;
  if exists(select 1 from public.factory_change_set_work_units
            where change_set_id=p_change_set_id and status in ('running','failed')) then
    raise exception 'change set has conflicting active/failed units';
  end if;
  update public.factory_runs set status='queued',last_error=null,
    metadata=metadata||jsonb_build_object('preflight_retry_reason',v_reason,'preflight_retry_at',now())
    where id=v_run.id;
  update public.factory_tasks set status='queued_execution',updated_at=now()
    where id=v_task.id;
  update public.factory_change_set_work_units set status='queued',updated_at=now()
    where id=v_unit.id;
  update public.factory_change_sets set status='building',updated_at=now(),
    lease_owner=null,lease_expires_at=null,
    metadata=(metadata-'blocker')||jsonb_build_object(
      'last_preflight_recovery',jsonb_build_object('run_id',v_run.id,'reason',v_reason,'at',now()))
    where id=v_set.id;
  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  ) values (
    v_set.project_id,v_task.id,v_run.id,'system','preflight-recovery',
    'change_set.preflight_requeued',
    jsonb_build_object('change_set_id',v_set.id,'work_unit_id',v_unit.id,'reason',v_reason)
  );
  return jsonb_build_object('change_set_id',v_set.id,'run_id',v_run.id,
                            'work_unit_id',v_unit.id,'status','building');
end;
$$;
revoke all on function public.factory_retry_blocked_change_set_preflight(uuid,text)
  from public,anon,authenticated;
grant execute on function public.factory_retry_blocked_change_set_preflight(uuid,text)
  to service_role;
