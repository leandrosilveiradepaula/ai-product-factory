-- Exact-source reinspection recovery after two bounded V2 empty plans.
-- Never treats prior paid output as success or extends immutable journey scope.
begin;
create or replace function public.factory_requeue_v2_issue_discovery_once(
  p_journey_id uuid, p_source_run_id uuid, p_planning_run_id uuid,
  p_command_id uuid, p_actor_id uuid, p_expected_generation bigint,
  p_expected_version bigint, p_expected_source_commit text
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare
  p public.factory_projects%rowtype;
  c public.factory_project_execution_controls%rowtype;
  j public.factory_journeys%rowtype;
  s public.factory_runs%rowtype;
  prior public.factory_runs%rowtype;
  t public.factory_tasks%rowtype;
  old jsonb;
  receipt jsonb;
  new_run uuid;
begin
  if p_journey_id is null or p_source_run_id is null or p_planning_run_id is null
     or p_command_id is null or p_actor_id is null
     or p_expected_generation is null or p_expected_version is null
     or p_expected_source_commit !~ '^[0-9a-f]{40}$'
  then raise exception 'invalid issue discovery retry identity' using errcode='PT400'; end if;
  if not exists(select 1 from public.factory_console_operators o
    where o.user_id=p_actor_id and o.role='admin' and o.is_active=true)
  then raise exception 'issue discovery retry requires active admin' using errcode='PT403'; end if;

  select * into p from public.factory_projects where project_key='crm-infodive'
     and repository='leandrosilveiradepaula/crm-infodive'
     and is_active=true and project_kind='existing' for update;
  if p.id is null then raise exception 'CRM project unavailable' using errcode='PT409'; end if;

  select a.payload into old from public.factory_audit_events a
    where a.project_id=p.id and a.event_type='journey.v2.issue_source_discovery_requeued'
      and a.payload->>'command_id'=p_command_id::text
    order by a.id desc limit 1;
  if old is not null then
    if old->>'journey_id' is distinct from p_journey_id::text
       or old->>'source_run_id' is distinct from p_source_run_id::text
       or old->>'planning_run_id' is distinct from p_planning_run_id::text
       or old->>'actor_id' is distinct from p_actor_id::text
       or old->>'source_commit' is distinct from p_expected_source_commit
       or old->>'generation' is distinct from p_expected_generation::text
       or old->>'control_version' is distinct from p_expected_version::text
    then raise exception 'issue discovery retry replay mismatch' using errcode='PT409'; end if;
    return old->'receipt';
  end if;

  select * into c from public.factory_project_execution_controls where project_id=p.id for update;
  select * into j from public.factory_journeys where id=p_journey_id and project_id=p.id for update;
  select * into s from public.factory_runs where id=p_source_run_id and journey_id=p_journey_id for update;
  select * into prior from public.factory_runs where id=p_planning_run_id and journey_id=p_journey_id for update;
  select * into t from public.factory_tasks where id=s.task_id and project_id=p.id for update;

  if c.state is distinct from 'running' or c.generation is distinct from p_expected_generation
    or c.version is distinct from p_expected_version
    or j.id is null or j.state is distinct from 'executing'
    or j.execution_generation is distinct from c.generation
    or j.source_commit is distinct from p_expected_source_commit
    or j.binding->>'source_commit' is distinct from j.source_commit
    or j.binding->>'execution_generation' is distinct from c.generation::text
    or j.binding->>'integration_branch' is distinct from s.branch_name
    or j.project_policy_version is distinct from 4
    or j.policy_digest is distinct from p.manifest->'journey_delivery_binding_v2'->>'digest'
    or j.request_snapshot->>'text' not like '%issue #209%'
    or j.request_snapshot->>'text' not like '%leandrosilveiradepaula/crm-infodive%'
    or t.id is null or t.journey_id is distinct from j.id or t.status is distinct from 'failed'
    or s.id is null or s.task_id is distinct from t.id or s.status is distinct from 'failed'
    or s.execution_route is distinct from 'direct'
    or s.source_commit is distinct from j.source_commit
    or s.metadata->>'error' is distinct from 'planning has no actionable tasks or decisions'
    or s.metadata->'stages' is distinct from '["reconciliation","gap_analysis","planning"]'::jsonb
    or s.metadata->'journey_binding_v2' is distinct from j.binding
    or s.metadata->>'execution_generation' is distinct from c.generation::text
    or prior.id is null or prior.task_id is distinct from t.id
    or prior.status is distinct from 'failed' or prior.execution_route is distinct from 'direct'
    or prior.source_commit is distinct from s.source_commit
    or prior.metadata->>'error' is distinct from 'planning has no actionable tasks or decisions'
    or prior.metadata->'stages' is distinct from '["planning"]'::jsonb
    or prior.metadata->'journey_binding_v2' is distinct from j.binding
    or prior.metadata#>>'{resume_checkpoint,schema}' is distinct from 'journey_v2_planning_recovery_v1'
    or prior.metadata#>>'{resume_checkpoint,source_run_id}' is distinct from s.id::text
    or prior.metadata->'stage_evidence'->'planning'->>'status' is distinct from 'failed'
    or prior.metadata->'stage_evidence'->'planning'->'output'->>'reason_code' is distinct from 'planning_non_actionable'
    or s.lease_owner is not null or prior.lease_owner is not null
    or s.candidate_commit is not null or prior.candidate_commit is not null
    or j.candidate_commit is not null or j.work_unit_output_commit is not null
    or j.preview_merge_sha is not null or j.production_release_sha is not null
    or not public.factory_control_quiescent(p.id)
  then raise exception 'V2 discovery retry state or source is not eligible' using errcode='PT409'; end if;

  if (select count(*) from public.factory_runs r where r.journey_id=j.id) <> 2
    or exists(select 1 from public.factory_runs r join public.factory_tasks task on r.task_id=task.id
        where task.project_id=p.id and r.status in ('created','queued','running'))
    or exists(select 1 from public.factory_tasks child where child.parent_task_id=t.id)
    or exists(select 1 from public.factory_change_sets cs where cs.journey_id=j.id)
    or exists(select 1 from public.factory_human_gates g where g.run_id in (s.id,prior.id))
    or exists(select 1 from public.factory_deployments d where d.run_id in (s.id,prior.id))
    or exists(select 1 from public.factory_release_reports rr where rr.run_id in (s.id,prior.id))
    or exists(select 1 from public.factory_evaluations ev where ev.run_id in (s.id,prior.id))
    or exists(select 1 from public.factory_audit_events ae
       where ae.project_id=p.id and ae.event_type='journey.v2.issue_source_discovery_requeued'
         and ae.payload->>'journey_id'=j.id::text)
  then raise exception 'V2 discovery retry already advanced or used' using errcode='PT409'; end if;
  -- The failure evidence is durable, and the candidate must not have started.
  -- Recompute all product stages with newly inspected current-source code.
  insert into public.factory_runs(task_id,journey_id,status,execution_route,source_commit,branch_name,metadata)
  values(t.id,j.id,'queued','direct',j.source_commit,j.binding->>'integration_branch',
    (s.metadata-'worker_id'-'claimed_at'-'error'-'stage_evidence') ||
    jsonb_build_object('stages',jsonb_build_array('reconciliation','gap_analysis','planning'),
      'issue_source_discovery_recovery',jsonb_build_object(
        'source_run_id',s.id,'planning_run_id',prior.id,'command_id',p_command_id,
        'previous_error','planning has no actionable tasks or decisions')))
  returning id into new_run;
  update public.factory_tasks set status='queued',updated_at=now() where id=t.id and status='failed';
  if not found then raise exception 'issue discovery retry task CAS lost' using errcode='PT409'; end if;
  receipt:=jsonb_build_object('status','requeued_new_source_inspection',
    'created',true,'journey_id',j.id,'run_id',new_run,'source_run_id',s.id,
    'previous_planning_run_id',prior.id,'generation',c.generation,
    'source_commit',j.source_commit,'release_authorized',false);
  insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  values(p.id,t.id,new_run,'human',p_actor_id::text,'journey.v2.issue_source_discovery_requeued',
    jsonb_build_object('command_id',p_command_id,'journey_id',j.id,
      'source_run_id',s.id,'planning_run_id',prior.id,
      'actor_id',p_actor_id,'generation',p_expected_generation,
      'control_version',p_expected_version,'source_commit',p_expected_source_commit,
      'receipt',receipt));
  return receipt;
end $fn$;
revoke all on function public.factory_requeue_v2_issue_discovery_once(uuid,uuid,uuid,uuid,uuid,bigint,bigint,text)
 from public,anon,authenticated;
grant execute on function public.factory_requeue_v2_issue_discovery_once(uuid,uuid,uuid,uuid,uuid,bigint,bigint,text)
 to service_role;
commit;
