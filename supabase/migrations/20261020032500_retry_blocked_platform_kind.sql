-- Operator-authorized, one-work-unit recovery of a *real* platform-kind
-- preflight failure. Inert when applied: must be invoked separately after
-- the Factory runtime fix has passed CI and merged. No model calls or Start.
create or replace function public.factory_retry_blocked_platform_kind(
  p_change_set_id uuid,
  p_expected_run_id uuid,
  p_project_key text,
  p_expected_generation bigint,
  p_reason text
)
returns jsonb language plpgsql
security invoker
set search_path=''
as $factory$
declare
  v_set public.factory_change_sets%rowtype;
  v_unit public.factory_change_set_work_units%rowtype;
  v_run public.factory_runs%rowtype;
  v_task public.factory_tasks%rowtype;
  v_project public.factory_projects%rowtype;
  v_control public.factory_project_execution_controls%rowtype;
  v_reason text := nullif(btrim(p_reason),'');
begin
  if p_change_set_id is null or p_expected_run_id is null
     or nullif(btrim(p_project_key),'') is null
     or length(p_project_key)>150
     or p_expected_generation is null or p_expected_generation<1
     or v_reason is null or length(v_reason)>300
  then
    raise exception 'invalid platform-kind recovery identity';
  end if;

  select * into v_set from public.factory_change_sets
    where id=p_change_set_id for update;
  if not found or v_set.status<>'blocked'
     or v_set.current_wave<>1
     or v_set.source_commit is not null or v_set.candidate_commit is not null
     or v_set.integration_branch is not null
     or v_set.release_run_id is not null
     or v_set.lease_owner is not null or v_set.lease_expires_at is not null
     or v_set.attempt_count>1
     or v_set.metadata->'blocker'->>'type'
         is distinct from 'implementation_preflight_error'
     or v_set.metadata->'blocker'->>'reason'
         is distinct from 'PermissionError: unrecognized project kind'
     or v_set.metadata->'blocker'->>'run_id' is distinct from p_expected_run_id::text
  then
    raise exception 'change set not eligible for platform-kind recovery';
  end if;

  select * into v_project from public.factory_projects
    where id=v_set.project_id for share;
  if not found or v_project.is_active is not true
     or v_project.project_kind is distinct from 'platform'
     or v_project.project_key is distinct from p_project_key
     or nullif(v_project.repository,'') is null
     or v_project.manifest->'delivery_target' is not null
  then
    raise exception 'project platform identity is not eligible';
  end if;

  select * into v_control from public.factory_project_execution_controls
    where project_id=v_project.id for share;
  if not found or v_control.state is distinct from 'running'
     or v_control.generation is distinct from p_expected_generation
  then
    raise exception 'project execution generation changed or is stopped';
  end if;

  if (select count(*) from public.factory_change_set_work_units
      where change_set_id=v_set.id)<>1
  then
    raise exception 'recovery requires one blocked work unit';
  end if;
  select * into v_unit from public.factory_change_set_work_units
    where change_set_id=v_set.id for update;
  if not found or v_unit.status<>'blocked' or v_unit.wave<>1
     or v_unit.run_id is distinct from p_expected_run_id
     or v_unit.base_commit is not null
     or v_unit.branch_name is not null
     or v_unit.output_commit is not null
     or v_unit.changed_files is distinct from '[]'::jsonb
     or v_set.metadata->'blocker'->>'work_unit_id'
         is distinct from v_unit.id::text
  then
    raise exception 'blocked work unit identity or uncommitted state changed';
  end if;

  select * into v_run from public.factory_runs
    where id=p_expected_run_id for update;
  select * into v_task from public.factory_tasks
    where id=v_unit.task_id for update;
  if v_run.id is null or v_task.id is null
     or v_run.status<>'blocked' or v_task.status<>'blocked'
     or v_run.task_id is distinct from v_task.id
     or v_task.id is distinct from v_unit.task_id
     or v_task.project_id is distinct from v_project.id
     or v_task.parent_task_id is distinct from v_set.root_task_id
     or v_run.lease_owner is not null or v_run.lease_expires_at is not null
     or v_run.attempt_count>2
     or v_run.source_commit is not null
     or v_run.candidate_commit is not null
     or v_run.branch_name is not null
     or v_run.last_error is distinct from 'PermissionError: unrecognized project kind'
     or v_run.metadata->>'execution_generation'
         is distinct from v_control.generation::text
  then
    raise exception 'run/task is no longer eligible for safe recovery';
  end if;

  -- The old Product Stage and paid model results are never rerun. Only this
  -- blocked Direct work-unit is requeued. The next Direct worker must still
  -- check epoch, source main SHA, write scopes, cost ledger and GitHub policy.
  update public.factory_runs
    set status='queued',last_error=null
    where id=v_run.id;
  update public.factory_tasks
    set status='queued_execution',updated_at=now()
    where id=v_task.id;
  update public.factory_change_set_work_units
    set status='queued',updated_at=now()
    where id=v_unit.id;
  update public.factory_change_sets
    set status='building',updated_at=now(),
      metadata=(metadata-'blocker') || jsonb_build_object(
        'platform_kind_recovery',
        jsonb_build_object(
          'reason',v_reason,'run_id',v_run.id,
          'generation',v_control.generation,'at',now()
        )
      )
    where id=v_set.id;
  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  ) values (
    v_project.id,v_task.id,v_run.id,'system','platform-kind-recovery',
    'change_set.platform_kind_requeued',
    jsonb_build_object(
      'change_set_id',v_set.id,'work_unit_id',v_unit.id,
      'generation',v_control.generation,'reason',v_reason
    )
  );
  return jsonb_build_object(
    'change_set_id',v_set.id,'work_unit_id',v_unit.id,
    'run_id',v_run.id,'status','building',
    'generation',v_control.generation
  );
end;
$factory$;
revoke all on function public.factory_retry_blocked_platform_kind(uuid,uuid,text,bigint,text)
  from public,anon,authenticated;
grant execute on function public.factory_retry_blocked_platform_kind(uuid,uuid,text,bigint,text)
  to service_role;
