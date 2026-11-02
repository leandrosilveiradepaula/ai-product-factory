-- Journey V2: durable, evidence-bound material requirement decision for a
-- blocked implementation. The approval resumes *only* the same Work Unit.
-- Never auto-approves a product decision or a production merge.
begin;

create or replace function public.factory_open_v2_work_unit_decision_gate(
 p_run_id uuid, p_decision jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare
 v_run public.factory_runs%rowtype;
 v_task public.factory_tasks%rowtype;
 v_unit public.factory_change_set_work_units%rowtype;
 v_set public.factory_change_sets%rowtype;
 v_project public.factory_projects%rowtype;
 v_control public.factory_project_execution_controls%rowtype;
 v_journey public.factory_journeys%rowtype;
 v_gate public.factory_human_gates%rowtype;
 v_question text;
 v_why text;
 v_quote text;
 v_reason text;
 v_source_path text;
 v_reasons jsonb;
 v_anchor jsonb;
begin
 if p_run_id is null or jsonb_typeof(p_decision) is distinct from 'object'
  or (select count(*) from jsonb_object_keys(p_decision))<>6
  or p_decision->>'decision_kind' is distinct from 'material_requirement_change'
 then raise exception 'invalid V2 material decision payload' using errcode='PT400'; end if;
 v_question:=p_decision->>'question';v_why:=p_decision->>'why_needed';
 v_quote:=p_decision->>'governance_quote';v_source_path:=p_decision->>'governance_path';
 v_reason:=p_decision->>'reason';
 if v_question is null or length(v_question) not between 20 and 400
  or v_why is null or length(v_why) not between 25 and 750
  or v_quote is null or length(v_quote) not between 35 and 480
  or v_reason is null or length(v_reason) not between 1 and 1000
  or v_source_path not in ('AGENTS.md','docs/codex/CURRENT_TASK.md')
  or (lower(v_quote) not like '%decisão humana%'
     and lower(v_quote) not like '%human decision%'
     and lower(v_quote) not like '%human approval%'
     and lower(v_quote) not like '%autorização explícita%')
 then raise exception 'material decision lacks quoted human authority' using errcode='PT400'; end if;
 -- Acquire the project-wide lock before altering any queue or gate state.
 select * into v_run from public.factory_runs where id=p_run_id;
 select * into v_task from public.factory_tasks where id=v_run.task_id;
 select * into v_project from public.factory_projects
   where id=v_task.project_id and is_active=true for update;
 select * into v_control from public.factory_project_execution_controls
   where project_id=v_project.id for update;
 select * into v_journey from public.factory_journeys
   where id=v_run.journey_id and project_id=v_project.id for update;
 select * into v_unit from public.factory_change_set_work_units
   where run_id=p_run_id for update;
 select * into v_set from public.factory_change_sets
   where id=v_unit.change_set_id and project_id=v_project.id for update;
 select * into v_run from public.factory_runs where id=p_run_id for update;
 select * into v_task from public.factory_tasks where id=v_run.task_id for update;
 if v_project.id is null or v_control.project_id is null
  or v_control.state is distinct from 'running'
  or v_journey.id is null or v_journey.state is distinct from 'executing'
  or v_journey.execution_generation is distinct from v_control.generation
  or v_journey.binding->>'execution_generation' is distinct from v_control.generation::text
  or v_journey.binding->>'binding_version' is distinct from '2'
  or v_journey.binding->>'source_commit' is distinct from v_journey.source_commit
  or v_run.metadata->'journey_binding_v2' is distinct from v_journey.binding
  or v_run.metadata->>'execution_generation' is distinct from v_control.generation::text
  or v_run.journey_id is distinct from v_journey.id
  or v_run.source_commit is distinct from v_journey.source_commit
  or v_task.id is null or v_task.journey_id is distinct from v_journey.id
  or v_unit.id is null or v_unit.task_id is distinct from v_task.id
  or v_unit.output_commit is not null or v_unit.wave is distinct from v_set.current_wave
  or v_set.id is null or v_set.journey_id is distinct from v_journey.id
  or v_set.source_commit is distinct from v_journey.source_commit
  or v_set.candidate_commit is distinct from v_journey.source_commit
  or v_unit.base_commit is distinct from v_journey.source_commit
  or v_set.lease_owner is not null or v_set.lease_expires_at is not null
  or v_journey.candidate_commit is not null or v_journey.work_unit_output_commit is not null
  or v_journey.preview_merge_sha is not null or v_journey.production_release_sha is not null
 then raise exception 'V2 human gate source/epoch binding failed' using errcode='PT409'; end if;
 v_reasons:=jsonb_build_array(jsonb_build_object(
   'decision_key','v2-material-'||v_unit.id::text,
   'decision_kind','material_requirement_change',
   'question',v_question,'why_needed',v_why,
   'governance_path',v_source_path,'governance_quote',v_quote));
 select * into v_gate from public.factory_human_gates
   where run_id=p_run_id and status='pending' for update;
 if v_gate.id is not null then
  if v_gate.gate_type is distinct from 'material_requirement_change'
    or v_gate.reasons is distinct from v_reasons
    or v_run.status is distinct from 'awaiting_human'
    or v_task.status is distinct from 'awaiting_human'
    or v_run.metadata->>'requested_action' is distinct from 'resolve_v2_material_decision'
    or v_run.metadata->>'decision_gate_id' is distinct from v_gate.id::text
  then raise exception 'pending gate replay identity mismatch' using errcode='PT409'; end if;
  return jsonb_build_object('status','awaiting_human','created',false,
    'gate_id',v_gate.id,'run_id',p_run_id,'journey_id',v_journey.id,
    'work_unit_id',v_unit.id,'release_authorized',false);
 end if;
 if exists(select 1 from public.factory_human_gates g where g.run_id=p_run_id)
    or exists(select 1 from public.factory_audit_events e where e.run_id=p_run_id
      and e.event_type='journey.v2.material_decision_gate_opened')
 then raise exception 'V2 material gate was already handled' using errcode='PT409'; end if;
 if v_run.lease_owner is not null or v_run.lease_expires_at is not null
   or v_run.candidate_commit is not null
 then
   -- Running claim is allowed to own the lease while opening its own gate.
   if v_run.status is distinct from 'running' then
     raise exception 'material decision requires unleased blocked or live worker' using errcode='PT409';
   end if;
 end if;
 if v_run.status='running' and v_unit.status='running'
   and v_set.status='building' then
   perform public.factory_block_change_set_work_unit(
     p_run_id,v_reason,'repository_governance');
   select * into v_run from public.factory_runs where id=p_run_id for update;
   select * into v_task from public.factory_tasks where id=v_run.task_id for update;
   select * into v_unit from public.factory_change_set_work_units
      where run_id=p_run_id for update;
   select * into v_set from public.factory_change_sets
      where id=v_unit.change_set_id for update;
 end if;
 if v_run.status is distinct from 'blocked'
   or v_task.status is distinct from 'blocked'
   or v_unit.status is distinct from 'blocked'
   or v_set.status is distinct from 'blocked'
   or v_set.metadata->'blocker'->>'type' is distinct from 'repository_governance'
   or v_set.metadata->'blocker'->>'reason' is distinct from v_reason
   or v_set.metadata->'blocker'->>'work_unit_id' is distinct from v_unit.id::text
   or v_set.metadata->'blocker'->>'run_id' is distinct from p_run_id::text
   or v_run.lease_owner is not null or v_run.lease_expires_at is not null
   or v_set.lease_owner is not null or v_set.lease_expires_at is not null
 then raise exception 'material gate requires exact blocked governance state' using errcode='PT409'; end if;
 v_anchor:=jsonb_build_object(
  'schema','v2_material_decision_gate_v1',
  'project_id',v_project.id,'journey_id',v_journey.id,
  'change_set_id',v_set.id,'work_unit_id',v_unit.id,
  'generation',v_control.generation,'version',v_control.version,
  'source_commit',v_journey.source_commit,'governance_path',v_source_path);
 insert into public.factory_human_gates(run_id,gate_type,status,reasons,resolution)
 values(p_run_id,'material_requirement_change','pending',v_reasons,
        jsonb_build_object('v2_anchor',v_anchor))
 returning * into v_gate;
 update public.factory_runs set status='awaiting_human',
   metadata=metadata||jsonb_build_object('requested_action','resolve_v2_material_decision',
     'decision_gate_id',v_gate.id,'decision_work_unit_id',v_unit.id),
   lease_owner=null,lease_expires_at=null
 where id=p_run_id and status='blocked';
 if not found then raise exception 'material gate run CAS lost' using errcode='PT409'; end if;
 update public.factory_tasks set status='awaiting_human',updated_at=now()
 where id=v_task.id and status='blocked';
 if not found then raise exception 'material gate task CAS lost' using errcode='PT409'; end if;
 insert into public.factory_audit_events(
  project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,v_task.id,p_run_id,'system','v2-material-gate',
  'journey.v2.material_decision_gate_opened',jsonb_build_object(
  'gate_id',v_gate.id,'anchor',v_anchor,'question',v_question));
 return jsonb_build_object('status','awaiting_human','created',true,
  'gate_id',v_gate.id,'run_id',p_run_id,'journey_id',v_journey.id,
  'work_unit_id',v_unit.id,'release_authorized',false);
end $fn$;

create or replace function public.factory_resolve_v2_material_decision_gate(
 p_gate_id uuid,p_resolution text,p_note text,p_actor_id uuid
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare
 g public.factory_human_gates%rowtype;
 p public.factory_projects%rowtype;
 c public.factory_project_execution_controls%rowtype;
 j public.factory_journeys%rowtype;
 r public.factory_runs%rowtype;
 t public.factory_tasks%rowtype;
 s public.factory_change_sets%rowtype;
 u public.factory_change_set_work_units%rowtype;
 anchor jsonb;
 decision jsonb;
 receipt jsonb;
begin
 if p_gate_id is null or p_actor_id is null
   or p_resolution not in ('approved','rejected')
   or length(coalesce(p_note,''))>2500
   or (p_resolution='approved' and length(btrim(coalesce(p_note,'')))<8)
 then raise exception 'invalid human material decision' using errcode='PT400'; end if;
 if not exists(select 1 from public.factory_console_operators o
     where o.user_id=p_actor_id and o.is_active=true and o.role='admin')
 then raise exception 'active Factory administrator required' using errcode='PT403'; end if;
 select * into g from public.factory_human_gates
   where id=p_gate_id for update;
 if g.id is null or g.gate_type is distinct from 'material_requirement_change'
  or g.resolution#>>'{v2_anchor,schema}' is distinct from 'v2_material_decision_gate_v1'
 then raise exception 'not a V2 material decision gate' using errcode='PT409'; end if;
 if g.status<>'pending' then
   if g.status=p_resolution and g.resolved_by=p_actor_id::text
      and g.resolution->>'note' is not distinct from p_note
   then return g.resolution->'receipt'; end if;
   raise exception 'material gate already resolved differently' using errcode='PT409';
 end if;
 anchor:=g.resolution->'v2_anchor';
 select * into r from public.factory_runs where id=g.run_id;
 select * into t from public.factory_tasks where id=r.task_id;
 select * into p from public.factory_projects
    where id=t.project_id and is_active=true for update;
 select * into c from public.factory_project_execution_controls
    where project_id=p.id for update;
 select * into j from public.factory_journeys
    where id=r.journey_id and project_id=p.id for update;
 select * into u from public.factory_change_set_work_units
    where run_id=r.id and id=(anchor->>'work_unit_id')::uuid for update;
 select * into s from public.factory_change_sets
    where id=u.change_set_id and project_id=p.id for update;
 select * into r from public.factory_runs where id=g.run_id for update;
 select * into t from public.factory_tasks where id=r.task_id for update;
 if p.id is null or c.project_id is null or j.id is null or u.id is null
   or s.id is null or t.id is null
   or c.state is distinct from 'running'
   or c.generation is distinct from (anchor->>'generation')::bigint
   or c.version is distinct from (anchor->>'version')::bigint
   or j.state is distinct from 'executing'
   or j.execution_generation is distinct from c.generation
   or j.binding->>'source_commit' is distinct from j.source_commit
   or j.binding->>'execution_generation' is distinct from c.generation::text
   or j.id::text is distinct from anchor->>'journey_id'
   or p.id::text is distinct from anchor->>'project_id'
   or s.id::text is distinct from anchor->>'change_set_id'
   or j.source_commit is distinct from anchor->>'source_commit'
   or r.metadata->'journey_binding_v2' is distinct from j.binding
   or r.metadata->>'decision_gate_id' is distinct from g.id::text
   or r.metadata->>'requested_action' is distinct from 'resolve_v2_material_decision'
   or r.status is distinct from 'awaiting_human'
   or t.status is distinct from 'awaiting_human'
   or t.journey_id is distinct from j.id
   or u.task_id is distinct from t.id
   or u.status is distinct from 'blocked'
   or u.output_commit is not null
   or u.base_commit is distinct from j.source_commit
   or r.candidate_commit is not null
   or r.lease_owner is not null or r.lease_expires_at is not null
   or s.status is distinct from 'blocked'
   or s.source_commit is distinct from j.source_commit
   or s.candidate_commit is distinct from j.source_commit
   or s.journey_id is distinct from j.id
   or s.lease_owner is not null or s.lease_expires_at is not null
   or j.candidate_commit is not null or j.work_unit_output_commit is not null
   or j.preview_merge_sha is not null or j.production_release_sha is not null
   or not public.factory_control_quiescent(p.id)
 then raise exception 'V2 decision gate state/epoch conflict' using errcode='PT409'; end if;
 receipt:=jsonb_build_object(
   'status',case when p_resolution='approved' then 'resumed' else 'decision_rejected' end,
   'gate_id',g.id,'run_id',r.id,'work_unit_id',u.id,
   'change_set_id',s.id,'journey_id',j.id,
   'generation',c.generation,'source_commit',j.source_commit,
   'release_authorized',false);
 decision:=jsonb_build_object('gate_id',g.id,'journey_id',j.id,
    'change_set_id',s.id,'work_unit_id',u.id,'decision_kind','material_requirement_change',
    'question',g.reasons->0->>'question','response',p_note,
    'actor_id',p_actor_id,'source_commit',j.source_commit);
 if p_resolution='approved' then
  update public.factory_projects set
    manifest=jsonb_set(manifest,'{human_decisions}',
      case when jsonb_typeof(manifest->'human_decisions')='array'
        then manifest->'human_decisions' else '[]'::jsonb end
      || jsonb_build_array(decision),true),
    updated_at=now()
  where id=p.id;
  update public.factory_change_sets set status='building',
    metadata=(metadata-'blocker')||jsonb_build_object('material_decision_gate_id',g.id),
    updated_at=now()
  where id=s.id and status='blocked';
  if not found then raise exception 'material decision change set CAS lost' using errcode='PT409'; end if;
  update public.factory_change_set_work_units set status='queued',updated_at=now()
  where id=u.id and status='blocked';
  if not found then raise exception 'material decision work unit CAS lost' using errcode='PT409'; end if;
  update public.factory_runs set status='queued',finished_at=null,last_error=null,
    metadata=(metadata-'requested_action')||jsonb_build_object(
      'decision_gate_resolution','approved','material_decision_gate_id',g.id),
    lease_owner=null,lease_expires_at=null
  where id=r.id and status='awaiting_human';
  if not found then raise exception 'material decision run CAS lost' using errcode='PT409'; end if;
  update public.factory_tasks set status='queued_execution',updated_at=now()
  where id=t.id and status='awaiting_human';
  if not found then raise exception 'material decision task CAS lost' using errcode='PT409'; end if;
 else
  update public.factory_runs set status='blocked',
    metadata=(metadata-'requested_action')||jsonb_build_object(
      'decision_gate_resolution','rejected','material_decision_gate_id',g.id)
  where id=r.id and status='awaiting_human';
  update public.factory_tasks set status='blocked',updated_at=now()
  where id=t.id and status='awaiting_human';
 end if;
 update public.factory_human_gates set status=p_resolution,resolved_at=now(),
   resolved_by=p_actor_id::text,
   resolution=jsonb_build_object('v2_anchor',anchor,'note',p_note,'resolution',p_resolution,
     'receipt',receipt)
 where id=g.id and status='pending';
 if not found then raise exception 'material gate decision CAS lost' using errcode='PT409'; end if;
 insert into public.factory_decisions(
   project_id,task_id,decision_type,question,decision,decided_by)
 values(p.id,t.id,'human_gate_resolution',g.reasons->0->>'question',
    jsonb_build_object('gate_id',g.id,'decision',decision,'resolution',p_resolution),
    p_actor_id::text);
 insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(p.id,t.id,r.id,'human',p_actor_id::text,
   'journey.v2.material_decision_gate_resolved',
   jsonb_build_object('gate_id',g.id,'resolution',p_resolution,
      'source_commit',j.source_commit,'receipt',receipt));
 return receipt;
end $fn$;

-- Failure handling cannot demote an already opened material decision gate.
CREATE OR REPLACE FUNCTION public.factory_block_change_set_work_unit(p_run_id uuid, p_reason text, p_blocker_type text DEFAULT 'implementation_blocked'::text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  v_unit public.factory_change_set_work_units%rowtype;
  v_set public.factory_change_sets%rowtype;
  v_task public.factory_tasks%rowtype;
  v_reason text;
  v_blocker_type text;
begin
  if exists(select 1 from public.factory_human_gates g
      where g.run_id=p_run_id and g.status='pending'
        and g.resolution#>>'{v2_anchor,schema}'='v2_material_decision_gate_v1')
  then raise exception 'pending V2 material gate cannot be bypassed by blocker'
      using errcode='PT409'; end if;
  v_reason:=left(btrim(coalesce(p_reason,'')),1000);
  v_blocker_type:=left(btrim(coalesce(p_blocker_type,'')),120);
  if v_reason='' then raise exception 'blocker reason is required'; end if;
  if v_blocker_type='' then raise exception 'blocker type is required'; end if;

  select * into v_unit
  from public.factory_change_set_work_units
  where run_id=p_run_id
  for update;
  if not found then raise exception 'change-set work unit not found'; end if;

  select * into v_set
  from public.factory_change_sets
  where id=v_unit.change_set_id
  for update;
  if not found then raise exception 'change set not found'; end if;

  select * into v_task
  from public.factory_tasks
  where id=v_unit.task_id
  for update;
  if not found then raise exception 'task not found'; end if;

  update public.factory_change_set_work_units
  set status='blocked',updated_at=now()
  where id=v_unit.id
    and status in ('pending','queued','running','failed');

  update public.factory_runs
  set status='blocked',
      finished_at=coalesce(finished_at,now()),
      last_error=v_reason,
      lease_owner=null,
      lease_expires_at=null,
      metadata=metadata||jsonb_build_object(
        'implementation_blocked',true,
        'blocker_type',v_blocker_type,
        'blocker_reason',v_reason
      )
  where id=p_run_id
    and status not in ('completed','cancelled');

  update public.factory_tasks
  set status='blocked',updated_at=now()
  where id=v_task.id
    and status not in ('completed','cancelled');

  update public.factory_change_sets
  set status='blocked',
      lease_owner=null,
      lease_expires_at=null,
      metadata=metadata||jsonb_build_object(
        'blocker',jsonb_build_object(
          'type',v_blocker_type,
          'reason',v_reason,
          'run_id',p_run_id,
          'work_unit_id',v_unit.id,
          'recorded_at',now()
        )
      ),
      updated_at=now()
  where id=v_set.id
    and status not in ('completed','superseded');

  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  )
  values(
    v_set.project_id,v_task.id,p_run_id,
    'system','change-set-builder','change_set.work_unit.blocked',
    jsonb_build_object(
      'change_set_id',v_set.id,
      'work_unit_id',v_unit.id,
      'blocker_type',v_blocker_type,
      'reason',v_reason
    )
  );

  return jsonb_build_object(
    'change_set_id',v_set.id,
    'work_unit_id',v_unit.id,
    'run_id',p_run_id,
    'status','blocked',
    'blocker_type',v_blocker_type,
    'reason',v_reason
  );
end;
$function$
;

-- Prevent the legacy gate resolver from bypassing Work Unit + Change Set CAS.
CREATE OR REPLACE FUNCTION public.factory_resolve_human_gate(p_gate_id uuid, p_resolution text, p_resolved_by text, p_note text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
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
 if v_gate.gate_type='material_requirement_change' and v_gate.resolution#>>'{v2_anchor,schema}'='v2_material_decision_gate_v1' then
   raise exception 'Journey V2 material gate requires atomic specialized resolution' using errcode='PT409';
 end if;
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
         then case when v_project_kind='greenfield' then 'planning_replan_queued'
                   else 'planning_reconciliation_queued' end
       when v_decision_only then 'decision_recorded'
       when p_resolution='approved' then 'queued'
       else 'cancelled'
     end
 );
end;
$function$
;

revoke all on function public.factory_open_v2_work_unit_decision_gate(uuid,jsonb)
 from public,anon,authenticated;
grant execute on function public.factory_open_v2_work_unit_decision_gate(uuid,jsonb)
 to service_role;
revoke all on function public.factory_resolve_v2_material_decision_gate(uuid,text,text,uuid)
 from public,anon,authenticated;
grant execute on function public.factory_resolve_v2_material_decision_gate(uuid,text,text,uuid)
 to service_role;
commit;
