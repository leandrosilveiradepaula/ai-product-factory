create or replace function public.factory_record_execution_team_plan(
 p_run_id uuid,
 p_plan jsonb
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
 v_project_id uuid;
 v_task_id uuid;
 v_locked_project_id uuid;
 v_version integer;
 v_status text;
 v_id uuid;
begin
 if p_plan is null or jsonb_typeof(p_plan)<>'object' then
  raise exception 'execution team plan must be a JSON object';
 end if;
 v_status:=coalesce(nullif(p_plan->>'status',''),'blocked');
 if v_status not in ('ready','blocked') then
  raise exception 'invalid execution team plan status';
 end if;

 select t.project_id,r.task_id into v_project_id,v_task_id
 from public.factory_runs r
 join public.factory_tasks t on t.id=r.task_id
 where r.id=p_run_id
 for update of r;
 if v_project_id is null then raise exception 'run not found'; end if;

 select p.id into v_locked_project_id
 from public.factory_projects p
 where p.id=v_project_id
 for update;
 if v_locked_project_id is null then raise exception 'project not found'; end if;

 select coalesce(max(version),0)+1 into v_version
 from public.factory_execution_team_plans
 where project_id=v_project_id;

 update public.factory_execution_team_plans
 set status='superseded'
 where project_id=v_project_id and status in ('ready','blocked');

 insert into public.factory_execution_team_plans(project_id,source_run_id,version,status,plan)
 values(v_project_id,p_run_id,v_version,v_status,p_plan)
 returning id into v_id;

 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(
  v_project_id,v_task_id,p_run_id,'system','execution-team-planner','team.plan.recorded',
  jsonb_build_object(
   'team_plan_id',v_id,
   'version',v_version,
   'status',v_status,
   'profiles_selected',coalesce((p_plan->>'profiles_selected')::int,0),
   'planned_worker_peak',coalesce((p_plan->>'planned_worker_peak')::int,0),
   'blocker_count',jsonb_array_length(coalesce(p_plan->'blockers','[]'::jsonb))
  )
 );

 return jsonb_build_object('id',v_id,'project_id',v_project_id,'version',v_version,'status',v_status);
end;
$$;

revoke all on function public.factory_record_execution_team_plan(uuid,jsonb) from public,anon,authenticated;
grant execute on function public.factory_record_execution_team_plan(uuid,jsonb) to service_role;
