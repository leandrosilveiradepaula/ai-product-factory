-- Fail-closed Direct-only scheduler. A human-gated run remains ineligible
-- until approval changes its status and task status in one transaction.
create or replace function public.factory_schedule_eligible_direct_run(
 p_run_id uuid default null,
 p_project_key text default null
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
 v_run public.factory_runs%rowtype;
 v_task public.factory_tasks%rowtype;
 v_assignment jsonb;
begin
 select r.* into v_run
 from public.factory_runs r
 join public.factory_tasks t on t.id=r.task_id
 join public.factory_projects proj on proj.id=t.project_id
 where r.status='queued'
   and r.execution_route='direct'
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

 v_assignment:=public.factory_schedule_run_agent(
   v_run.id,
   case
     when nullif(btrim(v_task.agent_role),'') is not null then v_task.agent_role
     when coalesce(v_task.required_capabilities,'[]'::jsonb)='[]'::jsonb
       then 'development'
     else null
   end,
   coalesce(v_task.required_capabilities,'[]'::jsonb),
   coalesce(v_task.scope_keys,'[]'::jsonb),
   900
 );
 if v_assignment is null then return null; end if;
 insert into public.factory_audit_events(
   project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
 ) values (
   v_task.project_id,v_task.id,v_run.id,'system','route-safe-direct-scheduler',
   'agent.assigned',v_assignment
 );
 return v_assignment || jsonb_build_object('run_id',v_run.id,'task_id',v_task.id);
end;
$$;
revoke all on function public.factory_schedule_eligible_direct_run(uuid,text)
 from public,anon,authenticated;
grant execute on function public.factory_schedule_eligible_direct_run(uuid,text)
 to service_role;
