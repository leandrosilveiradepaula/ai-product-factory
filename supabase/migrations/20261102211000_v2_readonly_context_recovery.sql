-- Exact, once-only recovery of a V2 builder blocked by an insufficient
-- immutable source snapshot after a previously APPROVED material decision.
-- This does not reset attempts, change policy, make model calls, open gates
-- or authorize any GitHub merge. Run only after the code fix is merged.
begin;

create or replace function public.factory_recover_v2_readonly_context_once(
 p_run_id uuid, p_failed_workflow_run_id bigint, p_failed_factory_sha text,
 p_observed_work_branch_sha text
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare
 v_project public.factory_projects%rowtype;
 v_control public.factory_project_execution_controls%rowtype;
 v_journey public.factory_journeys%rowtype;
 v_set public.factory_change_sets%rowtype;
 v_unit public.factory_change_set_work_units%rowtype;
 v_run public.factory_runs%rowtype;
 v_task public.factory_tasks%rowtype;
 v_gate public.factory_human_gates%rowtype;
 v_claim timestamptz;
 v_worker text;
 v_last_event text;
 v_model_count int;
 v_model_cost numeric;
 v_base text := 'b1935c8f6e61ae246eb8958673b2a9e18c3da81f';
 v_incident text := 'v2-readonly-source-context-41523358424-v1';
begin
 if p_run_id is distinct from 'b11daad8-dfc2-4a42-ba4a-a98e0d529238'::uuid
    or p_failed_workflow_run_id is distinct from 41523358424
    or p_failed_factory_sha is distinct from '81de8b1d5c0fd41948fae657b2d9ce31ed42d11e'
    or p_observed_work_branch_sha is distinct from v_base
 then raise exception 'unknown V2 read-only context recovery incident' using errcode='PT403'; end if;

 select p.* into v_project from public.factory_projects p
 join public.factory_tasks t on t.project_id=p.id
 join public.factory_runs r on r.task_id=t.id
 where r.id=p_run_id and p.is_active=true
 and p.repository='leandrosilveiradepaula/crm-infodive'
 for update of p;
 if v_project.id is null then raise exception 'incident project is not active' using errcode='PT409'; end if;
 select * into v_control from public.factory_project_execution_controls
 where project_id=v_project.id for share;
 select * into v_journey from public.factory_journeys
 where id='bb14e150-2c7e-423b-8e5d-e211dab6225c'::uuid
 and project_id=v_project.id for update;
 select * into v_set from public.factory_change_sets
 where id='3f09952e-0384-46ee-97aa-a46c89346678'::uuid
 and journey_id=v_journey.id and project_id=v_project.id for update;
 select * into v_unit from public.factory_change_set_work_units
 where id='179b34b0-e8f2-4055-bd28-7c7a89de3fc0'::uuid
 and change_set_id=v_set.id for update;
 select * into v_run from public.factory_runs
 where id=p_run_id and task_id=v_unit.task_id and journey_id=v_journey.id for update;
 select * into v_task from public.factory_tasks
 where id=v_run.task_id and project_id=v_project.id for update;

 if coalesce(v_run.metadata->>'v2_readonly_context_recovery_once','')=v_incident then
    return jsonb_build_object('requeued',false,'run_id',v_run.id,
      'status',v_run.status,'attempt_count',v_run.attempt_count,
      'release_authorized',false);
 end if;

 if v_run.id is null or v_task.id is null or v_unit.id is null or v_set.id is null
    or v_journey.id is null
    or v_control.state is distinct from 'running' or v_control.generation is distinct from 19
    or v_journey.state is distinct from 'executing'
    or v_journey.execution_generation is distinct from v_control.generation
    or v_journey.source_commit is distinct from v_base
    or v_journey.binding->>'source_commit' is distinct from v_base
    or v_journey.binding->>'execution_generation' is distinct from v_control.generation::text
    or v_journey.candidate_commit is not null
    or v_journey.work_unit_output_commit is not null
    or v_journey.preview_merge_sha is not null
    or v_journey.production_release_sha is not null
    or v_run.status is distinct from 'blocked'
    or v_run.attempt_count is distinct from 4
    or v_run.execution_route is distinct from 'direct'
    or v_run.source_commit is distinct from v_base
    or v_run.lease_owner is not null or v_run.lease_expires_at is not null
    or v_run.metadata->>'execution_generation' is distinct from '19'
    or v_run.metadata->'journey_binding_v2' is distinct from v_journey.binding
    or v_run.metadata->>'decision_gate_resolution' is distinct from 'approved'
    or v_run.metadata->>'preprovider_auth_recovery_once' is distinct from 'factory-v2-preprovider-github-broker-403-v1'
    or v_task.status is distinct from 'blocked'
    or v_set.status is distinct from 'blocked'
    or v_set.source_commit is distinct from v_base
    or v_set.candidate_commit is distinct from v_base
    or v_set.release_run_id is not null or v_set.lease_owner is not null
    or v_set.lease_expires_at is not null
    or v_set.metadata->'blocker'->>'type' is distinct from 'repository_governance'
    or v_set.metadata->'blocker'->>'run_id' is distinct from v_run.id::text
    or v_set.metadata->'blocker'->>'work_unit_id' is distinct from v_unit.id::text
    or v_unit.status is distinct from 'blocked'
    or v_unit.base_commit is distinct from v_base
    or v_unit.output_commit is not null
    or v_unit.changed_files is distinct from '[]'::jsonb
 then raise exception 'source, epoch, gate, or output state changed' using errcode='PT409'; end if;

 select * into v_gate from public.factory_human_gates
 where id='edbee01d-1d23-4e6b-a7a0-0b5a562183d4'::uuid and run_id=v_run.id
 and status='approved' and gate_type='material_requirement_change'
 for share;
 if v_gate.id is null or v_gate.resolved_at is null
    or v_gate.resolution->>'resolution' is distinct from 'approved'
 then raise exception 'human decision is not durably approved' using errcode='PT409'; end if;

 select created_at,payload->>'worker_id' into v_claim,v_worker
 from public.factory_audit_events where run_id=v_run.id
 and event_type='execution.direct.claimed'
 order by created_at desc limit 1;
 if v_claim is distinct from '2026-11-02T20:55:56.216782+00:00'::timestamptz
    or v_worker is distinct from 'gha-direct-41523358424-0'
 then raise exception 'exact last claim does not match incident' using errcode='PT409'; end if;
 select event_type into v_last_event from public.factory_audit_events
 where run_id=v_run.id order by created_at desc,id desc limit 1;
 if v_last_event is distinct from 'change_set.work_unit.blocked'
    or not exists (select 1 from public.factory_audit_events
       where run_id=v_run.id and event_type='change_set.work_unit.blocked'
       and created_at='2026-11-02T20:56:27.634693+00:00'::timestamptz)
    or exists (select 1 from public.factory_run_agent_assignments
       where run_id=v_run.id and status in ('assigned','claimed'))
    or exists (select 1 from public.factory_agent_scope_locks
       where run_id=v_run.id and released_at is null and lease_expires_at>now())
    or exists (select 1 from public.factory_change_set_work_units
       where change_set_id=v_set.id and id<>v_unit.id
       and (output_commit is not null or status in ('running','completed','integrated')))
 then raise exception 'unexpected side effect or active lease prevents recovery' using errcode='PT409'; end if;

 select count(*),sum(estimated_cost) into v_model_count,v_model_cost
 from public.factory_tool_usage where run_id=v_run.id
 and created_at>=v_claim and tool_family='openai' and operation='model_call';
 if v_model_count is distinct from 1 or v_model_cost is null
    or v_model_cost>0.50 or v_model_cost<=0
    or exists(select 1 from public.factory_tool_usage
       where run_id=v_run.id and created_at>=v_claim
         and (tool_family<>'openai' or operation<>'model_call' or estimated_cost is null))
 then raise exception 'paid model ledger or side effects do not match' using errcode='PT409'; end if;

 update public.factory_runs set status='queued',last_error=null,finished_at=null,
    lease_owner=null,lease_expires_at=null,
    metadata=(metadata-'execution_worker_id'-'execution_claimed_at') ||
     jsonb_build_object('v2_readonly_context_recovery_once',v_incident,
       'v2_readonly_context_recovery_at',now(),
       'v2_readonly_context_failed_workflow_id',p_failed_workflow_run_id,
       'v2_readonly_context_factory_sha',p_failed_factory_sha,
       'v2_readonly_context_work_branch_sha',p_observed_work_branch_sha,
       'v2_readonly_context_paid_attempts_preserved',attempt_count)
 where id=v_run.id and status='blocked';
 update public.factory_tasks set status='queued_execution',updated_at=now()
 where id=v_task.id and status='blocked';
 update public.factory_change_set_work_units set status='queued',updated_at=now()
 where id=v_unit.id and status='blocked';
 update public.factory_change_sets set status='building',updated_at=now(),
    lease_owner=null,lease_expires_at=null,
    metadata=(metadata-'blocker')||jsonb_build_object(
      'readonly_context_recovery',jsonb_build_object(
       'run_id',v_run.id,'workflow_id',p_failed_workflow_run_id,
       'factory_sha',p_failed_factory_sha,'observed_work_branch_sha',p_observed_work_branch_sha,
       'at',now(),'paid_attempt_count_preserved',v_run.attempt_count))
 where id=v_set.id and status='blocked';

 insert into public.factory_audit_events(
 project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,v_task.id,v_run.id,'system','readonly-context-recovery',
   'journey.v2.readonly_context_requeued',jsonb_build_object(
      'journey_id',v_journey.id,'work_unit_id',v_unit.id,
      'change_set_id',v_set.id,'generation',v_control.generation,
      'source_commit',v_base,'failed_workflow_id',p_failed_workflow_run_id,
      'incident_code','v2-readonly-source-context-41523358424',
      'one_known_model_call_after_claim',v_model_count,
      'model_cost_usd',v_model_cost,'preserved_attempt_count',v_run.attempt_count,
      'release_authorized',false));
 return jsonb_build_object('requeued',true,'run_id',v_run.id,
      'journey_id',v_journey.id,'work_unit_id',v_unit.id,'change_set_id',v_set.id,
      'source_commit',v_base,'generation',v_control.generation,
      'attempt_count',v_run.attempt_count,'release_authorized',false);
end;
$fn$;
revoke all on function public.factory_recover_v2_readonly_context_once(uuid,bigint,text,text) from public,anon,authenticated;
grant execute on function public.factory_recover_v2_readonly_context_once(uuid,bigint,text,text) to service_role;
commit;
