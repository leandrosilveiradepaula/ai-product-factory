create or replace function public.factory_claim_next_agent_direct_run(
  p_worker_id text,
  p_agent_key text default null,
  p_run_id uuid default null
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_run public.factory_runs%rowtype;
  v_task public.factory_tasks%rowtype;
  v_project public.factory_projects%rowtype;
  v_unit public.factory_change_set_work_units%rowtype;
  v_branch text;
  v_agent_key text;
  v_assignment_id uuid;
begin
  if nullif(btrim(p_worker_id),'') is null then raise exception 'worker_id is required';end if;

  select r.* into v_run
  from public.factory_runs r
  join public.factory_tasks t on t.id=r.task_id
  join public.factory_run_agent_assignments ra on ra.run_id=r.id and ra.status in ('assigned','claimed')
  join public.factory_agents a2 on a2.id=ra.agent_id and a2.is_active=true
  where r.status='queued' and r.execution_route='direct' and t.status='queued_execution'
    and (p_agent_key is null or a2.agent_key=p_agent_key)
    and (p_run_id is null or r.id=p_run_id)
  order by r.created_at
  for update of r skip locked
  limit 1;

  if v_run.id is null then return null;end if;

  select ra.id,a2.agent_key into v_assignment_id,v_agent_key
  from public.factory_run_agent_assignments ra
  join public.factory_agents a2 on a2.id=ra.agent_id and a2.is_active=true
  where ra.run_id=v_run.id and ra.status in ('assigned','claimed')
  order by ra.assigned_at desc,ra.id desc
  limit 1;

  if v_assignment_id is null or v_agent_key is null then
    raise exception 'active agent assignment not found';
  end if;

  select * into v_task from public.factory_tasks where id=v_run.task_id for update;
  select * into v_project from public.factory_projects where id=v_task.project_id;
  select * into v_unit from public.factory_change_set_work_units where run_id=v_run.id;
  if v_unit.id is null then raise exception 'change-set work unit not found'; end if;

  v_branch:='factory/cs-'||substr(v_unit.change_set_id::text,1,8)||'/'||
    regexp_replace(v_unit.plan_task_key,'[^a-zA-Z0-9_-]+','-','g');

  update public.factory_runs
  set status='implementing',
      started_at=coalesce(started_at,now()),
      lease_owner=p_worker_id,
      lease_expires_at=now()+interval '15 minutes',
      attempt_count=attempt_count+1,
      last_error=null,
      metadata=metadata||jsonb_build_object(
        'execution_worker_id',p_worker_id,
        'execution_claimed_at',now(),
        'agent_key',v_agent_key
      )
  where id=v_run.id;

  update public.factory_tasks
  set status='implementing',updated_at=now()
  where id=v_task.id;

  update public.factory_run_agent_assignments
  set status='claimed',claimed_at=coalesce(claimed_at,now())
  where id=v_assignment_id
    and status in ('assigned','claimed');

  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  )
  values(
    v_project.id,v_task.id,v_run.id,'agent',v_agent_key,'execution.direct.claimed',
    jsonb_build_object(
      'lease_minutes',15,
      'worker_id',p_worker_id,
      'change_set_id',v_unit.change_set_id,
      'work_unit_id',v_unit.id,
      'assignment_id',v_assignment_id
    )
  );

  return jsonb_build_object(
    'run_id',v_run.id,
    'task_id',v_task.id,
    'project_key',v_project.project_key,
    'repository',v_project.repository,
    'issue_number',null,
    'title',v_task.title,
    'description',v_task.description,
    'branch',v_branch,
    'agent_key',v_agent_key,
    'change_set_id',v_unit.change_set_id,
    'work_unit_id',v_unit.id,
    'wave',v_unit.wave,
    'human_gate_required',coalesce((v_run.metadata->>'human_gate_required')::boolean,false)
  );
end;
$$;

revoke all on function public.factory_claim_next_agent_direct_run(text,text,uuid)
from public,anon,authenticated;
grant execute on function public.factory_claim_next_agent_direct_run(text,text,uuid)
to service_role;


