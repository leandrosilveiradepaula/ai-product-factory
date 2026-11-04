-- Follow-up to 20261104123000: the exhausted CRM209 recovery cannot
-- use the paid Direct dispatch route. This strictly bounded RPC materializes
-- one no-model run only after the separate, human-gated resume RPC succeeds.
-- Never update the previous 3 paid attempts, authorize release, or merge.
begin;

do $check$
begin
 if not exists (
   select 1 from information_schema.columns
    where table_schema='public' and table_name='factory_ci_repair_requests'
      and column_name='deterministic_only'
 ) then
   raise exception 'apply approved CRM209 exhausted recovery migration first'
     using errcode='PT409';
 end if;
end;
$check$;

create or replace function public.factory_claim_crm209_native_ci_once(
  p_worker_id text,
  p_expected_candidate_commit text,
  p_expected_generation bigint,
  p_expected_request_id uuid
) returns jsonb
language plpgsql security invoker set search_path='' as $fn$
declare
 v_project public.factory_projects%rowtype;
 v_rr public.factory_ci_repair_requests%rowtype;
 v_cs public.factory_change_sets%rowtype;
 v_u public.factory_change_set_work_units%rowtype;
 v_t public.factory_tasks%rowtype;
 v_j public.factory_journeys%rowtype;
 v_root public.factory_tasks%rowtype;
 v_source_run public.factory_runs%rowtype;
 v_epoch bigint;
 v_state text;
 v_new_run uuid;
 v_branch text := 'factory/cs-3f09952e/ci-repair-4';
 v_scope jsonb := '["src/services/ContractService.ts","test/contract-access.test.ts"]'::jsonb;
