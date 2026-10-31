BEGIN;
CREATE OR REPLACE FUNCTION public.factory_dispatch_preapproved_planned_task_v2(p_project_key text, p_work_unit_id uuid, p_fingerprint text, p_route text, p_codex_level integer, p_codex_used boolean, p_codex_reasons jsonb, p_routing_policy_version text, p_human_gate boolean, p_gate_reasons jsonb, p_codex_mode text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY INVOKER
 SET search_path TO ''
AS $function$
declare v_project_id uuid;v_team_id uuid;v_team_status text;v_actual_fingerprint text;v_task public.factory_tasks%rowtype;v_run_id uuid;v_unit public.factory_change_set_work_units%rowtype;v_set public.factory_change_sets%rowtype;v_journey public.factory_journeys%rowtype;v_generation bigint;v_run_md jsonb;
begin
 if p_work_unit_id is null or p_fingerprint is null
    or p_fingerprint !~ '^[0-9a-f]{32}$' then
    raise exception 'exact Work Unit fingerprint required';
 end if;
 if p_route not in ('direct','codex') then
    raise exception 'invalid route';
 end if;
 if (p_route='codex' and (p_codex_mode is null or p_codex_mode not in ('manual','automatic')))
    or (p_route='direct' and p_codex_mode is not null) then
   raise exception 'invalid durable Codex execution mode';
 end if;
 select id into v_project_id from public.factory_projects
 where project_key=btrim(p_project_key) and is_active=true;
 if v_project_id is null then raise exception 'active project not found'; end if;
  perform public.factory_assert_project_running(v_project_id);
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
 if v_set.journey_id is distinct from v_task.journey_id then
  raise exception 'V2 task/Change Set journey mismatch' using errcode='PT409';
 end if;
 if v_task.journey_id is not null then
  select generation into v_generation from public.factory_project_execution_controls where project_id=v_project_id for share;
  select * into v_journey from public.factory_journeys where id=v_task.journey_id and project_id=v_project_id for share;
  if v_journey.id is null or v_generation is distinct from v_journey.execution_generation
    or v_journey.state not in ('source_bound','executing')
    or v_set.root_task_id is distinct from v_task.parent_task_id
    or v_journey.binding->>'source_commit' is distinct from v_journey.source_commit
    or v_journey.binding->>'integration_branch' is null
    or v_journey.binding->>'journey_id' is distinct from v_journey.id::text
    or v_journey.binding->>'project_id' is distinct from v_project_id::text
    or (v_set.source_commit is not null and v_set.source_commit is distinct from v_journey.source_commit)
  then raise exception 'V2 lineage/epoch invalid' using errcode='PT409'; end if;
 end if;
 v_actual_fingerprint:=md5(concat(
   to_jsonb(v_task)::text,'|',v_unit.id::text,'|',v_unit.status,'|',
   v_unit.agent_key,'|',v_unit.wave,'|',v_set.id::text,'|',
   v_set.status,'|',v_set.current_wave,'|',v_team_id::text));
 if v_actual_fingerprint is distinct from p_fingerprint then
   raise exception 'candidate changed between route preflight and claim';
 end if;
 v_run_md:=jsonb_build_object('dispatch_pending',true,'source','change-set','change_set_id',v_set.id,'work_unit_id',v_unit.id,'wave',v_unit.wave);
 if v_journey.id is not null then v_run_md:=v_run_md||jsonb_build_object('execution_generation',v_generation,'journey_binding_v2',v_journey.binding); end if;
 insert into public.factory_runs(task_id,status,source_commit,metadata)
 values(v_task.id,'created',v_journey.source_commit,v_run_md)
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
 if p_route='codex' then
   update public.factory_runs
   set metadata=coalesce(metadata,'{}'::jsonb)||jsonb_build_object('codex_execution_mode',p_codex_mode)
   where id=v_run_id and execution_route='codex';
   if not found then raise exception 'Codex execution-mode stamp failed'; end if;
 end if;
 return jsonb_build_object(
  'codex_execution_mode',p_codex_mode,'run_id',v_run_id,'task_id',v_task.id,'project_id',v_project_id,'project_key',p_project_key,
  'title',v_task.title,'description',v_task.description,'complexity',v_task.complexity,'risk',v_task.risk,
  'metadata',jsonb_build_object('acceptance_criteria',v_task.acceptance_criteria,'depends_on',v_task.depends_on,
    'change_set_id',v_set.id,'work_unit_id',v_unit.id,'wave',v_unit.wave,'agent_key',v_unit.agent_key)
 );
end;
$function$
;
REVOKE ALL ON FUNCTION public.factory_dispatch_preapproved_planned_task_v2(text,uuid,text,text,integer,boolean,jsonb,text,boolean,jsonb,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_dispatch_preapproved_planned_task_v2(text,uuid,text,text,integer,boolean,jsonb,text,boolean,jsonb,text) TO service_role;
COMMIT;