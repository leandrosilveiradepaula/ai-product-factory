create or replace function public.factory_claim_next_codex_run(p_worker_id text)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_run public.factory_runs%rowtype;
  v_task public.factory_tasks%rowtype;
  v_project public.factory_projects%rowtype;
  v_branch text;
  v_codex_level integer;
begin
  if nullif(btrim(p_worker_id),'') is null then
    raise exception 'worker_id is required';
  end if;

  select r.*
  into v_run
  from public.factory_runs r
  join public.factory_tasks t on t.id=r.task_id
  where r.status='queued'
    and r.execution_route='codex'
    and t.status='queued_execution'
  order by r.created_at
  for update of r skip locked
  limit 1;

  if v_run.id is null then
    return null;
  end if;

  select *
  into v_task
  from public.factory_tasks
  where id=v_run.task_id
  for update;

  select *
  into v_project
  from public.factory_projects
  where id=v_task.project_id;

  v_branch:='factory/task-'||v_task.id::text;
  v_codex_level:=greatest(1,coalesce((v_run.metadata->>'codex_level')::integer,1));

  update public.factory_runs
  set status='implementing',
      started_at=coalesce(started_at,now()),
      lease_owner=p_worker_id,
      lease_expires_at=now()+interval '15 minutes',
      attempt_count=attempt_count+1,
      metadata=metadata||jsonb_build_object(
        'execution_worker_id',p_worker_id,
        'execution_claimed_at',now()
      )
  where id=v_run.id
    and status='queued'
    and execution_route='codex';

  if not found then
    return null;
  end if;

  update public.factory_tasks
  set status='implementing',
      updated_at=now()
  where id=v_task.id
    and status='queued_execution';

  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  )
  values(
    v_project.id,v_task.id,v_run.id,'system',p_worker_id,'execution.codex.claimed',
    jsonb_build_object('codex_level',v_codex_level)
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
    'codex_level',v_codex_level,
    'human_gate_required',coalesce((v_run.metadata->>'human_gate_required')::boolean,false)
  );
end;
$$;

revoke all on function public.factory_claim_next_codex_run(text) from public,anon,authenticated;
grant execute on function public.factory_claim_next_codex_run(text) to service_role;

create or replace function public.factory_record_codex_invocation(
  p_run_id uuid,
  p_reported_usage jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_usage public.factory_codex_usage%rowtype;
  v_task_id uuid;
  v_project_id uuid;
begin
  select r.task_id,t.project_id
  into v_task_id,v_project_id
  from public.factory_runs r
  join public.factory_tasks t on t.id=r.task_id
  where r.id=p_run_id
    and r.execution_route='codex'
  for update of r;

  if v_task_id is null then
    raise exception 'codex run not found';
  end if;

  select u.*
  into v_usage
  from public.factory_codex_usage u
  where u.run_id=p_run_id
  order by u.created_at desc,u.id desc
  for update
  limit 1;

  if v_usage.id is null then
    raise exception 'codex policy ledger row not found';
  end if;

  update public.factory_codex_usage
  set invocation_count=invocation_count+1,
      reported_usage=coalesce(reported_usage,'{}'::jsonb)||coalesce(p_reported_usage,'{}'::jsonb)
  where id=v_usage.id
  returning * into v_usage;

  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  )
  values(
    v_project_id,v_task_id,p_run_id,'system','codex-worker','execution.codex.invoked',
    jsonb_build_object(
      'policy_level',v_usage.policy_level,
      'invocation_count',v_usage.invocation_count
    )
  );

  return jsonb_build_object(
    'run_id',p_run_id,
    'policy_level',v_usage.policy_level,
    'invocation_count',v_usage.invocation_count
  );
end;
$$;

revoke all on function public.factory_record_codex_invocation(uuid,jsonb) from public,anon,authenticated;
grant execute on function public.factory_record_codex_invocation(uuid,jsonb) to service_role;
