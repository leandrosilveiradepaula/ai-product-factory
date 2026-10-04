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


create or replace function public.factory_resolve_human_gate(
  p_gate_id uuid,
  p_resolution text,
  p_resolved_by text,
  p_note text default null
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
 v_gate public.factory_human_gates%rowtype;
 v_task_id uuid;
 v_project_id uuid;
 v_decision_only boolean;
 v_resume_task_id uuid;
 v_resume_run_id uuid;
 v_resume_external_key text;
begin
 if p_resolution not in ('approved','rejected') then raise exception 'invalid gate resolution'; end if;
 if nullif(btrim(p_resolved_by),'') is null then raise exception 'resolved_by is required'; end if;

 select * into v_gate from public.factory_human_gates where id=p_gate_id for update;
 if v_gate.id is null then raise exception 'gate not found'; end if;
 if v_gate.status <> 'pending' then raise exception 'gate already resolved'; end if;

 select r.task_id,t.project_id,coalesce((r.metadata->>'decision_only')::boolean,false)
 into v_task_id,v_project_id,v_decision_only
 from public.factory_runs r
 join public.factory_tasks t on t.id=r.task_id
 where r.id=v_gate.run_id
 for update of r;
 if v_task_id is null then raise exception 'run not found'; end if;

 if v_gate.gate_type='planning_decision'
    and p_resolution='approved'
    and nullif(btrim(coalesce(p_note,'')),'') is null
 then
   raise exception 'planning decision requires an explicit response';
 end if;

 update public.factory_human_gates
 set status=p_resolution,
     resolved_at=now(),
     resolved_by=btrim(p_resolved_by),
     resolution=jsonb_build_object(
       'resolution',p_resolution,
       'note',p_note,
       'decision_only',v_decision_only
     )
 where id=p_gate_id;

 if v_decision_only then
   update public.factory_runs
   set status='completed',
       finished_at=now(),
       metadata=metadata||jsonb_build_object(
         'human_gate_required',false,
         'gate_resolution',p_resolution,
         'decision_only_resolved',true,
         'decision_outcome',p_resolution,
         'decision_note',p_note
       )
   where id=v_gate.run_id;

   update public.factory_tasks
   set status='completed',updated_at=now()
   where id=v_task_id;

   if v_gate.gate_type='planning_decision' and p_resolution='approved' then
     update public.factory_projects
     set lifecycle_stage='planning',
         manifest=jsonb_set(
           manifest,
           '{human_decisions}',
           coalesce(manifest->'human_decisions','[]'::jsonb)
             || jsonb_build_array(jsonb_build_object(
               'gate_id',p_gate_id,
               'decisions',v_gate.reasons,
               'response',btrim(p_note),
               'resolved_by',btrim(p_resolved_by),
               'resolved_at',now()
             )),
           true
         ),
         updated_at=now()
     where id=v_project_id;

     v_resume_external_key:='planning-decision-reconcile-'||replace(p_gate_id::text,'-','');

     select id into v_resume_task_id
     from public.factory_tasks
     where project_id=v_project_id and external_key=v_resume_external_key
     limit 1;

     if v_resume_task_id is null then
       insert into public.factory_tasks(
         project_id,parent_task_id,external_key,title,description,status,complexity,risk,
         acceptance_criteria,depends_on
       ) values(
         v_project_id,v_task_id,v_resume_external_key,
         'Reconciliar projeto após decisão humana',
         'Reconciliar novamente o projeto usando a decisão humana registrada antes de criar backlog executável.',
         'queued','medium','{}'::jsonb,
         '["decisão humana incluída no contexto","planning refeito antes de materializar implementação"]'::jsonb,
         '[]'::jsonb
       )
       returning id into v_resume_task_id;

       insert into public.factory_runs(task_id,status,execution_route,metadata)
       values(
         v_resume_task_id,'created','direct',
         jsonb_build_object(
           'stages',jsonb_build_array('reconciliation','gap_analysis','planning'),
           'source','planning-decision',
           'reconcile_first',true,
           'decision_gate_id',p_gate_id
         )
       )
       returning id into v_resume_run_id;

       insert into public.factory_audit_events(
         project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
       )
       values(
         v_project_id,v_resume_task_id,v_resume_run_id,
         'system','human-gate-resume','planning_decision.continuation_enqueued',
         jsonb_build_object('gate_id',p_gate_id,'source_decision_run_id',v_gate.run_id)
       );
     else
       select id into v_resume_run_id
       from public.factory_runs
       where task_id=v_resume_task_id
       order by created_at desc
       limit 1;
     end if;
   end if;

 elsif p_resolution='approved' then
   update public.factory_runs
   set status='queued',
       metadata=metadata||jsonb_build_object(
         'human_gate_required',false,
         'gate_resolution','approved'
       )
   where id=v_gate.run_id;

   update public.factory_tasks
   set status='queued_execution',updated_at=now()
   where id=v_task_id;
 else
   update public.factory_runs
   set status='cancelled',
       finished_at=now(),
       metadata=metadata||jsonb_build_object('gate_resolution','rejected')
   where id=v_gate.run_id;

   update public.factory_tasks
   set status='cancelled',updated_at=now()
   where id=v_task_id;
 end if;

 insert into public.factory_decisions(
   project_id,task_id,decision_type,question,decision,decided_by
 )
 values(
   v_project_id,v_task_id,'human_gate_resolution',null,
   jsonb_build_object(
     'gate_id',p_gate_id,
     'gate_type',v_gate.gate_type,
     'resolution',p_resolution,
     'note',p_note,
     'decision_only',v_decision_only,
     'resume_task_id',v_resume_task_id,
     'resume_run_id',v_resume_run_id
   ),
   btrim(p_resolved_by)
 );

 insert into public.factory_audit_events(
   project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
 )
 values(
   v_project_id,v_task_id,v_gate.run_id,'human',btrim(p_resolved_by),'human_gate.resolved',
   jsonb_build_object(
     'gate_id',p_gate_id,
     'gate_type',v_gate.gate_type,
     'resolution',p_resolution,
     'note',p_note,
     'decision_only',v_decision_only,
     'resume_task_id',v_resume_task_id,
     'resume_run_id',v_resume_run_id
   )
 );

 return jsonb_build_object(
   'gate_id',p_gate_id,
   'run_id',v_gate.run_id,
   'task_id',v_task_id,
   'resolution',p_resolution,
   'decision_only',v_decision_only,
   'resume_task_id',v_resume_task_id,
   'resume_run_id',v_resume_run_id,
   'next_state',
     case
       when v_gate.gate_type='planning_decision' and p_resolution='approved'
         then 'planning_reconciliation_queued'
       when v_decision_only then 'decision_recorded'
       when p_resolution='approved' then 'queued'
       else 'cancelled'
     end
 );
end;
$$;

revoke all on function public.factory_resolve_human_gate(uuid,text,text,text)
from public,anon,authenticated;
grant execute on function public.factory_resolve_human_gate(uuid,text,text,text)
to service_role;
