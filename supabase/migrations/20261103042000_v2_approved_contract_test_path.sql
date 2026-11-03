-- Exact operator-approved test-path substitution for the existing CRM #209 V2 run.
-- No broad scope, product data, role, RLS, release, model call, or attempt reset.
begin;
create or replace function public.factory_approve_v2_contract_test_path_once(
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
 v_call_count integer;
 v_call_cost numeric;
 v_source text := 'b1935c8f6e61ae246eb8958673b2a9e18c3da81f';
 v_old_test text := 'src/services/ContractService.test.ts';
 v_new_test text := 'test/contract-access.test.ts';
 v_previous_scopes jsonb := '["src/services/ContractService.ts","contract-query-call-sites","src/services/ContractService.test.ts","src/app/(dashboard)/contracts/actions.ts"]'::jsonb;
 v_expected_context jsonb := '["src/services/ContractService.ts","src/app/(dashboard)/contracts/actions.ts"]'::jsonb;
 v_old_criterion text := 'src/services/ContractService.test.ts contém testes determinísticos e isolados de serviços remotos para leitura autorizada, isolamento entre organizações, isolamento entre proprietários quando aplicável ao modelo verificado, contratos sem deal quando aplicável, ordenação com empates, paginação global sem duplicatas, cenário aplicável acima de 1.000 itens ou vínculos e erro de consulta sem sucesso parcial.';
 v_new_scopes jsonb;
 v_criteria jsonb;
 v_plan jsonb;
 v_old_md5 text;
 v_new_md5 text;
 v_receipt text := 'v2-contract-test-path-41570692508-20261103-v1';
 v_authorization text := 'operator-explicit-approval-2026-11-03T03:16:10Z';
begin
 if p_run_id is distinct from 'b11daad8-dfc2-4a42-ba4a-a98e0d529238'::uuid
 or p_failed_workflow_run_id is distinct from 41570692508
 or p_failed_factory_sha is distinct from '2ae9f7d40df57fcd4700bff690ed5a9ae75e445f'
 or p_observed_work_branch_sha is distinct from v_source
 then raise exception 'unknown exact contract test-path approval' using errcode='PT403';end if;
 select p.* into v_project from public.factory_projects p
 join public.factory_tasks t on t.project_id=p.id
 join public.factory_runs r on r.task_id=t.id
 where r.id=p_run_id and p.is_active=true
 and p.repository='leandrosilveiradepaula/crm-infodive'
 for update of p;
 if v_project.id is null then raise exception 'active CRM project not found' using errcode='PT409';end if;
 select * into v_control from public.factory_project_execution_controls
 where project_id=v_project.id for share;
 select * into v_journey from public.factory_journeys
 where id='bb14e150-2c7e-423b-8e5d-e211dab6225c'::uuid
 and project_id=v_project.id for update;
 select * into v_set from public.factory_change_sets
 where id='3f09952e-0384-46ee-97aa-a46c89346678'::uuid
 and project_id=v_project.id and journey_id=v_journey.id for update;
 select * into v_unit from public.factory_change_set_work_units
 where id='179b34b0-e8f2-4055-bd28-7c7a89de3fc0'::uuid
 and change_set_id=v_set.id for update;
 select * into v_team from public.factory_execution_team_plans
 where id=v_set.team_plan_id and project_id=v_project.id for update;
 select * into v_run from public.factory_runs
 where id=p_run_id and task_id=v_unit.task_id and journey_id=v_journey.id for update;
 select * into v_task from public.factory_tasks
 where id=v_run.task_id and project_id=v_project.id for update;

 if coalesce(v_run.metadata->>'v2_contract_test_path_approved_once','')=v_receipt then
  return jsonb_build_object('requeued',false,'run_id',v_run.id,
   'status',v_run.status,'attempt_count',v_run.attempt_count,
   'approved_test_path',v_new_test,'release_authorized',false);
 end if;

 if v_journey.id is null or v_set.id is null or v_unit.id is null
 or v_team.id is null or v_run.id is null or v_task.id is null
 or v_control.state is distinct from 'running' or v_control.generation is distinct from 19
 or v_journey.state is distinct from 'executing'
 or v_journey.execution_generation is distinct from v_control.generation
 or v_journey.source_commit is distinct from v_source
 or v_journey.binding->>'source_commit' is distinct from v_source
 or v_journey.binding->>'execution_generation' is distinct from '19'
 or v_journey.binding->>'project_id' is distinct from v_project.id::text
 or v_journey.candidate_commit is not null
 or v_journey.work_unit_output_commit is not null
 or v_journey.preview_merge_sha is not null
 or v_journey.production_release_sha is not null
 or v_team.status is distinct from 'ready' or v_team.version is distinct from 19
 or jsonb_array_length(coalesce(v_team.plan->'task_assignments','[]'::jsonb))<>1
 or v_team.plan#>>'{task_assignments,0,task_key}' is distinct from 'issue209-contracts-isolated-read'
 or v_team.plan#>'{task_assignments,0,scope_keys}' is distinct from v_previous_scopes
 or v_team.plan#>'{task_assignments,0,context_paths}' is distinct from v_expected_context
 or v_team.plan#>>'{operator_scope_amendment,added_exact_write_path}'
      is distinct from 'src/app/(dashboard)/contracts/actions.ts'
 or v_team.plan#>>'{operator_scope_amendment,approval_reference}'
      is distinct from 'operator-explicit-approval-2026-11-03T01:18:12Z'
 or v_task.status is distinct from 'blocked'
 or v_task.journey_id is distinct from v_journey.id
 or v_task.scope_keys is distinct from v_previous_scopes
 or jsonb_typeof(v_task.acceptance_criteria) is distinct from 'array'
 or jsonb_array_length(v_task.acceptance_criteria) is distinct from 14
 or v_task.acceptance_criteria->>12 is distinct from v_old_criterion
 or v_run.status is distinct from 'blocked' or v_run.attempt_count is distinct from 6
 or v_run.execution_route is distinct from 'direct'
 or v_run.source_commit is distinct from v_source
 or v_run.lease_owner is not null or v_run.lease_expires_at is not null
 or v_run.metadata->'journey_binding_v2' is distinct from v_journey.binding
 or v_run.metadata->>'execution_generation' is distinct from '19'
 or v_run.metadata->>'decision_gate_resolution' is distinct from 'approved'
 or v_run.metadata->>'v2_single_caller_scope_approved_once'
      is distinct from 'v2-owner-approved-single-actions-scope-41558099308-v1'
 or v_run.last_error is distinct from
      'Bloqueado: os critérios obrigatórios exigem `src/services/ContractService.test.ts`, mas o `CURRENT_TASK.md` autoriza testes somente em `test/*contract*.test.ts` ou `tests/*contract*.test.ts`, e esses caminhos não estão em `repository.write_scopes`. Não é possível implementar e validar integralmente a tarefa sem uma decisão humana que alinhe os escopos.'
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
 or v_unit.output_commit is not null
 or v_unit.changed_files is distinct from '[]'::jsonb
 or v_unit.branch_name is distinct from 'factory/cs-3f09952e/issue209-contracts-isolated-read'
 then raise exception 'contract test path, scope, or run evidence changed' using errcode='PT409';end if;

 select * into v_gate from public.factory_human_gates
 where id='edbee01d-1d23-4e6b-a7a0-0b5a562183d4'::uuid
 and run_id=v_run.id and status='approved' and gate_type='material_requirement_change'
 for share;
 if v_gate.id is null or v_gate.resolved_at is null
 or v_gate.resolution->>'resolution' is distinct from 'approved'
 then raise exception 'prior material decision not approved' using errcode='PT409';end if;

 select created_at,payload->>'worker_id' into v_claim,v_worker
 from public.factory_audit_events where run_id=v_run.id
 and event_type='execution.direct.claimed' order by created_at desc limit 1;
 if v_claim is distinct from '2026-11-03T03:12:48.529201+00:00'::timestamptz
 or v_worker is distinct from 'gha-direct-41570692508-0'
 then raise exception 'direct worker identity drift' using errcode='PT409';end if;
 select event_type into v_last_event from public.factory_audit_events
 where run_id=v_run.id order by created_at desc,id desc limit 1;
 if v_last_event is distinct from 'change_set.work_unit.blocked'
 or not exists(select 1 from public.factory_audit_events where run_id=v_run.id
    and event_type='change_set.work_unit.blocked'
    and created_at='2026-11-03T03:13:32.00434+00:00'::timestamptz)
 or exists(select 1 from public.factory_run_agent_assignments a
    where a.run_id=v_run.id and a.status in ('assigned','claimed'))
 or exists(select 1 from public.factory_agent_scope_locks l
    where l.run_id=v_run.id and l.released_at is null and l.lease_expires_at>now())
 or exists(select 1 from public.factory_change_set_work_units w
    where w.change_set_id=v_set.id and w.id<>v_unit.id
    and (w.output_commit is not null or w.status in ('running','completed','integrated')))
 then raise exception 'concurrent effects or changed last incident' using errcode='PT409';end if;

 select count(*),sum(estimated_cost) into v_call_count,v_call_cost
 from public.factory_tool_usage where run_id=v_run.id and created_at>=v_claim
 and tool_family='openai' and operation='model_call';
 if v_call_count is distinct from 1 or v_call_cost is distinct from 0.035042
 or exists(select 1 from public.factory_tool_usage where run_id=v_run.id
   and created_at>=v_claim and
   (tool_family<>'openai' or operation<>'model_call' or estimated_cost is null))
 then raise exception 'paid ledger drift' using errcode='PT409';end if;

 v_new_scopes:=jsonb_build_array(
 'src/services/ContractService.ts','contract-query-call-sites',v_new_test,
 'src/app/(dashboard)/contracts/actions.ts');
 v_criteria:=jsonb_set(v_task.acceptance_criteria,'{12}',
 to_jsonb(replace(v_old_criterion,v_old_test,v_new_test)),false);
 v_old_md5:=md5(v_team.plan::text);
 v_plan:=jsonb_set(v_team.plan,'{task_assignments,0,scope_keys}',v_new_scopes,false);
 v_plan:=v_plan||jsonb_build_object('operator_test_path_amendment',jsonb_build_object(
   'run_id',v_run.id,'work_unit_id',v_unit.id,'generation',19,
   'source_commit',v_source,'old_test_path',v_old_test,'new_test_path',v_new_test,
   'approval_reference',v_authorization,'old_plan_md5',v_old_md5,
   'failed_workflow_run_id',p_failed_workflow_run_id,'applied_at',now()));
 v_new_md5:=md5(v_plan::text);
 update public.factory_execution_team_plans set plan=v_plan
 where id=v_team.id and plan=v_team.plan and status='ready';
 if not found then raise exception 'team plan CAS lost' using errcode='PT409';end if;
 update public.factory_tasks set scope_keys=v_new_scopes,
 acceptance_criteria=v_criteria,updated_at=now()
 where id=v_task.id and status='blocked'
 and scope_keys=v_previous_scopes and acceptance_criteria=v_task.acceptance_criteria;
 if not found then raise exception 'task CAS lost' using errcode='PT409';end if;
 update public.factory_runs set status='queued',last_error=null,finished_at=null,
 lease_owner=null,lease_expires_at=null,
 metadata=(metadata-'execution_worker_id'-'execution_claimed_at')||
   jsonb_build_object('v2_contract_test_path_approved_once',v_receipt,
     'v2_contract_test_path_approval_reference',v_authorization,
     'v2_contract_test_path_plan_before_md5',v_old_md5,
     'v2_contract_test_path_plan_after_md5',v_new_md5,
     'v2_contract_test_path_attempts_preserved',attempt_count,
     'v2_contract_test_path_approved_at',now())
 where id=v_run.id and status='blocked';
 if not found then raise exception 'run CAS lost' using errcode='PT409';end if;
 update public.factory_tasks set status='queued_execution',updated_at=now()
 where id=v_task.id and status='blocked';
 update public.factory_change_set_work_units set status='queued',updated_at=now()
 where id=v_unit.id and status='blocked';
 update public.factory_change_sets set status='building',updated_at=now(),
 lease_owner=null,lease_expires_at=null,
 metadata=(metadata-'blocker')||jsonb_build_object('approved_exact_test_path',
 jsonb_build_object('old',v_old_test,'new',v_new_test,'at',now(),
    'run_id',v_run.id,'preserved_attempt_count',v_run.attempt_count,
    'approval_reference',v_authorization,
    'plan_before_md5',v_old_md5,'plan_after_md5',v_new_md5))
 where id=v_set.id and status='blocked';
 insert into public.factory_audit_events(
 project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,v_task.id,v_run.id,'system','operator-test-path-approval',
 'journey.v2.exact_test_path_requeued',
 jsonb_build_object('journey_id',v_journey.id,'change_set_id',v_set.id,
 'work_unit_id',v_unit.id,'generation',19,'source_commit',v_source,
 'old_test_path',v_old_test,'new_test_path',v_new_test,
 'before_scopes',v_previous_scopes,'after_scopes',v_new_scopes,
 'approval_reference',v_authorization,'preserved_attempt_count',v_run.attempt_count,
 'paid_calls_since_last_claim',v_call_count,'last_paid_cost_usd',v_call_cost,
 'plan_before_md5',v_old_md5,'plan_after_md5',v_new_md5,
 'crm_data_modified',false,'release_authorized',false));
 return jsonb_build_object('requeued',true,'run_id',v_run.id,
 'journey_id',v_journey.id,'work_unit_id',v_unit.id,
 'old_test_path',v_old_test,'new_test_path',v_new_test,
 'attempt_count',v_run.attempt_count,'generation',v_control.generation,
 'source_commit',v_source,'plan_before_md5',v_old_md5,
 'plan_after_md5',v_new_md5,'release_authorized',false);
end;
$fn$;
revoke all on function public.factory_approve_v2_contract_test_path_once(uuid,bigint,text,text) from public,anon,authenticated;
grant execute on function public.factory_approve_v2_contract_test_path_once(uuid,bigint,text,text) to service_role;
commit;
