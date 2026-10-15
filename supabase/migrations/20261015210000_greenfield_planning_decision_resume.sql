-- Correct planning-decision continuation for genuinely new projects.
-- Greenfield intake has no existing-project state snapshot, so the original
-- reconciliation stage would fail before reaching the newly approved plan.
-- Imported/existing projects keep reconciliation + gap analysis as before.
-- SECURITY INVOKER / private RPC permissions are deliberately unchanged.
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
 v_project_kind text;
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
 select project_kind into v_project_kind from public.factory_projects where id=v_project_id;
 if v_project_kind is null then raise exception 'gate project not found'; end if;

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
         case when v_project_kind='greenfield' then 'Replanejar projeto novo após decisão humana'
            else 'Reconciliar projeto após decisão humana' end,
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
           'stages',case when v_project_kind='greenfield'
             then jsonb_build_array('planning')
             else jsonb_build_array('reconciliation','gap_analysis','planning') end,
           'source','planning-decision',
           'reconcile_first',(v_project_kind<>'greenfield'),
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

-- Repair only unclaimed, approved greenfield continuations previously
-- enqueued with the invalid imported-project stage sequence.
with corrected as (
 update public.factory_runs r
 set metadata=jsonb_set(
       jsonb_set(r.metadata,'{stages}','["planning"]'::jsonb,true),
       '{reconcile_first}','false'::jsonb,true)
 from public.factory_tasks t
 join public.factory_projects p on p.id=t.project_id
 where r.task_id=t.id
   and p.project_kind='greenfield'
   and r.status='created'
   and r.attempt_count=0
   and t.status='queued'
   and r.metadata->>'source'='planning-decision'
   and r.metadata->'stages'='["reconciliation","gap_analysis","planning"]'::jsonb
   and exists (
      select 1 from public.factory_human_gates g
      where g.id::text=r.metadata->>'decision_gate_id'
        and g.status='approved'
   )
 returning r.id as run_id,t.id as task_id,p.id as project_id
)
insert into public.factory_audit_events(
  project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
)
select project_id,task_id,run_id,'system','migration:greenfield-planning',
       'planning_decision.greenfield_stages_corrected',
       jsonb_build_object(
         'original_stages',jsonb_build_array('reconciliation','gap_analysis','planning'),
         'corrected_stages',jsonb_build_array('planning'),
         'no_paid_model_call',true
       )
from corrected;
