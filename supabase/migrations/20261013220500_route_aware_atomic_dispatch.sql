-- Route-aware dispatch: read-only preflight, then atomically claim exactly
-- the same Work Unit and route decision. Existing legacy claim API is disabled.
create or replace function public.factory_peek_planned_work(
 p_project_key text,p_limit integer default 100
) returns jsonb
language plpgsql security invoker set search_path=''
as $$
declare v_project_id uuid;v_team_id uuid;v_team_status text;v_items jsonb;
begin
 if p_limit<1 or p_limit>100 then raise exception 'invalid candidate limit';end if;
 select id into v_project_id from public.factory_projects
 where project_key=btrim(p_project_key) and is_active=true;
 if v_project_id is null then raise exception 'active project not found';end if;
 select id,status into v_team_id,v_team_status
 from public.factory_execution_team_plans
 where project_id=v_project_id order by version desc limit 1;
 if v_team_status is distinct from 'ready' then return '[]'::jsonb; end if;
 select coalesce(jsonb_agg(q.data order by q.created_at,q.work_unit_id),'[]'::jsonb)
 into v_items from (
  select u.created_at,u.id as work_unit_id,
   jsonb_build_object(
    'work_unit_id',u.id,
    'fingerprint',md5(concat(
      to_jsonb(t)::text,'|',u.id::text,'|',u.status,'|',
      u.agent_key,'|',u.wave,'|',cs.id::text,'|',
      cs.status,'|',cs.current_wave,'|',v_team_id::text)),
    'task_id',t.id,'project_key',p_project_key,'title',t.title,
    'description',t.description,'complexity',t.complexity,'risk',t.risk,
    'metadata',jsonb_build_object(
       'acceptance_criteria',t.acceptance_criteria,'depends_on',t.depends_on,
       'change_set_id',cs.id,'work_unit_id',u.id,'wave',u.wave,
       'agent_key',u.agent_key)
   ) as data
  from public.factory_change_set_work_units u
  join public.factory_change_sets cs on cs.id=u.change_set_id
  join public.factory_tasks t on t.id=u.task_id
  where cs.project_id=v_project_id and cs.team_plan_id=v_team_id
    and cs.status in ('planned','building')
    and u.status='pending' and u.wave=cs.current_wave
    and t.status='queued'
    and not exists(select 1 from public.factory_runs prior
      where prior.task_id=t.id
        and prior.status in ('created','queued','implementing','completed'))
    and not exists(select 1 from public.factory_change_set_work_units older
      where older.task_id=t.id and older.id<>u.id
        and older.status in ('queued','running','completed','integrated'))
  order by u.created_at,u.id limit p_limit
 ) q;
 return v_items;
end;
$$;
revoke all on function public.factory_peek_planned_work(text,integer) from public,anon,authenticated;
grant execute on function public.factory_peek_planned_work(text,integer) to service_role;

