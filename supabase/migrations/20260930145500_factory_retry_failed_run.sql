create or replace function public.factory_retry_failed_run(
  p_source_run_id uuid,
  p_reason text
)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_source public.factory_runs%rowtype;
  v_task public.factory_tasks%rowtype;
  v_project_id uuid;
  v_new_run_id uuid;
  v_existing_retry_id uuid;
  v_task_status text;
  v_reason text;
  v_metadata jsonb;
begin
  v_reason:=nullif(btrim(p_reason),'');
  if v_reason is null then raise exception 'retry reason is required'; end if;
  if length(v_reason)>1000 then raise exception 'retry reason is too long'; end if;

  select * into v_source from public.factory_runs where id=p_source_run_id for update;
  if not found then raise exception 'source run not found'; end if;
  if v_source.status<>'failed' then raise exception 'source run is not failed'; end if;

  select id into v_existing_retry_id
  from public.factory_runs
  where task_id=v_source.task_id
    and metadata->>'retry_of'=p_source_run_id::text
  order by created_at desc limit 1;
  if v_existing_retry_id is not null then raise exception 'retry already exists for source run'; end if;

  select * into v_task from public.factory_tasks where id=v_source.task_id for update;
  if not found then raise exception 'source task not found'; end if;
  v_project_id:=v_task.project_id;
  v_task_status:=case when v_source.execution_route is null or v_source.metadata ? 'stages' then 'queued' else 'queued_execution' end;

  v_metadata:=(v_source.metadata
    - 'worker_id' - 'claimed_at' - 'execution_worker_id' - 'execution_claimed_at' - 'error'
  ) || jsonb_build_object(
    'retry_of',p_source_run_id::text,
    'retry_reason',v_reason,
    'retry_source_commit',v_source.source_commit,
    'retry_queued_at',now()
  );

  insert into public.factory_runs(
    task_id,status,execution_route,source_commit,candidate_commit,branch_name,
    metadata,lease_owner,lease_expires_at,attempt_count,last_error
  ) values(
    v_source.task_id,'queued',v_source.execution_route,v_source.source_commit,null,null,
    v_metadata,null,null,0,null
  ) returning id into v_new_run_id;

  update public.factory_tasks set status=v_task_status,updated_at=now() where id=v_source.task_id;

  insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  values(
    v_project_id,v_source.task_id,v_new_run_id,'system','runtime-retry','run.retry_queued',
    jsonb_build_object(
      'source_run_id',p_source_run_id,
      'reason',v_reason,
      'source_commit',v_source.source_commit,
      'execution_route',v_source.execution_route
    )
  );

  return jsonb_build_object(
    'source_run_id',p_source_run_id,
    'run_id',v_new_run_id,
    'task_id',v_source.task_id,
    'status','queued',
    'task_status',v_task_status,
    'execution_route',v_source.execution_route,
    'source_commit',v_source.source_commit
  );
end;
$$;

revoke all on function public.factory_retry_failed_run(uuid,text) from public,anon,authenticated;
grant execute on function public.factory_retry_failed_run(uuid,text) to service_role;