create or replace function public.factory_claim_next_agent_codex_run(
  p_worker_id text,
  p_agent_key text default null,
  p_run_id uuid default null
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_run public.factory_runs%rowtype;
  v_task public.factory_tasks%rowtype;
  v_project public.factory_projects%rowtype;
  v_unit public.factory_change_set_work_units%rowtype;
  v_branch text;
  v_agent_key text;
  v_assignment_id uuid;
begin
  if nullif(btrim(p_worker_id),'') is null then raise exception 'worker_id is required';end if;

  select r.* into v_run
  from public.factory_runs r
  join public.factory_tasks t on t.id=r.task_id
  join public.factory_run_agent_assignments ra on ra.run_id=r.id and ra.status in ('assigned','claimed')
  join public.factory_agents a2 on a2.id=ra.agent_id and a2.is_active=true
  where r.status='queued' and r.execution_route='codex' and t.status='queued_execution'
    and (p_agent_key is null or a2.agent_key=p_agent_key)
    and (p_run_id is null or r.id=p_run_id)
  order by r.created_at
  for update of r skip locked
  limit 1;

  if v_run.id is null then return null;end if;

  select ra.id,a2.agent_key into v_assignment_id,v_agent_key
  from public.factory_run_agent_assignments ra
  join public.factory_agents a2 on a2.id=ra.agent_id and a2.is_active=true
  where ra.run_id=v_run.id and ra.status in ('assigned','claimed')
  order by ra.assigned_at desc,ra.id desc
  limit 1;

  if v_assignment_id is null or v_agent_key is null then
    raise exception 'active agent assignment not found';
  end if;

  select * into v_task from public.factory_tasks where id=v_run.task_id for update;
  select * into v_project from public.factory_projects where id=v_task.project_id;
  select * into v_unit from public.factory_change_set_work_units where run_id=v_run.id;
  if v_unit.id is null then raise exception 'change-set work unit not found'; end if;

  v_branch:='factory/cs-'||substr(v_unit.change_set_id::text,1,8)||'/'||
    regexp_replace(v_unit.plan_task_key,'[^a-zA-Z0-9_-]+','-','g');

  update public.factory_runs
  set status='implementing',
      started_at=coalesce(started_at,now()),
      lease_owner=p_worker_id,
      lease_expires_at=now()+interval '15 minutes',
      attempt_count=attempt_count+1,
      last_error=null,
      metadata=metadata||jsonb_build_object(
        'execution_worker_id',p_worker_id,
        'execution_claimed_at',now(),
        'agent_key',v_agent_key
      )
  where id=v_run.id;

  update public.factory_tasks
  set status='implementing',updated_at=now()
  where id=v_task.id;

  update public.factory_run_agent_assignments
  set status='claimed',claimed_at=coalesce(claimed_at,now())
  where id=v_assignment_id
    and status in ('assigned','claimed');

  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  )
  values(
    v_project.id,v_task.id,v_run.id,'agent',v_agent_key,'execution.codex.claimed',
    jsonb_build_object(
      'lease_minutes',15,
      'worker_id',p_worker_id,
      'change_set_id',v_unit.change_set_id,
      'work_unit_id',v_unit.id,
      'assignment_id',v_assignment_id
    )
  );

  return jsonb_build_object(
    'run_id',v_run.id,
    'task_id',v_task.id,
    'project_key',v_project.project_key,
    'repository',v_project.repository,
    'issue_number',null,
    'title',v_task.title,
    'description',v_task.description,
    'branch',v_branch,
    'agent_key',v_agent_key,
    'change_set_id',v_unit.change_set_id,
    'work_unit_id',v_unit.id,
    'wave',v_unit.wave,
    'codex_level',coalesce((v_run.metadata->>'codex_level')::int,1),
    'human_gate_required',coalesce((v_run.metadata->>'human_gate_required')::boolean,false)
  );
end;
$$;

revoke all on function public.factory_claim_next_agent_codex_run(text,text,uuid)
from public,anon,authenticated;
grant execute on function public.factory_claim_next_agent_codex_run(text,text,uuid)
to service_role;
