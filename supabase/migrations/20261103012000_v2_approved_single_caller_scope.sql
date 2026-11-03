-- One audited, exact-SHA scope amendment for the existing CRM V2 journey.
-- It never adds broad paths, changes RBAC/RLS, makes model calls, or merges code.
-- Operator approved precisely src/app/(dashboard)/contracts/actions.ts.
begin;
create or replace function public.factory_approve_v2_single_caller_scope_once(
 p_run_id uuid,p_failed_workflow_run_id bigint,p_failed_factory_sha text,
 p_observed_work_branch_sha text
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare
 v_project public.factory_projects%rowtype;
 v_control public.factory_project_execution_controls%rowtype;
 v_journey public.factory_journeys%rowtype;
 v_set public.factory_change_sets%rowtype;
 v_unit public.factory_change_set_work_units%rowtype;
 v_team public.factory_execution_team_plans%rowtype;
 v_task public.factory_tasks%rowtype;
 v_run public.factory_runs%rowtype;
 v_gate public.factory_human_gates%rowtype;
 v_claim timestamptz;
 v_worker text;
 v_last_event text;
 v_model_count integer;
 v_model_cost numeric;
 v_orig_scopes jsonb := '["src/services/ContractService.ts","contract-query-call-sites","src/services/ContractService.test.ts"]'::jsonb;
 v_original_context jsonb := '["src/services/ContractService.ts"]'::jsonb;
 v_added text := 'src/app/(dashboard)/contracts/actions.ts';
 v_source text := 'b1935c8f6e61ae246eb8958673b2a9e18c3da81f';
 v_receipt text := 'v2-owner-approved-single-actions-scope-41558099308-v1';
 v_approval text := 'operator-explicit-approval-2026-11-03T01:18:12Z';
 v_modified_plan jsonb;
 v_before_md5 text;
 v_after_md5 text;
begin
 if p_run_id is distinct from 'b11daad8-dfc2-4a42-ba4a-a98e0d529238'::uuid
 or p_failed_workflow_run_id is distinct from 41558099308
 or p_failed_factory_sha is distinct from '63123e415aadc9ff25354b9bd8aeccfe4284db63'
 or p_observed_work_branch_sha is distinct from v_source
 then raise exception 'unrecognized exact work-unit scope amendment' using errcode='PT403';end if;

 select p.* into v_project from public.factory_projects p
 join public.factory_tasks t on t.project_id=p.id
 join public.factory_runs r on r.task_id=t.id
 where r.id=p_run_id and p.is_active=true
 and p.repository='leandrosilveiradepaula/crm-infodive'
 for update of p;
 if v_project.id is null then raise exception 'inactive or missing project' using errcode='PT409';end if;
 select * into v_control from public.factory_project_execution_controls
 where project_id=v_project.id for share;
 select * into v_journey from public.factory_journeys
 where id='bb14e150-2c7e-423b-8e5d-e211dab6225c'::uuid
 and project_id=v_project.id for update;
 select * into v_set from public.factory_change_sets
 where id='3f09952e-0384-46ee-97aa-a46c89346678'::uuid
 and project_id=v_project.id and journey_id=v_journey.id for update;
 select * into v_unit from public.factory_change_set_work_units
 where id='179b34b0-e8f2-4055-bd28-7c7a89de3fc0'::uuid and change_set_id=v_set.id
 for update;
 select * into v_team from public.factory_execution_team_plans
 where id=v_set.team_plan_id and project_id=v_project.id for update;
 select * into v_run from public.factory_runs
 where id=p_run_id and task_id=v_unit.task_id and journey_id=v_journey.id
 for update;
 select * into v_task from public.factory_tasks
 where id=v_run.task_id and project_id=v_project.id for update;

 -- The replay marker is written in the same transaction as the scope change.
 if coalesce(v_run.metadata->>'v2_single_caller_scope_approved_once','')=v_receipt then
  return jsonb_build_object('requeued',false,'run_id',v_run.id,
   'status',v_run.status,'attempt_count',v_run.attempt_count,
   'approved_write_path',v_added,'release_authorized',false);
 end if;

 if v_journey.id is null or v_set.id is null or v_unit.id is null
    or v_team.id is null or v_run.id is null or v_task.id is null
    or v_control.state is distinct from 'running' or v_control.generation is distinct from 19
    or v_journey.state is distinct from 'executing'
    or v_journey.execution_generation is distinct from v_control.generation
    or v_journey.source_commit is distinct from v_source
    or v_journey.binding->>'source_commit' is distinct from v_source
    or v_journey.binding->>'execution_generation' is distinct from v_control.generation::text
    or v_journey.binding->>'project_id' is distinct from v_project.id::text
    or v_journey.candidate_commit is not null
    or v_journey.work_unit_output_commit is not null
    or v_journey.preview_merge_sha is not null
    or v_journey.production_release_sha is not null
    or v_team.status is distinct from 'ready' or v_team.version is distinct from 19
    or jsonb_array_length(coalesce(v_team.plan->'task_assignments','[]'::jsonb))<>1
    or v_team.plan#>>'{task_assignments,0,task_key}' is distinct from 'issue209-contracts-isolated-read'
    or v_team.plan#>'{task_assignments,0,scope_keys}' is distinct from v_orig_scopes
    or v_team.plan#>'{task_assignments,0,context_paths}' is distinct from v_original_context
    or v_task.scope_keys is distinct from v_orig_scopes
    or v_task.status is distinct from 'blocked'
    or v_task.journey_id is distinct from v_journey.id
    or v_run.status is distinct from 'blocked' or v_run.attempt_count is distinct from 5
    or v_run.execution_route is distinct from 'direct'
    or v_run.source_commit is distinct from v_source
    or v_run.lease_owner is not null or v_run.lease_expires_at is not null
    or v_run.metadata->'journey_binding_v2' is distinct from v_journey.binding
    or v_run.metadata->>'execution_generation' is distinct from '19'
    or v_run.metadata->>'decision_gate_resolution' is distinct from 'approved'
    or v_run.metadata->>'preprovider_auth_recovery_once' is distinct from 'factory-v2-preprovider-github-broker-403-v1'
    or v_run.metadata->>'v2_readonly_context_recovery_once' is distinct from 'v2-readonly-source-context-41523358424-v1'
    or v_run.last_error is distinct from 'Bloqueado: a implementação autorizada exige alterar o chamador server-side `src/app/(dashboard)/contracts/actions.ts` para fornecer contexto de identidade/autorização e propagar falhas, mas esse arquivo está fora de `repository.write_scopes`. Não posso ampliar o escopo de escrita nem implementar um bypass dentro de `ContractService`.'
    or v_set.status is distinct from 'blocked'
    or v_set.source_commit is distinct from v_source
    or v_set.candidate_commit is distinct from v_source
    or v_set.release_run_id is not null
    or v_set.lease_owner is not null or v_set.lease_expires_at is not null
    or v_set.metadata#>>'{blocker,type}' is distinct from 'repository_governance'
    or v_set.metadata#>>'{blocker,run_id}' is distinct from v_run.id::text
    or v_set.metadata#>>'{blocker,work_unit_id}' is distinct from v_unit.id::text
    or v_unit.status is distinct from 'blocked'
    or v_unit.base_commit is distinct from v_source
    or v_unit.output_commit is not null or v_unit.changed_files is distinct from '[]'::jsonb
    or v_unit.branch_name is distinct from 'factory/cs-3f09952e/issue209-contracts-isolated-read'
 then raise exception 'scope, approval, source or state drift' using errcode='PT409';end if;

 select * into v_gate from public.factory_human_gates
 where id='edbee01d-1d23-4e6b-a7a0-0b5a562183d4'::uuid
 and run_id=v_run.id and gate_type='material_requirement_change'
 and status='approved' for share;
 if v_gate.id is null or v_gate.resolved_at is null
 or v_gate.resolution->>'resolution' is distinct from 'approved'
 then raise exception 'existing material decision not approved' using errcode='PT409';end if;

 select created_at,payload->>'worker_id' into v_claim,v_worker
 from public.factory_audit_events where run_id=v_run.id
 and event_type='execution.direct.claimed' order by created_at desc limit 1;
 if v_claim is distinct from '2026-11-03T01:13:05.204273+00:00'::timestamptz
 or v_worker is distinct from 'gha-direct-41558099308-0'
 then raise exception 'last Direct claim is not incident worker' using errcode='PT409';end if;
 select event_type into v_last_event from public.factory_audit_events
 where run_id=v_run.id order by created_at desc,id desc limit 1;
 if v_last_event is distinct from 'change_set.work_unit.blocked'
 or not exists(select 1 from public.factory_audit_events
    where run_id=v_run.id and event_type='change_set.work_unit.blocked'
    and created_at='2026-11-03T01:13:42.698898+00:00'::timestamptz)
 or exists(select 1 from public.factory_run_agent_assignments a
    where a.run_id=v_run.id and a.status in ('assigned','claimed'))
 or exists(select 1 from public.factory_agent_scope_locks l
    where l.run_id=v_run.id and l.released_at is null and l.lease_expires_at>now())
 or exists(select 1 from public.factory_change_set_work_units w
    where w.change_set_id=v_set.id and w.id<>v_unit.id
    and (w.output_commit is not null or w.status in ('running','completed','integrated')))
 then raise exception 'concurrent side effects or changed claim' using errcode='PT409';end if;

 select count(*),sum(estimated_cost) into v_model_count,v_model_cost
 from public.factory_tool_usage where run_id=v_run.id and created_at>=v_claim
 and tool_family='openai' and operation='model_call';
 if v_model_count is distinct from 1 or v_model_cost is distinct from 0.034782
 or exists(select 1 from public.factory_tool_usage where run_id=v_run.id
    and created_at>=v_claim and
    (tool_family<>'openai' or operation<>'model_call' or estimated_cost is null))
 then raise exception 'paid ledger changed' using errcode='PT409';end if;

 v_before_md5:=md5(v_team.plan::text);
 v_modified_plan:=jsonb_set(v_team.plan,'{task_assignments,0,scope_keys}',
   v_orig_scopes||jsonb_build_array(v_added),false);
 v_modified_plan:=jsonb_set(v_modified_plan,'{task_assignments,0,context_paths}',
   v_original_context||jsonb_build_array(v_added),false);
 v_modified_plan:=v_modified_plan||jsonb_build_object(
  'operator_scope_amendment',jsonb_build_object(
     'run_id',v_run.id,'work_unit_id',v_unit.id,'generation',19,
     'source_commit',v_source,'added_exact_write_path',v_added,
     'approval_reference',v_approval,'prior_plan_md5',v_before_md5,
     'failed_workflow_run_id',p_failed_workflow_run_id,'at',now()));
 v_after_md5:=md5(v_modified_plan::text);

 update public.factory_execution_team_plans set plan=v_modified_plan
 where id=v_team.id and plan=v_team.plan and status='ready';
 if not found then raise exception 'plan CAS lost' using errcode='PT409';end if;
 update public.factory_tasks set scope_keys=v_orig_scopes||jsonb_build_array(v_added),
 updated_at=now() where id=v_task.id and scope_keys=v_orig_scopes and status='blocked';
 if not found then raise exception 'task scope CAS lost' using errcode='PT409';end if;
 update public.factory_runs set status='queued',last_error=null,finished_at=null,
    lease_owner=null,lease_expires_at=null,
    metadata=(metadata-'execution_worker_id'-'execution_claimed_at')||
      jsonb_build_object('v2_single_caller_scope_approved_once',v_receipt,
        'v2_single_caller_scope_approved_at',now(),
        'v2_single_caller_scope_plan_before_md5',v_before_md5,
        'v2_single_caller_scope_plan_after_md5',v_after_md5,
        'v2_single_caller_scope_approval_reference',v_approval,
        'v2_single_caller_scope_attempts_preserved',attempt_count)
 where id=v_run.id and status='blocked';
 if not found then raise exception 'run CAS lost' using errcode='PT409';end if;
 update public.factory_tasks set status='queued_execution',updated_at=now()
 where id=v_task.id and status='blocked';
 update public.factory_change_set_work_units set status='queued',updated_at=now()
 where id=v_unit.id and status='blocked';
 update public.factory_change_sets set status='building',lease_owner=null,
 lease_expires_at=null,updated_at=now(),
 metadata=(metadata-'blocker')||jsonb_build_object(
  'approved_exact_scope',jsonb_build_object(
     'work_unit_id',v_unit.id,'path',v_added,'approved_at',now(),
     'plan_before_md5',v_before_md5,'plan_after_md5',v_after_md5,
     'attempt_count_preserved',v_run.attempt_count,'approval_reference',v_approval))
 where id=v_set.id and status='blocked';

 insert into public.factory_audit_events(
  project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,v_task.id,v_run.id,'system','operator-scope-approval',
  'journey.v2.explicit_single_caller_scope_requeued',
  jsonb_build_object('journey_id',v_journey.id,'change_set_id',v_set.id,
    'work_unit_id',v_unit.id,'team_plan_id',v_team.id,'generation',19,
    'source_commit',v_source,'approved_exact_write_path',v_added,
    'prior_plan_md5',v_before_md5,'new_plan_md5',v_after_md5,
    'scope_before',v_orig_scopes,
    'scope_after',v_orig_scopes||jsonb_build_array(v_added),
    'approval_reference',v_approval,'failed_workflow_run_id',p_failed_workflow_run_id,
    'paid_model_calls_preserved',v_model_count,'latest_paid_cost_usd',v_model_cost,
    'attempt_count_preserved',v_run.attempt_count,
    'data_mutated',false,'release_authorized',false));
 return jsonb_build_object('requeued',true,'run_id',v_run.id,
 'journey_id',v_journey.id,'work_unit_id',v_unit.id,
 'approved_exact_write_path',v_added,'attempt_count',v_run.attempt_count,
 'generation',v_control.generation,'source_commit',v_source,
 'plan_before_md5',v_before_md5,'plan_after_md5',v_after_md5,
 'release_authorized',false);
end;
$fn$;
revoke all on function public.factory_approve_v2_single_caller_scope_once(uuid,bigint,text,text) from public,anon,authenticated;
grant execute on function public.factory_approve_v2_single_caller_scope_once(uuid,bigint,text,text) to service_role;
commit;
