-- V2 planned tasks must be named by immutable journey lineage rather than
-- project-wide task title. Keep V1 behavior unchanged for unbound tasks.
-- The existing functions are preserved except scoped hash/key lookup, pinned
-- V2 Change Set metadata and exact-source guard. Tested in disposable PostgreSQL.
begin;

CREATE OR REPLACE FUNCTION public.factory_persist_product_stage(p_run_id uuid, p_stage text, p_output jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  v_task_id uuid;
  v_journey_id uuid;
  v_project_id uuid;
  v_version integer;
  v_created_tasks integer := 0;
  v_item jsonb;
  v_external_key text;
  v_snapshot_id uuid;
  v_decisions jsonb;
  v_decision_task_id uuid;
  v_decision_run_id uuid;
  v_gate_id uuid;
begin
  if p_stage not in ('discovery','specification','reconciliation','gap_analysis','planning') then
    raise exception 'unsupported product stage';
  end if;

  select r.task_id,t.project_id,r.journey_id into v_task_id,v_project_id,v_journey_id
  from public.factory_runs r
  join public.factory_tasks t on t.id=r.task_id
  where r.id=p_run_id;
  if v_project_id is null then raise exception 'run not found'; end if;

  if p_stage='discovery' then
    update public.factory_product_specs
    set spec=jsonb_set(spec,'{discovery}',coalesce(p_output,'{}'::jsonb),true)
    where project_id=v_project_id
      and version=(select max(version) from public.factory_product_specs where project_id=v_project_id);
    update public.factory_projects set lifecycle_stage='specification',updated_at=now() where id=v_project_id;

  elsif p_stage='specification' then
    select coalesce(max(version),0)+1 into v_version
    from public.factory_product_specs where project_id=v_project_id;
    insert into public.factory_product_specs(project_id,version,status,spec)
    values(v_project_id,v_version,'candidate',coalesce(p_output,'{}'::jsonb));
    update public.factory_projects set lifecycle_stage='planning',updated_at=now() where id=v_project_id;

  elsif p_stage='reconciliation' then
    if btrim(coalesce(p_output->>'summary',''))='' then raise exception 'reconciliation summary is required'; end if;
    insert into public.factory_project_state_snapshots(
      project_id,run_id,observed_stage,summary,evidence,gaps,constraints,source_status
    )
    values(
      v_project_id,p_run_id,nullif(btrim(p_output->>'observed_stage'),''),
      btrim(p_output->>'summary'),coalesce(p_output->'evidence','[]'::jsonb),
      coalesce(p_output->'gaps','[]'::jsonb),coalesce(p_output->'constraints','[]'::jsonb),
      coalesce(p_output->'source_status','{}'::jsonb)
    )
    returning id into v_snapshot_id;

  elsif p_stage='gap_analysis' then
    update public.factory_projects
    set lifecycle_stage='planning',
        manifest=manifest||jsonb_build_object('gap_analysis',coalesce(p_output,'{}'::jsonb)),
        updated_at=now()
    where id=v_project_id;

  else
    v_decisions:=coalesce(p_output->'decisions_needed','[]'::jsonb);
    if jsonb_typeof(v_decisions)<>'array' then
      raise exception 'planning decisions_needed must be an array';
    end if;

    update public.factory_projects
    set lifecycle_stage=case when jsonb_array_length(v_decisions)>0 then 'planning' else 'implementation' end,
        manifest=manifest||jsonb_build_object('engineering_plan',coalesce(p_output,'{}'::jsonb)),
        updated_at=now()
    where id=v_project_id;

    if jsonb_array_length(v_decisions)>0 then
      v_external_key:='planning-decisions-'||replace(p_run_id::text,'-','');

      select t.id into v_decision_task_id
      from public.factory_tasks t
      where t.project_id=v_project_id and t.external_key=v_external_key
      limit 1;

      if v_decision_task_id is null then
        insert into public.factory_tasks(
          project_id,parent_task_id,external_key,title,description,status,complexity,risk,
          acceptance_criteria,depends_on
        ) values(
          v_project_id,v_task_id,v_external_key,
          'Resolver decisões de planejamento',
          'Responder as decisões materiais ou de governança antes de qualquer implementação dependente.',
          'awaiting_human','medium','{}'::jsonb,
          '["decisões humanas registradas de forma durável","nenhuma implementação dependente iniciada antes da resolução"]'::jsonb,
          '[]'::jsonb
        )
        returning id into v_decision_task_id;

        insert into public.factory_runs(
          task_id,status,execution_route,metadata
        ) values(
          v_decision_task_id,'awaiting_human','direct',
          jsonb_build_object(
            'decision_only',true,
            'requested_action','planning_decision',
            'planning_decisions',v_decisions,
            'source_planning_run_id',p_run_id
          )
        )
        returning id into v_decision_run_id;

        insert into public.factory_human_gates(run_id,gate_type,status,reasons)
        values(v_decision_run_id,'planning_decision','pending',v_decisions)
        returning id into v_gate_id;

        perform public.factory_supersede_stale_planning_gates(v_project_id,v_gate_id);

        insert into public.factory_decisions(
          project_id,task_id,decision_type,question,decision,decided_by
        ) values(
          v_project_id,v_decision_task_id,'planning_decision_requested',
          'Resolver decisões de planejamento antes da implementação.',
          jsonb_build_object('gate_id',v_gate_id,'source_run_id',p_run_id,'decisions',v_decisions),
          'ai-product-factory'
        );

        insert into public.factory_audit_events(
          project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
        ) values(
          v_project_id,v_decision_task_id,v_decision_run_id,
          'system','runtime-worker','human_gate.requested',
          jsonb_build_object(
            'gate_id',v_gate_id,
            'gate_type','planning_decision',
            'source_planning_run_id',p_run_id,
            'decisions',v_decisions
          )
        );
      else
        select r.id,g.id into v_decision_run_id,v_gate_id
        from public.factory_runs r
        left join public.factory_human_gates g on g.run_id=r.id and g.status='pending'
        where r.task_id=v_decision_task_id
        order by r.created_at desc
        limit 1;
      end if;
    else
      for v_item in
        select value from jsonb_array_elements(coalesce(p_output->'tasks','[]'::jsonb))
      loop
        v_external_key:='plan-'||substr(md5(coalesce(v_item->>'title',v_item::text)||case when v_journey_id is not null then ':journey:'||v_journey_id::text else '' end),1,16);
        if not exists(
          select 1 from public.factory_tasks
          where project_id=v_project_id and external_key=v_external_key
        ) then
          insert into public.factory_tasks(
            project_id,parent_task_id,external_key,title,description,status,complexity,risk,
            acceptance_criteria,depends_on,agent_role,required_capabilities,scope_keys
          ) values(
            v_project_id,v_task_id,v_external_key,coalesce(nullif(v_item->>'title',''),'Planned task'),
            v_item->>'description','queued',
            case when v_item->>'complexity' in ('low','medium','high','very_high')
              then v_item->>'complexity' else 'medium' end,
            coalesce(v_item->'risk','{}'::jsonb),
            coalesce(v_item->'acceptance_criteria','[]'::jsonb),
            coalesce(v_item->'depends_on','[]'::jsonb),
            nullif(v_item->>'preferred_agent_role',''),
            coalesce(v_item->'required_capabilities','[]'::jsonb),
            coalesce(v_item->'scope_keys','[]'::jsonb)
          );
          v_created_tasks:=v_created_tasks+1;
        end if;
      end loop;
    end if;
  end if;

  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  )
  values(
    v_project_id,v_task_id,p_run_id,'system','runtime-worker','product.stage.persisted',
    jsonb_build_object(
      'stage',p_stage,
      'created_tasks',v_created_tasks,
      'snapshot_id',v_snapshot_id,
      'human_gate_id',v_gate_id
    )
  );

  return jsonb_build_object(
    'project_id',v_project_id,
    'stage',p_stage,
    'created_tasks',v_created_tasks,
    'snapshot_id',v_snapshot_id,
    'human_gate_id',v_gate_id,
    'decision_run_id',v_decision_run_id
  );
