create or replace function public.factory_claim_next_run(p_worker_id text)
returns jsonb
language plpgsql
set search_path=''
as $$
declare
  v_run public.factory_runs%rowtype;
  v_task public.factory_tasks%rowtype;
  v_project public.factory_projects%rowtype;
  v_spec jsonb;
  v_snapshot jsonb;
  v_recent_tasks jsonb;
  v_github_access jsonb;
  v_pending_gates jsonb;
begin
  if nullif(btrim(p_worker_id),'') is null then raise exception 'worker_id is required'; end if;

  select r.* into v_run
  from public.factory_runs r
  join public.factory_tasks t on t.id=r.task_id
  where r.status in ('created','queued') and t.status='queued'
  order by r.created_at
  for update of r skip locked
  limit 1;
  if v_run.id is null then return null; end if;

  select * into v_task from public.factory_tasks where id=v_run.task_id for update;
  select * into v_project from public.factory_projects where id=v_task.project_id;

  select ps.spec into v_spec
  from public.factory_product_specs ps
  where ps.project_id=v_project.id
  order by ps.version desc
  limit 1;

  select jsonb_build_object(
    'id',s.id,
    'observed_stage',s.observed_stage,
    'summary',s.summary,
    'evidence',s.evidence,
    'gaps',s.gaps,
    'constraints',s.constraints,
    'source_status',s.source_status,
    'created_at',s.created_at
  ) into v_snapshot
  from public.factory_project_state_snapshots s
  where s.project_id=v_project.id
  order by s.created_at desc
  limit 1;

  select coalesce(jsonb_agg(jsonb_build_object(
    'external_key',x.external_key,
    'title',x.title,
    'status',x.status,
    'updated_at',x.updated_at
  ) order by x.updated_at desc),'[]'::jsonb)
  into v_recent_tasks
  from (
    select t.external_key,t.title,t.status,t.updated_at
    from public.factory_tasks t
    where t.project_id=v_project.id
      and t.id<>v_task.id
    order by t.updated_at desc
    limit 25
  ) x;

  select jsonb_build_object(
    'auth_mode',a.auth_mode,
    'status',a.status,
    'required_capabilities',a.required_capabilities,
    'observed_capabilities',a.observed_capabilities,
    'last_verified_at',a.last_verified_at,
    'last_error',a.last_error
  )
  into v_github_access
  from public.factory_project_github_access a
  where a.project_id=v_project.id
  limit 1;

  select coalesce(jsonb_agg(jsonb_build_object(
    'gate_type',x.gate_type,
    'status',x.status,
    'requested_at',x.requested_at,
    'task_external_key',x.external_key,
    'task_title',x.title
  ) order by x.requested_at desc),'[]'::jsonb)
  into v_pending_gates
  from (
    select g.gate_type,g.status,g.requested_at,t.external_key,t.title
    from public.factory_human_gates g
    join public.factory_runs r on r.id=g.run_id
    join public.factory_tasks t on t.id=r.task_id
    where t.project_id=v_project.id and g.status='pending'
    order by g.requested_at desc
    limit 25
  ) x;

  update public.factory_runs
  set status='running',
      started_at=coalesce(started_at,now()),
      lease_owner=p_worker_id,
      lease_expires_at=now()+interval '15 minutes',
      attempt_count=attempt_count+1,
      last_error=null,
      metadata=metadata||jsonb_build_object('worker_id',p_worker_id,'claimed_at',now())
  where id=v_run.id;

  update public.factory_tasks set status='running',updated_at=now() where id=v_task.id;

  insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  values(v_project.id,v_task.id,v_run.id,'system',p_worker_id,'run.claimed',jsonb_build_object('lease_minutes',15));

  return jsonb_build_object(
    'run_id',v_run.id,
    'task_id',v_task.id,
    'project_id',v_project.id,
    'project_key',v_project.project_key,
    'stages',coalesce(v_run.metadata->'stages','[]'::jsonb),
    'context',jsonb_build_object(
      'task',v_task.description,
      'manifest',v_project.manifest,
      'intake_spec',coalesce(v_spec,'{}'::jsonb),
      'state_snapshot',v_snapshot,
      'current_state_facts',jsonb_build_object(
        'recent_tasks',v_recent_tasks,
        'github_access',coalesce(v_github_access,'{}'::jsonb),
        'pending_human_gates',v_pending_gates
      )
    )
  );
end;
$$;

revoke all on function public.factory_claim_next_run(text)
from public,anon,authenticated;
grant execute on function public.factory_claim_next_run(text)
to service_role;
