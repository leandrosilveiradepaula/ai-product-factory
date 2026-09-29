create or replace function public.factory_dispatch_next_planned_task(p_project_key text)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
 v_project_id uuid;
 v_team_status text;
 v_task public.factory_tasks%rowtype;
 v_run_id uuid;
begin
 select id into v_project_id
 from public.factory_projects
 where project_key=btrim(p_project_key) and is_active=true;
 if v_project_id is null then raise exception 'active project not found'; end if;

 select status into v_team_status
 from public.factory_execution_team_plans
 where project_id=v_project_id
 order by version desc
 limit 1;

 if v_team_status is distinct from 'ready' then
  return null;
 end if;

 select * into v_task
 from public.factory_tasks
 where project_id=v_project_id
   and status='queued'
   and external_key like 'plan-%'
 order by created_at
 for update skip locked
 limit 1;
 if v_task.id is null then return null; end if;

 insert into public.factory_runs(task_id,status,metadata)
 values(v_task.id,'created',jsonb_build_object('dispatch_pending',true,'source','engineering-plan'))
 returning id into v_run_id;

 update public.factory_tasks
 set status='dispatching',updated_at=now()
 where id=v_task.id;

 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project_id,v_task.id,v_run_id,'system','backlog-dispatcher','task.dispatch.claimed',
        jsonb_build_object('team_plan_status',v_team_status));

 return jsonb_build_object(
  'run_id',v_run_id,
  'task_id',v_task.id,
  'project_id',v_project_id,
  'project_key',p_project_key,
  'title',v_task.title,
  'description',v_task.description,
  'complexity',v_task.complexity,
  'risk',v_task.risk,
  'metadata',jsonb_build_object(
    'acceptance_criteria',v_task.acceptance_criteria,
    'depends_on',v_task.depends_on
  )
 );
end;
$$;

revoke all on function public.factory_dispatch_next_planned_task(text) from public,anon,authenticated;
grant execute on function public.factory_dispatch_next_planned_task(text) to service_role;
