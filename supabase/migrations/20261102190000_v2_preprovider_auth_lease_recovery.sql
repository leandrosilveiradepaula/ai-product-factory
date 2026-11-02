-- One audited recovery for CRM V2 run whose trusted Factory runner lost
-- GitHub App authorization before model invocation or repository mutation.
-- The permanent prevention is in runtime_cli: preflight before claim.
-- No generic retry ceiling increase, no new Journey or model invocation.
begin;

create or replace function public.factory_recover_v2_preprovider_auth_once(
 p_run_id uuid, p_failed_workflow_run_id bigint, p_failed_factory_sha text
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare
 v_project public.factory_projects%rowtype;
 v_control public.factory_project_execution_controls%rowtype;
 v_journey public.factory_journeys%rowtype;
 v_set public.factory_change_sets%rowtype;
 v_unit public.factory_change_set_work_units%rowtype;
 v_run public.factory_runs%rowtype;
 v_task public.factory_tasks%rowtype;
 v_claim timestamptz;
 v_worker text;
 v_gate public.factory_human_gates%rowtype;
begin
 -- A narrow, SHA-bound operational repair, not a generic override of retry
 -- policy. These values are backed by GitHub Actions 41488749263, the
 -- immutable Control Plane audit and source branch verified at its base SHA.
 if p_run_id is distinct from 'b11daad8-dfc2-4a42-ba4a-a98e0d529238'::uuid
    or p_failed_workflow_run_id is distinct from 41488749263
    or p_failed_factory_sha is distinct from '1683787407ed82483288b759d70d413e99fb6d35'
 then raise exception 'preprovider recovery is not authorized for this run' using errcode='PT403'; end if;

 select p.* into v_project from public.factory_projects p
 join public.factory_tasks t on t.project_id=p.id
 join public.factory_runs r on r.task_id=t.id
 where r.id=p_run_id and p.is_active=true
 for update of p;
 if not found then raise exception 'recovery project is unavailable' using errcode='PT409'; end if;

 select * into v_control from public.factory_project_execution_controls
 where project_id=v_project.id for share;
 select * into v_journey from public.factory_journeys
 where project_id=v_project.id and id='bb14e150-2c7e-423b-8e5d-e211dab6225c'::uuid for update;
 select * into v_set from public.factory_change_sets
 where project_id=v_project.id and journey_id=v_journey.id
 and id='3f09952e-0384-46ee-97aa-a46c89346678'::uuid for update;
 select * into v_unit from public.factory_change_set_work_units
 where change_set_id=v_set.id and id='179b34b0-e8f2-4055-bd28-7c7a89de3fc0'::uuid for update;
 select * into v_run from public.factory_runs where id=p_run_id and task_id=v_unit.task_id for update;
 select * into v_task from public.factory_tasks where id=v_run.task_id and project_id=v_project.id for update;

 -- A replay is observationally idempotent and cannot create an extra claim.
 if coalesce(v_run.metadata->>'preprovider_auth_recovery_once','')='factory-v2-preprovider-github-broker-403-v1' then
  return jsonb_build_object('requeued',false,'run_id',v_run.id,
   'journey_id',v_journey.id,'status',v_run.status,'release_authorized',false);
 end if;

 if v_control.state is distinct from 'running' or v_control.generation is distinct from 19
    or v_journey.id is null or v_journey.state is distinct from 'executing'
    or v_journey.execution_generation is distinct from v_control.generation
    or v_journey.source_commit is distinct from 'b1935c8f6e61ae246eb8958673b2a9e18c3da81f'
    or v_journey.binding->>'source_commit' is distinct from v_journey.source_commit
    or v_journey.binding->>'execution_generation' is distinct from v_control.generation::text
    or v_journey.candidate_commit is not null or v_journey.work_unit_output_commit is not null
    or v_journey.preview_merge_sha is not null or v_journey.production_release_sha is not null
    or v_run.id is null or v_task.id is null or v_unit.id is null or v_set.id is null
    or v_run.journey_id is distinct from v_journey.id
    or v_run.metadata->'journey_binding_v2' is distinct from v_journey.binding
    or v_run.metadata->>'execution_generation' is distinct from v_control.generation::text
    or v_run.metadata->>'decision_gate_resolution' is distinct from 'approved'
    or v_run.source_commit is distinct from v_journey.source_commit
    or v_run.execution_route is distinct from 'direct'
    or v_run.status is distinct from 'failed'
    or v_run.last_error is distinct from 'lease expired after maximum attempts'
    or v_run.attempt_count is distinct from 3
    or v_run.lease_owner is not null or v_run.lease_expires_at is not null
    or v_task.status is distinct from 'failed'
    or v_set.status is distinct from 'blocked'
    or v_set.metadata->>'blocker' is distinct from 'builder_retry_exhausted'
    or v_set.source_commit is distinct from v_journey.source_commit
    or v_set.candidate_commit is distinct from v_journey.source_commit
    or v_set.release_run_id is not null
    or v_set.lease_owner is not null or v_set.lease_expires_at is not null
    or v_unit.status is distinct from 'failed'
    or v_unit.base_commit is distinct from v_journey.source_commit
    or v_unit.output_commit is not null
    or v_unit.changed_files is distinct from '[]'::jsonb
 then raise exception 'recovery state, epoch, or side-effect evidence mismatch' using errcode='PT409'; end if;

 select * into v_gate from public.factory_human_gates
 where id='edbee01d-1d23-4e6b-a7a0-0b5a562183d4'::uuid
 and run_id=v_run.id and status='approved' for share;
 if v_gate.id is null or v_gate.resolved_at is null
 then raise exception 'human decision is not durably approved' using errcode='PT409'; end if;

 select a.created_at,a.payload->>'worker_id' into v_claim,v_worker
 from public.factory_audit_events a
 where a.run_id=v_run.id and a.event_type='execution.direct.claimed'
 order by a.created_at desc limit 1;
 if v_claim is null or v_worker is distinct from 'gha-direct-41488749263-0'
    or v_claim is distinct from '2026-11-02T17:13:25.266829+00:00'::timestamptz
    or not exists (select 1 from public.factory_audit_events a
      where a.run_id=v_run.id and a.event_type='run.lease_recovered'
      and a.created_at>v_claim)
    or exists (select 1 from public.factory_audit_events a
      where a.run_id=v_run.id and a.created_at>v_claim
      and a.event_type not in ('run.lease_recovered'))
    or exists (select 1 from public.factory_tool_usage u
      where u.run_id=v_run.id and u.created_at>=v_claim)
    or exists (select 1 from public.factory_change_set_work_units u
      where u.change_set_id=v_set.id and u.id<>v_unit.id
      and (u.output_commit is not null or u.status in ('running','completed','integrated')))
    or exists (select 1 from public.factory_run_agent_assignments a
      where a.run_id=v_run.id and a.status in ('assigned','claimed'))
    or exists (select 1 from public.factory_agent_scope_locks l
      where l.run_id=v_run.id and l.released_at is null and l.lease_expires_at>now())
 then raise exception 'post-claim effects or active assignments prevent recovery' using errcode='PT409'; end if;

 update public.factory_runs set status='queued',last_error=null,finished_at=null,
    lease_owner=null,lease_expires_at=null,
    metadata=(metadata-'execution_worker_id'-'execution_claimed_at') ||
      jsonb_build_object('preprovider_auth_recovery_once','factory-v2-preprovider-github-broker-403-v1',
      'preprovider_auth_recovery_at',now(),
      'preprovider_auth_recovery_factory_run_id',p_failed_workflow_run_id,
      'preprovider_auth_recovery_factory_sha',p_failed_factory_sha,
      'preprovider_auth_recovery_preserved_attempt_count',attempt_count)
 where id=v_run.id and status='failed';
 update public.factory_tasks set status='queued_execution',updated_at=now() where id=v_task.id;
 update public.factory_change_set_work_units set status='queued',updated_at=now() where id=v_unit.id;
 update public.factory_change_sets set status='building',lease_owner=null,lease_expires_at=null,
    updated_at=now(),metadata=(metadata-'blocker')||jsonb_build_object(
     'preprovider_auth_recovery',jsonb_build_object('run_id',v_run.id,
        'factory_workflow_run_id',p_failed_workflow_run_id,'at',now(),
        'original_attempt_count',v_run.attempt_count))
 where id=v_set.id;

 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,v_task.id,v_run.id,'system','preprovider-auth-recovery',
  'journey.v2.preprovider_auth_lease_requeued',jsonb_build_object(
    'journey_id',v_journey.id,'change_set_id',v_set.id,'work_unit_id',v_unit.id,
    'generation',v_control.generation,'source_commit',v_journey.source_commit,
    'failed_factory_workflow_id',p_failed_workflow_run_id,
    'failed_factory_sha',p_failed_factory_sha,
    'failure_code','github_app_token_event_not_allowed',
    'model_calls_after_claim',0,'new_run_created',false,
    'attempt_count_preserved',v_run.attempt_count,'release_authorized',false));
 return jsonb_build_object('requeued',true,'run_id',v_run.id,
   'journey_id',v_journey.id,'change_set_id',v_set.id,'work_unit_id',v_unit.id,
   'generation',v_control.generation,'attempt_count',v_run.attempt_count,
   'source_commit',v_journey.source_commit,'release_authorized',false);
end;
$fn$;
revoke all on function public.factory_recover_v2_preprovider_auth_once(uuid,bigint,text) from public,anon,authenticated;
grant execute on function public.factory_recover_v2_preprovider_auth_once(uuid,bigint,text) to service_role;
commit;
