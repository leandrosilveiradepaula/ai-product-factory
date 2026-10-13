-- Safe, idempotent planning boundary. Do not mutate historical Change Sets.
create or replace function public.factory_materialize_change_set(p_team_plan_id uuid)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
 v_team public.factory_execution_team_plans%rowtype;
 v_existing public.factory_change_sets%rowtype;
 v_task_status text;
 v_root_task_id uuid;
 v_change_set_id uuid;
 v_item jsonb;
 v_task_id uuid;
 v_external_key text;
 v_wave integer;
 v_count integer:=0;
begin
 select * into v_team from public.factory_execution_team_plans where id=p_team_plan_id for update;
 if not found then raise exception 'team plan not found'; end if;
 if v_team.status<>'ready' then raise exception 'team plan must be ready'; end if;
 -- Lock the plan before the existing Change Set; repeated RPCs are read-only.
 select * into v_existing from public.factory_change_sets
 where team_plan_id=v_team.id for update;
 if found then
   return jsonb_build_object('change_set_id',v_existing.id,
     'builder_work_units',(select count(*) from public.factory_change_set_work_units
       where change_set_id=v_existing.id),
     'status',v_existing.status,'already_materialized',true);
 end if;
 if exists(select 1 from public.factory_execution_team_plans newer
   where newer.project_id=v_team.project_id and newer.version>v_team.version) then
   raise exception 'stale team plan cannot be materialized';
 end if;
 select r.task_id into v_root_task_id from public.factory_runs r where r.id=v_team.source_run_id;
 if v_root_task_id is null then raise exception 'team plan source run not found'; end if;

 insert into public.factory_change_sets(project_id,team_plan_id,root_task_id,status,metadata)
 values(v_team.project_id,v_team.id,v_root_task_id,'planned',
   jsonb_build_object('team_plan_version',v_team.version,'selection_policy',v_team.plan->>'selection_policy'))
 returning id into v_change_set_id;

 for v_item in
   select value from jsonb_array_elements(coalesce(v_team.plan->'task_assignments','[]'::jsonb))
 loop
   if coalesce(v_item->>'execution_lane','')<>'builder' then continue; end if;
   if coalesce(v_item->>'task_key','')='' then raise exception 'builder task missing task_key'; end if;
   v_external_key:='plan-'||substr(md5(coalesce(v_item->>'title',v_item::text)),1,16);
   select id,status into v_task_id,v_task_status
   from public.factory_tasks
   where project_id=v_team.project_id and external_key=v_external_key
   limit 1;
   if v_task_id is null then raise exception 'planned task not found for change-set task %',v_item->>'task_key'; end if;
   if v_task_status<>'queued' then
     raise exception 'planned task is not queued: %',v_item->>'task_key';
   end if;
   if exists(select 1 from public.factory_runs r where r.task_id=v_task_id
     and r.status in ('created','queued','implementing','completed')) then
     raise exception 'planned task already has execution history: %',v_item->>'task_key';
   end if;
   if exists(select 1 from public.factory_change_set_work_units previous
     where previous.task_id=v_task_id
       and previous.status in ('queued','running','completed','integrated')) then
     raise exception 'planned task already has work unit history: %',v_item->>'task_key';
   end if;
   v_wave=coalesce((v_item->>'wave')::integer,1);
   insert into public.factory_change_set_work_units(change_set_id,task_id,plan_task_key,agent_key,wave,status)
   values(v_change_set_id,v_task_id,v_item->>'task_key',v_item->>'agent_key',v_wave,'pending')
;
   v_count:=v_count+1;
 end loop;

 if v_count=0 then update public.factory_change_sets set status='review_ready',updated_at=now() where id=v_change_set_id; end if;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_team.project_id,v_root_task_id,v_team.source_run_id,'system','change-set-planner','change_set.materialized',
   jsonb_build_object('change_set_id',v_change_set_id,'builder_work_units',v_count,'team_plan_id',v_team.id));
 return jsonb_build_object('change_set_id',v_change_set_id,'builder_work_units',v_count,'status',case when v_count=0 then 'review_ready' else 'planned' end);
end;
$$;
revoke all on function public.factory_materialize_change_set(uuid) from public,anon,authenticated;
grant execute on function public.factory_materialize_change_set(uuid) to service_role;


-- A work unit is runnable only under the latest ready team plan.
create or replace function public.factory_dispatch_next_planned_task(p_project_key text)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_project_id uuid;v_team_id uuid;v_team_status text;v_task public.factory_tasks%rowtype;v_run_id uuid;v_unit public.factory_change_set_work_units%rowtype;v_set public.factory_change_sets%rowtype;
begin
 select id into v_project_id from public.factory_projects where project_key=btrim(p_project_key) and is_active=true;
 if v_project_id is null then raise exception 'active project not found'; end if;
 select id,status into v_team_id,v_team_status from public.factory_execution_team_plans where project_id=v_project_id order by version desc limit 1;
 if v_team_status is distinct from 'ready' then return null; end if;
 select u.* into v_unit
 from public.factory_change_set_work_units u
 join public.factory_change_sets s on s.id=u.change_set_id
 join public.factory_tasks t on t.id=u.task_id
 where s.project_id=v_project_id and s.team_plan_id=v_team_id and t.status='queued'
   and not exists (select 1 from public.factory_runs prior
     where prior.task_id=t.id and prior.status in ('created','queued','implementing','completed'))
   and not exists (select 1 from public.factory_change_set_work_units prior_unit
     where prior_unit.task_id=t.id and prior_unit.id<>u.id
       and prior_unit.status in ('queued','running','completed','integrated')) and s.status in ('planned','building') and u.status='pending' and u.wave=s.current_wave
 order by u.created_at for update of u skip locked limit 1;
 if v_unit.id is null then return null; end if;
 select * into v_set from public.factory_change_sets where id=v_unit.change_set_id;
 select * into v_task from public.factory_tasks where id=v_unit.task_id for update;
 insert into public.factory_runs(task_id,status,metadata)
 values(v_task.id,'created',jsonb_build_object('dispatch_pending',true,'source','change-set','change_set_id',v_set.id,'work_unit_id',v_unit.id,'wave',v_unit.wave))
 returning id into v_run_id;
 update public.factory_tasks set status='dispatching',updated_at=now() where id=v_task.id;
 update public.factory_change_set_work_units set status='queued',run_id=v_run_id,updated_at=now() where id=v_unit.id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project_id,v_task.id,v_run_id,'system','backlog-dispatcher','change_set.work_unit.dispatched',
   jsonb_build_object('change_set_id',v_set.id,'work_unit_id',v_unit.id,'wave',v_unit.wave,'team_plan_status',v_team_status));
 return jsonb_build_object(
  'run_id',v_run_id,'task_id',v_task.id,'project_id',v_project_id,'project_key',p_project_key,
  'title',v_task.title,'description',v_task.description,'complexity',v_task.complexity,'risk',v_task.risk,
  'metadata',jsonb_build_object('acceptance_criteria',v_task.acceptance_criteria,'depends_on',v_task.depends_on,
    'change_set_id',v_set.id,'work_unit_id',v_unit.id,'wave',v_unit.wave,'agent_key',v_unit.agent_key)
 );
end;
$$;
revoke all on function public.factory_dispatch_next_planned_task(text) from public,anon,authenticated;
grant execute on function public.factory_dispatch_next_planned_task(text) to service_role;