begin
 -- These values are supplied only as a CAS precondition. Caller input
 -- NEVER selects arbitrary project, PR, run, source or write scope.
 if p_expected_request_id is distinct from
       'ca53e605-b132-4937-aed3-f907cea2e221'::uuid
    or p_expected_candidate_commit is distinct from
       'e5eb59c1a56b0c922a5e0d1e956e8c442dff152b'
    or p_expected_generation is distinct from 19
 then
   return jsonb_build_object('status','idle','claimed',false,
                             'paid_model_calls',0,'release_authorized',false);
 end if;
 if p_worker_id is null or btrim(p_worker_id) !~ '^[A-Za-z0-9_-]{8,100}$' then
   raise exception 'invalid native CI worker identity' using errcode='PT400';
 end if;

 -- Lock the project epoch first; pause/restart cannot race the claim.
 select state,generation into v_state,v_epoch
 from public.factory_project_execution_controls
 where project_id='2d30e00a-ff72-4044-b838-011c263ed672'::uuid
 for share;
 if v_state is distinct from 'running' or v_epoch is distinct from 19 then
   raise exception 'native CI project epoch revoked' using errcode='PT409';
 end if;
 select * into v_project from public.factory_projects
 where id='2d30e00a-ff72-4044-b838-011c263ed672'::uuid;
 if not found or v_project.project_key is distinct from 'crm-infodive'
    or v_project.repository is distinct from 'leandrosilveiradepaula/crm-infodive'
    or v_project.project_kind is distinct from 'existing'
    or not v_project.is_active
    or exists(
      select 1 from public.factory_project_scheduling s
      where s.project_id=v_project.id and s.paused
    ) then
   raise exception 'native CI project control revoked' using errcode='PT409';
 end if;

 select * into v_rr from public.factory_ci_repair_requests
 where id=p_expected_request_id for update skip locked;
 if not found or v_rr.status is distinct from 'queued' then
   return jsonb_build_object('status','idle','claimed',false,
                             'paid_model_calls',0,'release_authorized',false);
 end if;
 if v_rr.project_id is distinct from v_project.id
    or v_rr.change_set_id is distinct from '3f09952e-0384-46ee-97aa-a46c89346678'::uuid
    or v_rr.repository is distinct from v_project.repository
    or v_rr.pr_number is distinct from 212
    or v_rr.branch is distinct from 'factory/journey-bb14e150-2c7e-423b-8e5d-e211dab6225c'
    or v_rr.original_candidate_commit is distinct from p_expected_candidate_commit
    or v_rr.execution_generation is distinct from v_epoch
    or v_rr.attempt is distinct from 4 or v_rr.max_attempts is distinct from 3
    or v_rr.failure_class is distinct from 'code'
    or v_rr.deterministic_only is distinct from true
    or v_rr.write_scopes is distinct from v_scope
    or v_rr.blocker_reason is not null
    or v_rr.lease_owner is not null or v_rr.lease_expires_at is not null
    or v_rr.source_run_id is distinct from 'b302e61f-0471-4f92-9e9d-84ac9f5c9694'::uuid
    or v_rr.task_id is null or v_rr.work_unit_id is null
    or v_rr.release_run_id is not null or v_rr.repaired_commit is not null
    or jsonb_array_length(v_rr.failures) is distinct from 1
    or v_rr.failures->0->>'details_url' is distinct from
      'https://github.com/leandrosilveiradepaula/crm-infodive/actions/runs/41764182167/job/126358570861'
 then
   raise exception 'native CI exhaustion ledger changed' using errcode='PT409';
 end if;
 select * into v_cs from public.factory_change_sets
 where id=v_rr.change_set_id for update;
 select * into v_j from public.factory_journeys
 where id='bb14e150-2c7e-423b-8e5d-e211dab6225c'::uuid for share;
 select * into v_u from public.factory_change_set_work_units
 where id=v_rr.work_unit_id for update;
 select * into v_t from public.factory_tasks where id=v_rr.task_id for update;
 select * into v_root from public.factory_tasks where id=v_cs.root_task_id;
 select * into v_source_run from public.factory_runs
 where id=v_rr.source_run_id for share;

 if v_cs.project_id is distinct from v_project.id
    or v_cs.journey_id is distinct from v_j.id
    or v_cs.status is distinct from 'building'
    or v_cs.current_wave is distinct from 5
    or v_cs.attempt_count is distinct from 0
    or v_cs.source_commit is distinct from 'b1935c8f6e61ae246eb8958673b2a9e18c3da81f'
    or v_cs.candidate_commit is distinct from p_expected_candidate_commit
    or v_cs.integration_branch is distinct from v_rr.branch
    or v_cs.release_run_id is not null
    or v_cs.lease_owner is not null or v_cs.lease_expires_at is not null
    or v_cs.metadata->>'ci_repair_request_id' is distinct from v_rr.id::text
    or v_cs.metadata->>'deterministic_only_recovery' is null
    or v_u.change_set_id is distinct from v_cs.id
    or v_u.task_id is distinct from v_t.id
    or v_u.status is distinct from 'pending' or v_u.wave is distinct from 5
    or v_u.plan_task_key is distinct from 'ci-repair-4'
    or v_u.agent_key is distinct from 'development'
    or v_u.run_id is not null or v_u.base_commit is not null
    or v_u.output_commit is not null or v_u.branch_name is not null
    or v_t.status is distinct from 'queued'
    or v_t.parent_task_id is distinct from v_root.id
    or v_t.project_id is distinct from v_project.id
    or v_t.journey_id is distinct from v_j.id
    or v_t.scope_keys is distinct from v_scope
    or v_root.status is distinct from 'queued_execution'
    or v_j.state is distinct from 'executing'
    or v_j.project_id is distinct from v_project.id
    or v_j.execution_generation is distinct from v_epoch
    or v_j.source_commit is distinct from v_cs.source_commit
    or v_j.binding->>'source_commit' is distinct from v_cs.source_commit
    or v_j.binding->>'integration_branch' is distinct from v_cs.integration_branch
    or v_j.binding->>'preview_base_ref' is distinct from 'preview/crm209-delivery-v4'
    or v_source_run.status is distinct from 'repair_pending'
    or v_source_run.journey_id is distinct from v_j.id
    or v_source_run.candidate_commit is distinct from p_expected_candidate_commit
    or v_source_run.metadata->>'ci_repair_request_id' is distinct from v_rr.id::text
    or (select count(*) from public.factory_change_set_work_units u
        where u.change_set_id=v_cs.id and u.wave<5 and u.status='integrated') <> 4
    or exists(select 1 from public.factory_change_set_work_units u
      where u.change_set_id=v_cs.id and u.id<>v_u.id and u.wave>=5)
    or exists(select 1 from public.factory_runs r where r.task_id=v_t.id)
    or exists(select 1 from public.factory_run_agent_assignments a
       join public.factory_runs r on r.id=a.run_id
       where r.journey_id=v_j.id and a.status in ('assigned','claimed','running'))
 then
   raise exception 'native CI recovery execution lineage revoked' using errcode='PT409';
 end if;

 insert into public.factory_runs(
   task_id,journey_id,status,execution_route,source_commit,
   candidate_commit,branch_name,started_at,lease_owner,lease_expires_at,
   attempt_count,metadata
 ) values (
   v_t.id,v_j.id,'implementing',null,v_cs.source_commit,
   v_cs.candidate_commit,v_branch,now(),p_worker_id,
   now()+interval '10 minutes',1,
   jsonb_build_object('source','change-set','change_set_id',v_cs.id,
     'work_unit_id',v_u.id,'execution_generation',v_epoch,
     'project_id',v_project.id,'execution_worker_id',p_worker_id,
     'ci_repair_request_id',v_rr.id,'deterministic_only',true,
     'model_calls_allowed',false,'human_gate_required',false,
     'native_ci_recovery',true,'journey_binding_v2',v_j.binding)
 ) returning id into v_new_run;

 update public.factory_change_set_work_units
 set status='queued',run_id=v_new_run,updated_at=now()
 where id=v_u.id and status='pending' and run_id is null;
 if not found then raise exception 'native CI work unit claim lost' using errcode='PT409'; end if;
 update public.factory_tasks set status='implementing',updated_at=now()
 where id=v_t.id and status='queued';
 if not found then raise exception 'native CI task claim lost' using errcode='PT409'; end if;
 update public.factory_ci_repair_requests
 set status='running',lease_owner=p_worker_id,
   lease_expires_at=now()+interval '10 minutes',updated_at=now()
 where id=v_rr.id and status='queued' and deterministic_only=true;
 if not found then raise exception 'native CI request claim lost' using errcode='PT409'; end if;

 insert into public.factory_audit_events(
   project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
 ) values (
   v_project.id,v_t.id,v_new_run,'system','native-ci-deterministic-worker',
   'journey.v2.native_ci.claimed',
   jsonb_build_object('repair_request_id',v_rr.id,'work_unit_id',v_u.id,
     'candidate_commit',v_rr.original_candidate_commit,
     'execution_generation',v_epoch,'worker_id',p_worker_id,
     'paid_model_calls',0,'release_authorized',false)
 );
 return jsonb_build_object(
   'status','claimed','claimed',true,'run_id',v_new_run,
   'task_id',v_t.id,'project_id',v_project.id,
   'project_key',v_project.project_key,'repository',v_project.repository,
   'change_set_id',v_cs.id,'work_unit_id',v_u.id,
   'branch',v_branch,'wave',v_u.wave,
   'title',v_t.title,'description',v_t.description,
   'candidate_commit',v_cs.candidate_commit,
   'execution_generation',v_epoch,
   'paid_model_calls',0,'model_calls_allowed',false,
   'release_authorized',false
 );
