-- Harden Codex automatic assignment and claim after mode isolation.
-- No backfill, no new work, no secrets, no entitlement or release changes.
-- Only already assigned, compatible, active agents may claim automatic runs.

CREATE OR REPLACE FUNCTION public.factory_schedule_eligible_codex_run(p_run_id uuid DEFAULT NULL::uuid, p_project_key text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY INVOKER
 SET search_path TO ''
AS $function$
declare
 v_run public.factory_runs%rowtype;
 v_task public.factory_tasks%rowtype;
 v_assignment jsonb;
 v_preferred_role text;
 v_codex_agent_key text;
begin
 select r.* into v_run
 from public.factory_runs r
 join public.factory_tasks t on t.id=r.task_id
 join public.factory_projects proj on proj.id=t.project_id
 where r.status='queued'
   and r.execution_route='codex'
   and r.metadata->>'codex_execution_mode'='automatic'
   and t.status='queued_execution'
   and proj.is_active=true
   and (p_run_id is null or r.id=p_run_id)
   and (p_project_key is null or proj.project_key=btrim(p_project_key))
   and not exists (
     select 1 from public.factory_run_agent_assignments ra
     where ra.run_id=r.id and ra.status in ('assigned','claimed')
   )
 order by r.created_at,r.id
 for update of r skip locked
 limit 1;
 if v_run.id is null then return null; end if;
 select * into v_task from public.factory_tasks where id=v_run.task_id for update;
 if v_task.status<>'queued_execution' then return null; end if;

 v_preferred_role:=coalesce(nullif(btrim(v_task.agent_role),''),'development');
 select a.agent_key into v_codex_agent_key
 from public.factory_agents a
 where a.is_active=true and a.allowed_tools ?& array['codex','github_write']
   and (a.agent_key=v_preferred_role or a.role=v_preferred_role)
   and not exists (
     select 1 from jsonb_array_elements_text(coalesce(v_task.required_capabilities,'[]'::jsonb)) cap(value)
     where not (a.capabilities ? cap.value)
   )
 order by case when a.agent_key=v_preferred_role then 0 else 1 end,a.agent_key
 limit 1;
 if v_codex_agent_key is null then return null; end if;
 v_assignment:=public.factory_schedule_run_agent(
   v_run.id,v_codex_agent_key,
   coalesce(v_task.required_capabilities,'[]'::jsonb),
   coalesce(v_task.scope_keys,'[]'::jsonb),900
 );
 if v_assignment is null then return null; end if;
 -- The general allocator can select by role as well as exact agent key.
 -- Fail the entire transaction if that selection changes agent or tools.
 if v_assignment->>'agent_key' is distinct from v_codex_agent_key
    or not (coalesce(v_assignment->'allowed_tools','[]'::jsonb) ?& array['codex','github_write']) then
   raise exception 'Codex allocator changed selected agent or required tools';
 end if;
 insert into public.factory_audit_events(
   project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
 ) values (
   v_task.project_id,v_task.id,v_run.id,'system','route-safe-codex-scheduler',
   'agent.codex_auto.assigned',v_assignment
 );
 return v_assignment || jsonb_build_object('run_id',v_run.id,'task_id',v_task.id);
end;
$function$;

CREATE OR REPLACE FUNCTION public.factory_claim_next_agent_codex_run(p_worker_id text, p_agent_key text DEFAULT NULL::text, p_run_id uuid DEFAULT NULL::uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY INVOKER
 SET search_path TO ''
AS $function$
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
  join public.factory_projects proj on proj.id=t.project_id and proj.is_active=true
  join public.factory_run_agent_assignments ra on ra.run_id=r.id and ra.status in ('assigned','claimed')
  join public.factory_agents a2 on a2.id=ra.agent_id and a2.is_active=true
    and a2.allowed_tools ?& array['codex','github_write']
  where r.status='queued' and r.execution_route='codex'
    and r.metadata->>'codex_execution_mode'='automatic' and t.status='queued_execution'
    and (p_agent_key is null or a2.agent_key=p_agent_key)
    and (p_run_id is null or r.id=p_run_id)
    and not exists (
      select 1 from jsonb_array_elements_text(coalesce(t.required_capabilities,'[]'::jsonb)) cap(value)
      where not (a2.capabilities ? cap.value)
    )
  order by r.created_at
  for update of r skip locked
  limit 1;

  if v_run.id is null then return null;end if;

  select ra.id,a2.agent_key into v_assignment_id,v_agent_key
  from public.factory_run_agent_assignments ra
  join public.factory_tasks t on t.id=v_run.task_id
  join public.factory_agents a2 on a2.id=ra.agent_id and a2.is_active=true
    and a2.allowed_tools ?& array['codex','github_write']
  where ra.run_id=v_run.id and ra.status in ('assigned','claimed')
    and (p_agent_key is null or a2.agent_key=p_agent_key)
    and not exists (
      select 1 from jsonb_array_elements_text(coalesce(t.required_capabilities,'[]'::jsonb)) cap(value)
      where not (a2.capabilities ? cap.value)
    )
  order by ra.assigned_at desc,ra.id desc
  limit 1 for update of ra skip locked;

  if v_assignment_id is null or v_agent_key is null then
    raise exception 'active agent assignment not found';
  end if;

  select * into v_task from public.factory_tasks where id=v_run.task_id for update;
  select * into v_project from public.factory_projects where id=v_task.project_id;
  if v_task.status is distinct from 'queued_execution' or v_project.is_active is distinct from true then
    return null;
  end if;
  select * into v_unit from public.factory_change_set_work_units
    where run_id=v_run.id and status='queued';
  if v_unit.id is null then raise exception 'queued change-set work unit not found'; end if;

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
  where id=v_run.id and status='queued' and execution_route='codex'
    and metadata->>'codex_execution_mode'='automatic';
  if not found then raise exception 'automatic Codex claim lost mode guard'; end if;

  update public.factory_tasks
  set status='implementing',updated_at=now()
  where id=v_task.id;

  update public.factory_run_agent_assignments
  set status='claimed',claimed_at=coalesce(claimed_at,now())
  where id=v_assignment_id
    and run_id=v_run.id
    and status in ('assigned','claimed');
  if not found then raise exception 'automatic Codex assignment update lost'; end if;

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
$function$;

CREATE OR REPLACE FUNCTION public.factory_agent_work_matrix(p_limit integer DEFAULT 12)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY INVOKER
 SET search_path TO ''
AS $function$
 with work as (
   select r.id run_id,r.execution_route,a.agent_key,a.role,ra.assigned_at
   from public.factory_run_agent_assignments ra
   join public.factory_runs r on r.id=ra.run_id
   join public.factory_agents a on a.id=ra.agent_id
   join public.factory_tasks t on t.id=r.task_id
   where ra.status='assigned' and r.status='queued' and t.status='queued_execution' and a.is_active
     and (r.execution_route='direct'
          or (r.execution_route='codex' and r.metadata->>'codex_execution_mode'='automatic'
              and a.allowed_tools ?& array['codex','github_write']
              and not exists (
                select 1 from jsonb_array_elements_text(coalesce(t.required_capabilities,'[]'::jsonb)) cap(value)
                where not (a.capabilities ? cap.value)
              )))
   order by ra.assigned_at
   limit greatest(1,least(coalesce(p_limit,12),32))
 )
 select jsonb_build_object(
   'direct',coalesce((select jsonb_agg(jsonb_build_object('run_id',run_id,'agent_key',agent_key,'role',role) order by assigned_at) from work where execution_route='direct'),'[]'::jsonb),
   'codex',coalesce((select jsonb_agg(jsonb_build_object('run_id',run_id,'agent_key',agent_key,'role',role) order by assigned_at) from work where execution_route='codex'),'[]'::jsonb)
 );
$function$;

revoke all on function public.factory_schedule_eligible_codex_run(uuid,text) from public,anon,authenticated;
grant execute on function public.factory_schedule_eligible_codex_run(uuid,text) to service_role;
revoke all on function public.factory_claim_next_agent_codex_run(text,text,uuid) from public,anon,authenticated;
grant execute on function public.factory_claim_next_agent_codex_run(text,text,uuid) to service_role;
revoke all on function public.factory_agent_work_matrix(integer) from public,anon,authenticated;
grant execute on function public.factory_agent_work_matrix(integer) to service_role;
