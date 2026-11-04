-- One-case, no-model recovery for the *already exhausted* CRM #209 native CI.
-- Candidate only: never apply to the production Control Plane before a separate
-- human migration approval after PR CI and production merge.
-- A failed native CI after this recovery MUST NOT create another paid attempt.
begin;

alter table public.factory_ci_repair_requests
  add column deterministic_only boolean not null default false;

-- Preserve the paid-attempt cap for EVERY normal request. The only exceptional
-- non-exhausted row is the already recorded attempt 4/3 of CRM #212, with one
-- exact previously integrated test file and one immutable candidate SHA.
alter table public.factory_ci_repair_requests
  drop constraint factory_ci_repair_attempt_bound;
alter table public.factory_ci_repair_requests
  add constraint factory_ci_repair_attempt_bound check (
    (status = 'exhausted'
      and attempt = max_attempts + 1 and not deterministic_only)
    or
    (status <> 'exhausted' and (
      (attempt <= max_attempts and not deterministic_only)
      or (
        deterministic_only
        and id = 'ca53e605-b132-4937-aed3-f907cea2e221'::uuid
        and project_id = '2d30e00a-ff72-4044-b838-011c263ed672'::uuid
        and change_set_id = '3f09952e-0384-46ee-97aa-a46c89346678'::uuid
        and attempt = max_attempts + 1 and max_attempts = 3
        and failure_class = 'code'
        and original_candidate_commit = 'e5eb59c1a56b0c922a5e0d1e956e8c442dff152b'
        and write_scopes = '["src/services/ContractService.ts","test/contract-access.test.ts"]'::jsonb
      )
    ))
  );

create or replace function public.factory_resume_crm209_exhausted_native_ci_once(
 p_expected_candidate_commit text,
 p_expected_generation bigint,
 p_expected_request_id uuid
) returns jsonb
language plpgsql security invoker set search_path='' as $fn$
declare
 v_rr public.factory_ci_repair_requests%rowtype;
 v_cs public.factory_change_sets%rowtype;
 v_run public.factory_runs%rowtype;
 v_root public.factory_tasks%rowtype;
 v_journey public.factory_journeys%rowtype;
 v_count integer;
 v_task uuid;
 v_unit uuid;
 v_scopes jsonb := '["src/services/ContractService.ts","test/contract-access.test.ts"]'::jsonb;
 v_issued_at timestamptz := now();