end;
$fn$;

revoke all on function public.factory_claim_crm209_native_ci_once(text,text,bigint,uuid)
 from public,anon,authenticated;
grant execute on function public.factory_claim_crm209_native_ci_once(text,text,bigint,uuid)
 to service_role;

-- Read-only epoch/lease fence that the runtime calls immediately before
-- creating any GitHub branch or commit (the wrapper also checks before
-- ensure_branch and all other writing API operations).
create or replace function public.factory_assert_crm209_native_ci_claim(
 p_run_id uuid,p_worker_id text,p_candidate_commit text,p_generation bigint
) returns jsonb
language plpgsql security invoker set search_path='' as $fn$
declare
 v_r public.factory_runs%rowtype;
 v_u public.factory_change_set_work_units%rowtype;
 v_cs public.factory_change_sets%rowtype;
 v_rr public.factory_ci_repair_requests%rowtype;
 v_j public.factory_journeys%rowtype;
 v_p public.factory_projects%rowtype;
 v_state text;
 v_epoch bigint;
begin
 select c.state,c.generation into v_state,v_epoch
 from public.factory_project_execution_controls c
 where c.project_id='2d30e00a-ff72-4044-b838-011c263ed672'::uuid
 for share;
 if v_state is distinct from 'running' or v_epoch is distinct from 19
    or p_generation is distinct from 19
    or p_worker_id is null or btrim(p_worker_id) !~ '^[A-Za-z0-9_-]{8,100}

    or p_candidate_commit is distinct from 'e5eb59c1a56b0c922a5e0d1e956e8c442dff152b'
 then raise exception 'CRM209 native execution epoch revoked' using errcode='PT409';
 end if;
 select * into v_r from public.factory_runs where id=p_run_id;
 select * into v_u from public.factory_change_set_work_units
 where run_id=p_run_id;
 select * into v_cs from public.factory_change_sets where id=v_u.change_set_id;
 select * into v_rr from public.factory_ci_repair_requests
 where id='ca53e605-b132-4937-aed3-f907cea2e221'::uuid;
 select * into v_j from public.factory_journeys
 where id='bb14e150-2c7e-423b-8e5d-e211dab6225c'::uuid;
 select * into v_p from public.factory_projects where id=v_cs.project_id;
 if v_r.id is null or v_r.status is distinct from 'implementing'
    or v_r.lease_owner is distinct from p_worker_id
    or v_r.lease_expires_at is null or v_r.lease_expires_at<=clock_timestamp()
    or v_r.metadata->>'ci_repair_request_id' is distinct from v_rr.id::text
    or v_r.metadata->>'execution_generation' is distinct from '19'
    or v_r.metadata->>'deterministic_only' is distinct from 'true'
    or v_r.metadata->>'model_calls_allowed' is distinct from 'false'
    or v_r.execution_route is not null
    or v_r.journey_id is distinct from v_j.id
    or v_r.candidate_commit is distinct from p_candidate_commit
    or v_r.branch_name is distinct from 'factory/cs-3f09952e/ci-repair-4'
    or v_u.status not in ('queued','running')
    or v_u.wave is distinct from 5
    or v_u.change_set_id is distinct from v_cs.id
    or v_cs.status is distinct from 'building'
    or v_cs.current_wave is distinct from 5
    or v_cs.candidate_commit is distinct from p_candidate_commit
    or v_rr.status is distinct from 'running'
    or v_rr.work_unit_id is distinct from v_u.id
    or v_rr.lease_owner is distinct from p_worker_id
    or v_rr.lease_expires_at is null or v_rr.lease_expires_at<=clock_timestamp()
    or v_rr.deterministic_only is distinct from true
    or v_rr.write_scopes is distinct from
      '["src/services/ContractService.ts","test/contract-access.test.ts"]'::jsonb
    or v_j.execution_generation is distinct from v_epoch
    or v_j.state is distinct from 'executing'
    or v_p.project_key is distinct from 'crm-infodive'
    or v_p.repository is distinct from 'leandrosilveiradepaula/crm-infodive'
    or not v_p.is_active
    or exists(select 1 from public.factory_project_scheduling sc
       where sc.project_id=v_p.id and sc.paused)
 then raise exception 'CRM209 native CI claim invalidated' using errcode='PT409';
 end if;
 return jsonb_build_object('status','verified','run_id',p_run_id,
    'model_calls_allowed',false,'release_authorized',false);
end;
$fn$;
revoke all on function public.factory_assert_crm209_native_ci_claim(uuid,text,text,bigint)
 from public,anon,authenticated;
grant execute on function public.factory_assert_crm209_native_ci_claim(uuid,text,text,bigint)
 to service_role;
commit;