end;
$function$
;

CREATE OR REPLACE FUNCTION public.factory_materialize_change_set(p_team_plan_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
 v_team public.factory_execution_team_plans%rowtype;
 v_existing public.factory_change_sets%rowtype;
 v_task_status text;
 v_root_task_id uuid;
 v_root_journey_id uuid;
 v_source_commit text;
 v_integration_branch text;
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
 select r.task_id,r.journey_id into v_root_task_id,v_root_journey_id from public.factory_runs r where r.id=v_team.source_run_id;
 if v_root_task_id is null then raise exception 'team plan source run not found'; end if;
 if v_root_journey_id is not null then
   select j.source_commit,j.binding->>'integration_branch' into v_source_commit,v_integration_branch
   from public.factory_journeys j join public.factory_project_execution_controls c on c.project_id=j.project_id
   where j.id=v_root_journey_id and j.project_id=v_team.project_id and j.state='executing'
     and j.execution_generation=c.generation and c.state='running'
     and exists(select 1 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id where r.id=v_team.source_run_id and r.journey_id=j.id and r.source_commit=j.source_commit and t.project_id=j.project_id and t.journey_id=j.id)
   for update of j;
   if v_source_commit is null or v_integration_branch is null then
     raise exception 'journey V2 plan binding not executable' using errcode='PT409';
   end if;
 end if;

 insert into public.factory_change_sets(project_id,team_plan_id,root_task_id,status,source_commit,integration_branch,metadata)
 values(v_team.project_id,v_team.id,v_root_task_id,'planned',v_source_commit,v_integration_branch,
   jsonb_build_object('team_plan_version',v_team.version,'selection_policy',v_team.plan->>'selection_policy'))
 returning id into v_change_set_id;

 for v_item in
   select value from jsonb_array_elements(coalesce(v_team.plan->'task_assignments','[]'::jsonb))
 loop
   if coalesce(v_item->>'execution_lane','')<>'builder' then continue; end if;
   if coalesce(v_item->>'task_key','')='' then raise exception 'builder task missing task_key'; end if;
   v_external_key:='plan-'||substr(md5(coalesce(v_item->>'title',v_item::text)||case when v_root_journey_id is not null then ':journey:'||v_root_journey_id::text else '' end),1,16);
   select id,status into v_task_id,v_task_status
   from public.factory_tasks
   where project_id=v_team.project_id and external_key=v_external_key
     and journey_id is not distinct from v_root_journey_id
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
$function$
;


-- One-off deterministic settlement of a fully persisted V2 engineering plan.
-- A failed materialization is not evidence of an implementation candidate.
create or replace function public.factory_recover_v2_plan_task_collision_once(
  p_journey_id uuid, p_source_run_id uuid, p_team_plan_id uuid,
  p_command_id uuid, p_actor_id uuid, p_expected_generation bigint,
  p_expected_version bigint, p_source_sha text
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare
 p public.factory_projects%rowtype;
 c public.factory_project_execution_controls%rowtype;
 j public.factory_journeys%rowtype;
 r public.factory_runs%rowtype;
 t public.factory_tasks%rowtype;
 team public.factory_execution_team_plans%rowtype;
 previous jsonb;
 plan jsonb;
 assignment jsonb;
 task_def jsonb;
 title text;
 scoped_key text;
 legacy_key text;
 child_id uuid;
 result jsonb;
 materialized jsonb;
begin
 if p_journey_id is null or p_source_run_id is null or p_team_plan_id is null
    or p_command_id is null or p_actor_id is null
    or p_expected_generation is null or p_expected_version is null
    or p_source_sha !~ '^[0-9a-f]{40}
 then raise exception 'invalid V2 plan materialization recovery request' using errcode='PT400'; end if;
 if not exists(select 1 from public.factory_console_operators o
    where o.user_id=p_actor_id and o.is_active=true and o.role='admin')
 then raise exception 'V2 materialization recovery requires active admin' using errcode='PT403'; end if;
 select * into p from public.factory_projects
   where project_key='crm-infodive' and is_active=true
     and project_kind='existing'
     and repository='leandrosilveiradepaula/crm-infodive' for update;
 if p.id is null then raise exception 'CRM project not found' using errcode='PT409'; end if;
 select a.payload into previous from public.factory_audit_events a
   where a.project_id=p.id
     and a.event_type='journey.v2.plan_task_collision_recovered'
     and a.payload->>'command_id'=p_command_id::text
   order by a.id desc limit 1;
 if previous is not null then
   if previous->>'journey_id' is distinct from p_journey_id::text
     or previous->>'source_run_id' is distinct from p_source_run_id::text
     or previous->>'team_plan_id' is distinct from p_team_plan_id::text
     or previous->>'actor_id' is distinct from p_actor_id::text
     or previous->>'generation' is distinct from p_expected_generation::text
     or previous->>'control_version' is distinct from p_expected_version::text
     or previous->>'source_commit' is distinct from p_source_sha
   then raise exception 'materialization recovery replay mismatch' using errcode='PT409'; end if;
   return previous->'receipt';
 end if;
 select * into c from public.factory_project_execution_controls where project_id=p.id for update;
 select * into j from public.factory_journeys where id=p_journey_id and project_id=p.id for update;
 select * into r from public.factory_runs where id=p_source_run_id and journey_id=p_journey_id for update;
 select * into t from public.factory_tasks where id=r.task_id and project_id=p.id for update;
 select * into team from public.factory_execution_team_plans
   where id=p_team_plan_id and project_id=p.id for update;
 plan:=p.manifest->'engineering_plan';
 if c.state is distinct from 'running' or c.generation is distinct from p_expected_generation
   or c.version is distinct from p_expected_version
   or j.id is null or j.state is distinct from 'executing'
   or j.execution_generation is distinct from c.generation
   or j.source_commit is distinct from p_source_sha
   or j.binding->>'source_commit' is distinct from p_source_sha
   or j.binding->>'execution_generation' is distinct from c.generation::text
   or j.binding->>'integration_branch' is distinct from r.branch_name
   or j.project_policy_version is distinct from 4
   or j.policy_digest is distinct from p.manifest->'journey_delivery_binding_v2'->>'digest'
   or j.request_snapshot->>'text' not like '%issue #209%'
   or j.candidate_commit is not null or j.work_unit_output_commit is not null
   or j.preview_merge_sha is not null or j.production_release_sha is not null
   or r.id is null or r.status is distinct from 'failed'
   or r.execution_route is distinct from 'direct'
   or r.source_commit is distinct from p_source_sha
   or r.metadata->>'error' is distinct from 'control-plane RPC failed: factory_materialize_change_set (400)'
   or r.metadata->'journey_binding_v2' is distinct from j.binding
   or r.metadata->'stages' is distinct from '["reconciliation","gap_analysis","planning"]'::jsonb
   or r.metadata->>'execution_generation' is distinct from c.generation::text
   or r.lease_owner is not null or r.candidate_commit is not null
   or t.id is null or t.status is distinct from 'failed' or t.journey_id is distinct from j.id
   or team.id is null or team.source_run_id is distinct from r.id
   or team.status is distinct from 'ready'
   or team.version is distinct from 19
   or jsonb_typeof(plan->'tasks') is distinct from 'array'
   or jsonb_array_length(plan->'tasks') is distinct from 1
   or jsonb_typeof(plan->'decisions_needed') is distinct from 'array'
   or jsonb_array_length(plan->'decisions_needed') is distinct from 0
   or jsonb_typeof(team.plan->'task_assignments') is distinct from 'array'
   or jsonb_array_length(team.plan->'task_assignments') is distinct from 1
   or not public.factory_control_quiescent(p.id)
 then raise exception 'V2 materialization recovery identity/epoch mismatch' using errcode='PT409'; end if;
 task_def:=plan->'tasks'->0;
 assignment:=team.plan->'task_assignments'->0;
 title:=task_def->>'title';
 if title is null or btrim(title)='' or task_def->>'task_key' is distinct from assignment->>'task_key'
   or title is distinct from assignment->>'title'
   or assignment->>'execution_lane' is distinct from 'builder'
   or assignment->>'agent_key' is distinct from 'development'
 then raise exception 'V2 source plan and team assignment mismatch' using errcode='PT409'; end if;
 scoped_key:='plan-'||substr(md5(title||':journey:'||j.id::text),1,16);
 legacy_key:='plan-'||substr(md5(title),1,16);
 if (select count(*) from public.factory_runs where journey_id=j.id) <> 3
   or exists(select 1 from public.factory_runs other
     join public.factory_tasks ot on ot.id=other.task_id
     where ot.project_id=p.id and other.status in ('created','queued','running'))
   or exists(select 1 from public.factory_tasks child where child.parent_task_id=t.id)
   or exists(select 1 from public.factory_tasks child where child.project_id=p.id and child.external_key=scoped_key)
   or not exists(select 1 from public.factory_tasks legacy
     where legacy.project_id=p.id and legacy.external_key=legacy_key
       and legacy.journey_id is distinct from j.id and legacy.status='blocked')
   or exists(select 1 from public.factory_change_sets cs where cs.journey_id=j.id or cs.team_plan_id=team.id)
   or exists(select 1 from public.factory_human_gates h join public.factory_runs hr on hr.id=h.run_id where hr.journey_id=j.id)
   or exists(select 1 from public.factory_deployments d join public.factory_runs dr on dr.id=d.run_id where dr.journey_id=j.id)
   or exists(select 1 from public.factory_release_reports d join public.factory_runs dr on dr.id=d.run_id where dr.journey_id=j.id)
   or exists(select 1 from public.factory_evaluations e join public.factory_runs er on er.id=e.run_id where er.journey_id=j.id)
   or not exists(select 1 from public.factory_audit_events a where a.run_id=r.id
     and a.event_type='product.stage.persisted' and a.payload->>'stage'='planning'
       and a.payload->>'created_tasks'='0')
   or not exists(select 1 from public.factory_audit_events a where a.run_id=r.id
     and a.event_type='team.plan.recorded' and a.payload->>'team_plan_id'=team.id::text)
   or exists(select 1 from public.factory_audit_events a where a.project_id=p.id
       and a.event_type='journey.v2.plan_task_collision_recovered'
       and a.payload->>'journey_id'=j.id::text)
 then raise exception 'V2 materialization recovery work already advanced or no collision proof' using errcode='PT409'; end if;

 insert into public.factory_tasks(
    project_id,parent_task_id,journey_id,external_key,title,description,status,
    complexity,risk,acceptance_criteria,depends_on,
    agent_role,required_capabilities,scope_keys
 ) values (
    p.id,t.id,j.id,scoped_key,title,task_def->>'description','queued',
    case when task_def->>'complexity' in ('low','medium','high','very_high')
      then task_def->>'complexity' else 'medium' end,
    coalesce(task_def->'risk','{}'::jsonb),
    coalesce(task_def->'acceptance_criteria','[]'::jsonb),
    coalesce(task_def->'depends_on','[]'::jsonb),
    nullif(task_def->>'preferred_agent_role',''),
    coalesce(task_def->'required_capabilities','[]'::jsonb),
    coalesce(task_def->'scope_keys','[]'::jsonb)
 ) returning id into child_id;
 materialized:=public.factory_materialize_change_set(team.id);
 if materialized->>'status' is distinct from 'planned'
    or (materialized->>'builder_work_units')::int is distinct from 1
    or not exists(select 1 from public.factory_change_sets cs
         where cs.id=(materialized->>'change_set_id')::uuid
           and cs.journey_id=j.id and cs.source_commit=j.source_commit
           and cs.integration_branch=j.binding->>'integration_branch'
           and cs.status='planned')
    or not exists(select 1 from public.factory_change_set_work_units w
         where w.change_set_id=(materialized->>'change_set_id')::uuid
           and w.task_id=child_id and w.status='pending')
 then raise exception 'V2 materialization postconditions not satisfied' using errcode='PT409'; end if;

 result:=jsonb_build_object('status','recovered', 'created',true,
   'journey_id',j.id,'source_run_id',r.id,'team_plan_id',team.id,
   'task_id',child_id,'change_set_id',materialized->>'change_set_id',
   'generation',c.generation,'source_commit',j.source_commit,
   'paid_calls',0,'release_authorized',false,
   'original_run_status','failed');
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(p.id,t.id,r.id,'human',p_actor_id::text,'journey.v2.plan_task_collision_recovered',
   jsonb_build_object('command_id',p_command_id,'journey_id',j.id,
     'source_run_id',r.id,'team_plan_id',team.id,'actor_id',p_actor_id,
     'generation',p_expected_generation,'control_version',p_expected_version,
     'source_commit',p_source_sha,'receipt',result));
 return result;
end $fn$;

revoke all on function public.factory_recover_v2_plan_task_collision_once(
 uuid,uuid,uuid,uuid,uuid,bigint,bigint,text) from public,anon,authenticated;
grant execute on function public.factory_recover_v2_plan_task_collision_once(
 uuid,uuid,uuid,uuid,uuid,bigint,bigint,text) to service_role;

commit;
