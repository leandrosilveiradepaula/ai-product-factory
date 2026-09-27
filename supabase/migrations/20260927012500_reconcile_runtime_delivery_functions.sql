-- Reconcile runtime/delivery functions that predate complete migration-history discipline.
-- This migration is intentionally idempotent and captures the current production definitions.

create or replace function public.factory_claim_next_direct_run(p_worker_id text)
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
begin
  if nullif(btrim(p_worker_id),'') is null then
    raise exception 'worker_id is required';
  end if;

  select r.*
  into v_run
  from public.factory_runs r
  join public.factory_tasks t on t.id=r.task_id
  where r.status='queued'
    and r.execution_route='direct'
    and t.status='queued_execution'
  order by r.created_at
  for update of r skip locked
  limit 1;

  if v_run.id is null then
    return null;
  end if;

  select * into v_task
  from public.factory_tasks
  where id=v_run.task_id
  for update;

  select * into v_project
  from public.factory_projects
  where id=v_task.project_id;

  v_branch:='factory/task-'||v_task.id::text;

  update public.factory_runs
  set status='implementing',
      started_at=coalesce(started_at,now()),
      lease_owner=p_worker_id,
      lease_expires_at=now()+interval '15 minutes',
      attempt_count=attempt_count+1,
      last_error=null,
      metadata=metadata||jsonb_build_object(
        'execution_worker_id',p_worker_id,
        'execution_claimed_at',now()
      )
  where id=v_run.id;

  update public.factory_tasks
  set status='implementing',
      updated_at=now()
  where id=v_task.id;

  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  )
  values(
    v_project.id,v_task.id,v_run.id,'system',p_worker_id,
    'execution.direct.claimed',jsonb_build_object('lease_minutes',15)
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
    'human_gate_required',
    coalesce((v_run.metadata->>'human_gate_required')::boolean,false)
  );
end;
$$;

revoke all on function public.factory_claim_next_direct_run(text)
from public,anon,authenticated;
grant execute on function public.factory_claim_next_direct_run(text) to service_role;

create or replace function public.factory_bind_github_issue(
  p_run_id uuid,
  p_issue_number integer,
  p_issue_url text
)
returns void
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_task_id uuid;
  v_project_id uuid;
begin
  if p_issue_number is null or p_issue_number < 1 then
    raise exception 'invalid issue number';
  end if;

  select r.task_id,t.project_id
  into v_task_id,v_project_id
  from public.factory_runs r
  join public.factory_tasks t on t.id=r.task_id
  where r.id=p_run_id
  for update of r;

  if v_task_id is null then
    raise exception 'run not found';
  end if;

  update public.factory_runs
  set metadata=metadata||jsonb_build_object(
    'github_issue',
    jsonb_build_object('number',p_issue_number,'url',p_issue_url)
  )
  where id=p_run_id;

  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  )
  values(
    v_project_id,v_task_id,p_run_id,'system','execution-worker',
    'github.issue.bound',
    jsonb_build_object('number',p_issue_number,'url',p_issue_url)
  );
end;
$$;

revoke all on function public.factory_bind_github_issue(uuid,integer,text)
from public,anon,authenticated;
grant execute on function public.factory_bind_github_issue(uuid,integer,text)
to service_role;

create or replace function public.factory_update_run_delivery_status(
  p_run_id uuid,
  p_status text,
  p_candidate_commit text default null
)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_task_id uuid;
  v_project_id uuid;
begin
  select r.task_id,t.project_id
  into v_task_id,v_project_id
  from public.factory_runs r
  join public.factory_tasks t on t.id=r.task_id
  where r.id=p_run_id
  for update of r;

  if v_task_id is null then
    raise exception 'run not found';
  end if;

  update public.factory_runs
  set status=p_status,
      candidate_commit=coalesce(p_candidate_commit,candidate_commit),
      finished_at=case
        when p_status in ('completed','failed','merged') then now()
        else finished_at
      end
  where id=p_run_id;

  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  )
  values(
    v_project_id,v_task_id,p_run_id,'system','github-loop',
    'run.status.updated',
    jsonb_build_object(
      'status',p_status,
      'candidate_commit',p_candidate_commit
    )
  );

  return jsonb_build_object(
    'run_id',p_run_id,
    'task_id',v_task_id,
    'status',p_status,
    'candidate_commit',p_candidate_commit
  );
end;
$$;

revoke all on function public.factory_update_run_delivery_status(uuid,text,text)
from public,anon,authenticated;
grant execute on function public.factory_update_run_delivery_status(uuid,text,text)
to service_role;

create or replace function public.factory_record_delivery_tool_usage(
  p_run_id uuid,
  p_tool_family text,
  p_operation text,
  p_usage_units numeric,
  p_estimated_cost numeric,
  p_metadata jsonb
)
returns bigint
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_id bigint;
begin
  if not exists(select 1 from public.factory_runs where id=p_run_id) then
    raise exception 'run not found';
  end if;

  insert into public.factory_tool_usage(
    run_id,tool_family,operation,usage_units,estimated_cost,metadata
  )
  values(
    p_run_id,p_tool_family,p_operation,p_usage_units,p_estimated_cost,
    coalesce(p_metadata,'{}'::jsonb)
  )
  returning id into v_id;

  return v_id;
end;
$$;

revoke all on function public.factory_record_delivery_tool_usage(
  uuid,text,text,numeric,numeric,jsonb
) from public,anon,authenticated;
grant execute on function public.factory_record_delivery_tool_usage(
  uuid,text,text,numeric,numeric,jsonb
) to service_role;