begin
 if p_expected_candidate_commit is distinct from 'e5eb59c1a56b0c922a5e0d1e956e8c442dff152b'
    or p_expected_generation is distinct from 19
    or p_expected_request_id is distinct from 'ca53e605-b132-4937-aed3-f907cea2e221'::uuid
 then
  return jsonb_build_object('status','idle','requeued',false);
 end if;

 select * into v_rr from public.factory_ci_repair_requests
 where id = p_expected_request_id for update;
 if not found or v_rr.status <> 'exhausted' then
  return jsonb_build_object('status','idle','requeued',false);
 end if;
 if v_rr.project_id is distinct from '2d30e00a-ff72-4044-b838-011c263ed672'::uuid
    or v_rr.change_set_id is distinct from '3f09952e-0384-46ee-97aa-a46c89346678'::uuid
    or v_rr.source_run_id is distinct from 'b302e61f-0471-4f92-9e9d-84ac9f5c9694'::uuid
    or v_rr.repository is distinct from 'leandrosilveiradepaula/crm-infodive'
    or v_rr.branch is distinct from 'factory/journey-bb14e150-2c7e-423b-8e5d-e211dab6225c'
    or v_rr.original_candidate_commit is distinct from p_expected_candidate_commit
    or v_rr.execution_generation is distinct from p_expected_generation
    or v_rr.pr_number is distinct from 212
    or v_rr.attempt is distinct from 4
    or v_rr.max_attempts is distinct from 3
    or v_rr.failure_class is distinct from 'code'
    or v_rr.deterministic_only
    or v_rr.work_unit_id is not null or v_rr.task_id is not null
    or v_rr.release_run_id is not null or v_rr.repaired_commit is not null
    or v_rr.write_scopes <> '[]'::jsonb
    or v_rr.lease_owner is not null or v_rr.lease_expires_at is not null
    or v_rr.blocker_reason is distinct from 'ci_repair_attempts_exhausted'
    or jsonb_typeof(v_rr.failures) is distinct from 'array'
    or jsonb_array_length(v_rr.failures) <> 1
    or v_rr.failures->0->>'name' is distinct from 'native-ci/tests'
    or v_rr.failures->0->>'conclusion' is distinct from 'failure'
    or v_rr.failures->0->>'failure_class' is distinct from 'code'
    or v_rr.failures->0->>'summary' is distinct from 'Verified failed GitHub Actions step (run and attempt bound)'
    or v_rr.failures->0->>'details_url' is distinct from
       'https://github.com/leandrosilveiradepaula/crm-infodive/actions/runs/41764182167/job/126358570861'
 then
  raise exception 'immutable CRM209 exhaustion evidence drift' using errcode='PT409';
 end if;

 select * into v_cs from public.factory_change_sets
 where id = v_rr.change_set_id for update;
 select * into v_run from public.factory_runs
 where id = v_rr.source_run_id for update;
 select * into v_root from public.factory_tasks
 where id = v_cs.root_task_id for update;
 select * into v_journey from public.factory_journeys
 where id = 'bb14e150-2c7e-423b-8e5d-e211dab6225c'::uuid for share;

 if v_cs.status is distinct from 'blocked'
    or v_cs.project_id is distinct from v_rr.project_id
    or v_cs.journey_id is distinct from v_journey.id
    or v_cs.current_wave is distinct from 4
    or v_cs.attempt_count is distinct from 1
    or v_cs.candidate_commit is distinct from v_rr.original_candidate_commit
    or v_cs.source_commit is distinct from 'b1935c8f6e61ae246eb8958673b2a9e18c3da81f'
    or v_cs.integration_branch is distinct from v_rr.branch
    or v_cs.release_run_id is distinct from v_run.id
    or v_cs.lease_owner is not null or v_cs.lease_expires_at is not null
    or v_cs.metadata->>'blocker' is distinct from 'ci_repair_attempts_exhausted'
    or v_cs.metadata->>'ci_repair_request_id' is distinct from '50076343-55e7-47dc-80ee-2424e4d69499'
    or v_run.status is distinct from 'failed_gate'
    or v_run.task_id is distinct from v_root.id
    or v_run.journey_id is distinct from v_journey.id
    or v_run.candidate_commit is distinct from v_rr.original_candidate_commit
    or v_run.branch_name is distinct from v_rr.branch
    or v_run.metadata->>'ci_repair_request_id' is distinct from v_rr.id::text
    or v_run.metadata->>'execution_generation' is distinct from '19'
    or v_run.metadata->>'change_set_id' is distinct from v_cs.id::text
    or v_run.attempt_count is distinct from 0
    or v_run.lease_owner is not null or v_run.lease_expires_at is not null
    or v_root.status is distinct from 'failed'
    or v_root.project_id is distinct from v_rr.project_id
    or v_root.journey_id is distinct from v_journey.id
    or v_journey.state is distinct from 'executing'
    or v_journey.project_id is distinct from v_rr.project_id
    or v_journey.execution_generation is distinct from 19
    or v_journey.source_commit is distinct from v_cs.source_commit
    or v_journey.binding->>'source_commit' is distinct from v_cs.source_commit
    or v_journey.binding->>'integration_branch' is distinct from v_cs.integration_branch
    or v_journey.binding->>'preview_base_ref' is distinct from 'preview/crm209-delivery-v4'
    or v_journey.binding->>'binding_version' is distinct from '2'
    or v_journey.binding->>'execution_generation' is distinct from '19'
    or not exists (
      select 1 from public.factory_projects p
      join public.factory_project_execution_controls c on c.project_id=p.id
      where p.id=v_rr.project_id and p.project_kind='existing'
        and p.is_active and p.repository=v_rr.repository
        and c.state='running' and c.generation=p_expected_generation
    )
    or exists (
      select 1 from public.factory_project_scheduling s
      where s.project_id=v_rr.project_id and s.paused
    )
 then
  raise exception 'CRM209 native recovery lifecycle drift' using errcode='PT409';
 end if;

 select count(*) into v_count from public.factory_ci_repair_requests r
 where r.change_set_id=v_cs.id;
 if v_count <> 4 then
  raise exception 'CRM209 native recovery repair ledger changed' using errcode='PT409';
 end if;
 select count(*) into v_count from public.factory_ci_repair_requests r
 where r.change_set_id=v_cs.id and r.id<>v_rr.id
   and r.status='ci_failed' and r.max_attempts=3 and r.attempt in (1,2,3)
   and r.deterministic_only=false;
 if v_count <> 3 or exists (
    select 1 from public.factory_runs r where r.journey_id=v_journey.id
    and r.id<>v_run.id and r.status in ('queued','running','implementing','ci_pending','awaiting_release')
 ) or exists (
    select 1 from public.factory_change_set_work_units w
    where w.change_set_id=v_cs.id and w.wave>4
 ) or exists (
    select 1 from public.factory_run_agent_assignments a
    join public.factory_runs r on r.id=a.run_id
    where r.journey_id=v_journey.id and a.status in ('assigned','claimed','running')
 ) or exists (
    select 1 from public.factory_human_gates h
    join public.factory_runs r on r.id=h.run_id
    where r.journey_id=v_journey.id and h.status in ('pending','open','awaiting')
 ) then
  raise exception 'CRM209 native recovery conflicts with active work' using errcode='PT409';
 end if;

 insert into public.factory_tasks(
   project_id,parent_task_id,external_key,title,description,status,complexity,
   risk,acceptance_criteria,depends_on,scope_keys,journey_id
 ) values (
   v_rr.project_id,v_root.id,'native-ci-exhausted-'||v_rr.id::text,
   'Deterministic native Vitest alias repair after exhausted CI budget',
   'One exact Vitest import replacement in the already integrated test. NEVER call a paid model.',
   'queued','medium','{}'::jsonb,
   jsonb_build_array(jsonb_build_object('failed_job',
      v_rr.failures->0->>'details_url','candidate_commit',v_rr.original_candidate_commit,
      'deterministic_only',true)),
   '[]'::jsonb,v_scopes,v_journey.id
 ) returning id into v_task;

 insert into public.factory_change_set_work_units(
   change_set_id,task_id,plan_task_key,agent_key,wave,status
 ) values (
   v_cs.id,v_task,'ci-repair-4','development',5,'pending'
 ) returning id into v_unit;

 update public.factory_ci_repair_requests
 set deterministic_only=true,status='queued',task_id=v_task,work_unit_id=v_unit,
     write_scopes=v_scopes,blocker_reason=null,updated_at=v_issued_at
 where id=v_rr.id and status='exhausted';
 if not found then raise exception 'CRM209 exhaustion CAS lost' using errcode='PT409'; end if;

 update public.factory_tasks set status='queued_execution',updated_at=v_issued_at
 where id=v_root.id and status='failed';
 if not found then raise exception 'CRM209 root CAS lost' using errcode='PT409'; end if;

 update public.factory_runs
 set status='repair_pending',metadata=metadata || jsonb_build_object(
     'ci_repair_attempt',4,'deterministic_only_recovery',true)
 where id=v_run.id and status='failed_gate';
 if not found then raise exception 'CRM209 source run CAS lost' using errcode='PT409'; end if;

 update public.factory_change_sets set
   status='building',current_wave=5,release_run_id=null,attempt_count=0,
   lease_owner=null,lease_expires_at=null,
   metadata=(metadata - 'blocker') || jsonb_build_object(
     'ci_repair_request_id',v_rr.id,'ci_repair_attempt',4,
     'deterministic_only_recovery',jsonb_build_object(
       'request_id',v_rr.id,'candidate_commit',v_rr.original_candidate_commit,
       'failed_job',v_rr.failures->0->>'details_url','at',v_issued_at)),
   updated_at=v_issued_at
 where id=v_cs.id and status='blocked';
 if not found then raise exception 'CRM209 change set CAS lost' using errcode='PT409'; end if;

 insert into public.factory_audit_events(
   project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
 ) values (
   v_rr.project_id,v_task,v_run.id,'system','native-ci-exhausted-recovery',
   'journey.v2.native_ci_deterministic_exception',
   jsonb_build_object('repair_request_id',v_rr.id,'attempt',4,'max_attempts',3,
     'previous_status','exhausted','work_unit_id',v_unit,
     'candidate_commit',v_rr.original_candidate_commit,
     'failed_job',v_rr.failures->0->>'details_url',
     'write_scopes',v_scopes,'model_calls_allowed',false,
     'paid_model_calls',0,'release_authorized',false,'new_start',false)
 );
 return jsonb_build_object(
   'status','requeued','requeued',true,'request_id',v_rr.id,
   'work_unit_id',v_unit,'candidate_commit',v_rr.original_candidate_commit,
   'model_calls_allowed',false,'paid_model_calls',0,'release_authorized',false
 );
end;
$fn$;

revoke all on function public.factory_resume_crm209_exhausted_native_ci_once(text,bigint,uuid)
 from public,anon,authenticated;
grant execute on function public.factory_resume_crm209_exhausted_native_ci_once(text,bigint,uuid)
 to service_role;
commit;