create or replace function public.factory_dispatch_preapproved_planned_task(
 p_project_key text,p_work_unit_id uuid,p_fingerprint text,p_route text,
 p_codex_level integer,p_codex_used boolean,p_codex_reasons jsonb,
 p_routing_policy_version text,p_human_gate boolean,p_gate_reasons jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_project_id uuid;v_team_id uuid;v_team_status text;v_actual_fingerprint text;v_task public.factory_tasks%rowtype;v_run_id uuid;v_unit public.factory_change_set_work_units%rowtype;v_set public.factory_change_sets%rowtype;
begin
 if p_work_unit_id is null or p_fingerprint is null
    or p_fingerprint !~ '^[0-9a-f]{32}$' then
    raise exception 'exact Work Unit fingerprint required';
 end if;
 if p_route not in ('direct','codex') then
    raise exception 'invalid route';
 end if;
 select id into v_project_id from public.factory_projects
 where project_key=btrim(p_project_key) and is_active=true;
 if v_project_id is null then raise exception 'active project not found'; end if;
 select id,status into v_team_id,v_team_status from public.factory_execution_team_plans where project_id=v_project_id order by version desc limit 1;
 if v_team_status is distinct from 'ready' then return null; end if;
 select u.* into v_unit
 from public.factory_change_set_work_units u
 join public.factory_change_sets s on s.id=u.change_set_id
 join public.factory_tasks t on t.id=u.task_id
 where s.project_id=v_project_id and s.team_plan_id=v_team_id and t.status='queued'
   and u.id=p_work_unit_id
   and not exists (select 1 from public.factory_runs prior
     where prior.task_id=t.id and prior.status in ('created','queued','implementing','completed'))
   and not exists (select 1 from public.factory_change_set_work_units prior_unit
     where prior_unit.task_id=t.id and prior_unit.id<>u.id
       and prior_unit.status in ('queued','running','completed','integrated')) and s.status in ('planned','building') and u.status='pending' and u.wave=s.current_wave
 order by u.created_at for update of u skip locked limit 1;
 if v_unit.id is null then return null; end if;
 select * into v_set from public.factory_change_sets where id=v_unit.change_set_id for update;
 select * into v_task from public.factory_tasks where id=v_unit.task_id for update;
 if v_task.status<>'queued' or v_set.status not in ('planned','building')
    or v_unit.wave<>v_set.current_wave or v_set.team_plan_id<>v_team_id then
   return null;
 end if;
 v_actual_fingerprint:=md5(concat(
   to_jsonb(v_task)::text,'|',v_unit.id::text,'|',v_unit.status,'|',
   v_unit.agent_key,'|',v_unit.wave,'|',v_set.id::text,'|',
   v_set.status,'|',v_set.current_wave,'|',v_team_id::text));
 if v_actual_fingerprint is distinct from p_fingerprint then
   raise exception 'candidate changed between route preflight and claim';
 end if;
 insert into public.factory_runs(task_id,status,metadata)
 values(v_task.id,'created',jsonb_build_object('dispatch_pending',true,'source','change-set','change_set_id',v_set.id,'work_unit_id',v_unit.id,'wave',v_unit.wave))
 returning id into v_run_id;
 update public.factory_tasks set status='dispatching',updated_at=now() where id=v_task.id;
 update public.factory_change_set_work_units set status='queued',run_id=v_run_id,updated_at=now() where id=v_unit.id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project_id,v_task.id,v_run_id,'system','backlog-dispatcher','change_set.work_unit.dispatched',
   jsonb_build_object('change_set_id',v_set.id,'work_unit_id',v_unit.id,'wave',v_unit.wave,'team_plan_status',v_team_status));
 perform public.factory_record_dispatch_decision_v2(
   v_run_id,p_route,p_codex_level,p_codex_used,p_codex_reasons,
   p_routing_policy_version,p_human_gate,p_gate_reasons
 );
 return jsonb_build_object(
  'run_id',v_run_id,'task_id',v_task.id,'project_id',v_project_id,'project_key',p_project_key,
  'title',v_task.title,'description',v_task.description,'complexity',v_task.complexity,'risk',v_task.risk,
  'metadata',jsonb_build_object('acceptance_criteria',v_task.acceptance_criteria,'depends_on',v_task.depends_on,
    'change_set_id',v_set.id,'work_unit_id',v_unit.id,'wave',v_unit.wave,'agent_key',v_unit.agent_key)
 );
end;
$$;
revoke all on function public.factory_dispatch_preapproved_planned_task(text,uuid,text,text,integer,boolean,jsonb,text,boolean,jsonb)
 from public,anon,authenticated;
grant execute on function public.factory_dispatch_preapproved_planned_task(text,uuid,text,text,integer,boolean,jsonb,text,boolean,jsonb)
 to service_role;
revoke execute on function public.factory_dispatch_next_planned_task(text) from service_role;
