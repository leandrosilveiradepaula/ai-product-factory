create or replace function public.factory_supersede_stale_planning_gates(
  p_project_id uuid,
  p_keep_gate_id uuid default null
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_row record;
  v_superseded integer := 0;
begin
  if p_project_id is null then raise exception 'project_id is required'; end if;

  for v_row in
    select
      g.id as gate_id,
      g.run_id,
      r.task_id,
      g.requested_at
    from public.factory_human_gates g
    join public.factory_runs r on r.id=g.run_id
    join public.factory_tasks t on t.id=r.task_id
    where t.project_id=p_project_id
      and g.gate_type='planning_decision'
      and g.status='pending'
      and (p_keep_gate_id is null or g.id<>p_keep_gate_id)
    order by g.requested_at,g.id
    for update of g
  loop
    update public.factory_human_gates
    set status='rejected',
        resolved_at=now(),
        resolved_by='system:planning-gate-supersession',
        resolution=jsonb_build_object(
          'resolution','superseded',
          'reason','newer_planning_context_exists',
          'superseded_by_gate_id',p_keep_gate_id
        )
    where id=v_row.gate_id
      and status='pending';

    update public.factory_runs
    set status='cancelled',
        finished_at=coalesce(finished_at,now()),
        metadata=metadata||jsonb_build_object(
          'superseded',true,
          'superseded_by_gate_id',p_keep_gate_id,
          'superseded_reason','newer_planning_context_exists'
        )
    where id=v_row.run_id
      and status not in ('completed','cancelled','failed');

    update public.factory_tasks
    set status='cancelled',updated_at=now()
    where id=v_row.task_id
      and status not in ('completed','cancelled','failed');

    insert into public.factory_audit_events(
      project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
    )
    values(
      p_project_id,v_row.task_id,v_row.run_id,
      'system','planning-gate-supersession','human_gate.superseded',
      jsonb_build_object(
        'gate_id',v_row.gate_id,
        'gate_type','planning_decision',
        'superseded_by_gate_id',p_keep_gate_id,
        'reason','newer_planning_context_exists'
      )
    );

    v_superseded:=v_superseded+1;
  end loop;

  return jsonb_build_object(
    'project_id',p_project_id,
    'keep_gate_id',p_keep_gate_id,
    'superseded_gates',v_superseded
  );
end;
$$;

revoke all on function public.factory_supersede_stale_planning_gates(uuid,uuid)
from public,anon,authenticated;
grant execute on function public.factory_supersede_stale_planning_gates(uuid,uuid)
to service_role;


do $$
declare
  v_project record;
begin
  for v_project in
    select distinct
      t.project_id,
      (
        select g2.id
        from public.factory_human_gates g2
        join public.factory_runs r2 on r2.id=g2.run_id
        join public.factory_tasks t2 on t2.id=r2.task_id
        where t2.project_id=t.project_id
          and g2.gate_type='planning_decision'
        order by g2.requested_at desc,g2.id desc
        limit 1
      ) as latest_gate_id
    from public.factory_human_gates g
    join public.factory_runs r on r.id=g.run_id
    join public.factory_tasks t on t.id=r.task_id
    where g.gate_type='planning_decision'
      and g.status='pending'
  loop
    perform public.factory_supersede_stale_planning_gates(
      v_project.project_id,
      v_project.latest_gate_id
    );
  end loop;
end;
$$;


create or replace function public.factory_persist_product_stage(
  p_run_id uuid,
  p_stage text,
  p_output jsonb
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_task_id uuid;
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

  select r.task_id,t.project_id into v_task_id,v_project_id
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
        v_external_key:='plan-'||substr(md5(coalesce(v_item->>'title',v_item::text)),1,16);
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
$$;

revoke all on function public.factory_persist_product_stage(uuid,text,jsonb)
from public,anon,authenticated;
grant execute on function public.factory_persist_product_stage(uuid,text,jsonb)
to service_role;
