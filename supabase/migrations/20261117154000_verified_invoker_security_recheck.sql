-- B4: Re-run a genuine scoped-RLS Security review after the deterministic
-- Guardian's strictly bounded SECURITY INVOKER classification was corrected.
-- Historical failed evaluation and repair findings remain durable.
-- Never converts a failed review into PASS; only queues a new real scan.
create or replace function public.factory_requeue_verified_invoker_security_once_v1(
  p_run_id uuid,p_pr_number integer,p_candidate_commit text,
  p_security_job_id uuid,p_verified_proof jsonb
) returns jsonb
language plpgsql security invoker set search_path='' as $body$
declare
 v_run public.factory_runs%rowtype;
 v_task public.factory_tasks%rowtype;
 v_cs public.factory_change_sets%rowtype;
 v_project public.factory_projects%rowtype;
 v_job public.factory_specialist_lane_jobs%rowtype;
 v_repair public.factory_repair_jobs%rowtype;
 v_unit public.factory_change_set_work_units%rowtype;
 v_child public.factory_runs%rowtype;
 v_generation bigint;
 v_original_findings jsonb;
begin
 if p_run_id is null or p_security_job_id is null
    or p_pr_number is null or p_pr_number < 1
    or p_candidate_commit is null or p_candidate_commit !~ '^[0-9a-f]{40}$'
    or jsonb_typeof(p_verified_proof) is distinct from 'object'
    or length(p_verified_proof::text)>8192
    or p_verified_proof->>'repository' is null
    or p_verified_proof->>'candidate_commit' is distinct from p_candidate_commit
    or p_verified_proof->>'pr_number' is distinct from p_pr_number::text
    or p_verified_proof->>'source' is distinct from 'github_native_ci_full_pr_scanner'
    or p_verified_proof->>'guardian' is distinct from 'architecture_guardian_v1'
    or p_verified_proof->>'blockers' is distinct from '0'
    or coalesce((p_verified_proof->>'files_reviewed')~'^[1-9][0-9]*$',false) is false
    or (p_verified_proof->>'files_reviewed')::integer not between 1 and 3000
    or coalesce((p_verified_proof->>'diff_sha256')~'^[a-f0-9]{64}$',false) is false
    or coalesce((p_verified_proof->>'factory_main_sha')~'^[a-f0-9]{40}$',false) is false
    or p_verified_proof->>'native_ci_state' is distinct from 'success'
    or coalesce((p_verified_proof->>'native_checks')~'^[1-9][0-9]*$',false) is false
    or (p_verified_proof->>'native_checks')::integer<2
    or p_verified_proof->>'factory_main_ci' is distinct from 'success'
    or p_verified_proof->>'release_authorized' is distinct from 'false'
    or p_verified_proof->>'model_called' is distinct from 'false'
 then raise exception 'independent exact-SHA invoker recheck proof missing' using errcode='PT400';end if;

 -- Execution control is locked before job mutations, preserving Pause/generation.
 select c.generation into v_generation
 from public.factory_project_execution_controls c
 join public.factory_projects p on p.id=c.project_id
 join public.factory_runs r on r.task_id in (
   select t.id from public.factory_tasks t where t.project_id=p.id)
 where r.id=p_run_id and c.state='running' and c.generation>0
   and p.is_active=true
 for share of c,p;
 if not found then raise exception 'active project epoch missing' using errcode='PT409';end if;

 select * into v_run from public.factory_runs where id=p_run_id for update;
 if not found or v_run.status is distinct from 'specialist_review_failed'
    or v_run.candidate_commit is distinct from p_candidate_commit
    or v_run.metadata->>'execution_generation' is distinct from v_generation::text
    or v_run.metadata->>'source' is distinct from 'change-set'
    or v_run.lease_owner is not null or v_run.lease_expires_at is not null
    or v_run.finished_at is not null
 then raise exception 'original same-SHA review not recoverable' using errcode='PT409';end if;

 select * into v_task from public.factory_tasks where id=v_run.task_id for share;
 select * into v_cs from public.factory_change_sets
 where id=(v_run.metadata->>'change_set_id')::uuid for update;
 select * into v_project from public.factory_projects
 where id=v_task.project_id for share;
 if v_task.status is distinct from 'integrated'
    or v_project.id is distinct from v_cs.project_id
    or v_project.project_kind is distinct from 'greenfield'
    or v_project.repository is distinct from p_verified_proof->>'repository'
    or v_cs.root_task_id is distinct from v_task.id
    or v_cs.status is distinct from 'blocked'
    or v_cs.release_run_id is not null
    or v_cs.candidate_commit is distinct from p_candidate_commit
    or v_cs.integration_branch is distinct from v_run.branch_name
    or v_cs.lease_owner is not null or v_cs.lease_expires_at is not null
    or v_cs.metadata#>>'{integration_release_request,pr_number}' is distinct from p_pr_number::text
    or v_cs.metadata#>>'{integration_release_request,candidate_commit}' is distinct from p_candidate_commit
 then raise exception 'change set or external release lineage changed' using errcode='PT409';end if;

 select * into v_job from public.factory_specialist_lane_jobs
 where id=p_security_job_id for update;
 if not found or v_job.run_id is distinct from p_run_id
    or v_job.project_id is distinct from v_project.id
    or v_job.role is distinct from 'security'
    or v_job.status is distinct from 'failed'
    or v_job.candidate_commit is distinct from p_candidate_commit
    or v_job.evidence->>'_factory_epoch' is distinct from v_generation::text
    or v_job.lease_expires_at is not null
    or jsonb_typeof(v_job.findings) is distinct from 'array'
    or jsonb_array_length(v_job.findings)<1
 then raise exception 'failed Security job not independently identified' using errcode='PT409';end if;
 -- Only this exact static-rule false-positive family may be rechecked. Any
 -- other error/critical finding remains BLOCKING and cannot use this pathway.
 if not exists(select 1 from jsonb_array_elements(v_job.findings) f
     where f->>'code'='permissive_public_grant' and f->>'severity'='error')
    or exists(select 1 from jsonb_array_elements(v_job.findings) f
     where f->>'severity' in ('error','critical')
       and f->>'code' is distinct from 'permissive_public_grant')
    or exists(select 1 from jsonb_array_elements(v_job.findings) f
     where f->>'code'='permissive_public_grant'
       and (f->>'kind' is distinct from 'database_security'
            or f->>'source' is distinct from 'architecture_guardian_v1'
            or f->>'path' !~ '^supabase/migrations/[A-Za-z0-9_./-]+[.]sql$'))
 then raise exception 'security failure includes non-recheckable blocker'
    using errcode='PT409';end if;

 if (select count(*) from public.factory_specialist_lane_jobs j
   where j.run_id=p_run_id and j.candidate_commit=p_candidate_commit
     and j.required and j.role in ('qa','operations') and j.status='passed') <> 2
   or (select count(*) from public.factory_specialist_lane_jobs j
     where j.run_id=p_run_id and j.candidate_commit=p_candidate_commit
       and j.required and j.status in ('failed','blocked')) <> 1
   or not exists (select 1 from public.factory_evaluations e
       where e.run_id=p_run_id and e.eval_type='specialist_security'
         and e.status='failed' and e.baseline_ref=p_candidate_commit)
   or exists(select 1 from public.factory_audit_events a
       where a.run_id=p_run_id and a.event_type='specialist.auth_invoker_recheck.queued'
         and a.payload->>'candidate_commit'=p_candidate_commit)
 then raise exception 'review baseline, QA/Operations, or one-shot guard failed'
    using errcode='PT409';end if;

 select * into v_repair from public.factory_repair_jobs
 where specialist_job_id=p_security_job_id and source_run_id=p_run_id
   and candidate_commit=p_candidate_commit
   and source_role='security'
 for update;
 if not found or v_repair.status not in ('running','blocked')
 then raise exception 'associated security repair not stable' using errcode='PT409';end if;
 select * into v_unit from public.factory_change_set_work_units
 where id=v_repair.work_unit_id for share;
 select * into v_child from public.factory_runs
 where id=v_unit.run_id for share;
 if v_unit.status is distinct from 'blocked'
    or v_unit.base_commit is distinct from p_candidate_commit
    or v_unit.output_commit is not null
    or v_child.status is distinct from 'blocked'
    or v_child.lease_owner is not null or v_child.lease_expires_at is not null
 then raise exception 'failed repair worker may still be active' using errcode='PT409';end if;

 if exists(select 1 from public.factory_release_reports rr
      where rr.run_id=p_run_id and rr.status='released')
    or exists(select 1 from public.factory_human_gates h
      where h.run_id=p_run_id and h.status='pending')
 then raise exception 'release gate already active' using errcode='PT409';end if;

 v_original_findings=v_job.findings;
 insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,v_task.id,p_run_id,'system','independent-guardian-recheck',
    'specialist.auth_invoker_recheck.queued',
    jsonb_build_object('security_job_id',p_security_job_id,
      'repair_job_id',v_repair.id,
      'original_findings',v_original_findings,
      'previous_status',v_job.status,
      'candidate_commit',p_candidate_commit,
      'exact_sha_proof',p_verified_proof,
      'new_real_scan_required',true,
      'original_failure_preserved_in_evaluations',true,
      'release_authorized',false,'paid_model_calls',0));

 -- Requeue the same unique (run,role,SHA) lane for a real scanner pass.
 -- The prior failed eval and complete findings audit remain append-only.
 update public.factory_specialist_lane_jobs
 set status='queued',attempt_count=0,lease_owner=null,lease_expires_at=null,
     findings='[]'::jsonb,evidence=jsonb_build_object('_factory_epoch',v_generation,
       '_factory_verified_recheck',p_verified_proof->>'diff_sha256'),
     completed_at=null,updated_at=now()
 where id=p_security_job_id and status='failed';

 update public.factory_repair_jobs
 set status='blocked',updated_at=now()
 where id=v_repair.id and status in ('running','blocked');
 update public.factory_change_sets
 set status='ci_pending',release_run_id=p_run_id,updated_at=now(),
     metadata=metadata||jsonb_build_object('verified_invoker_recheck',
       jsonb_build_object('run_id',p_run_id,
         'candidate_commit',p_candidate_commit,
         'security_job_id',p_security_job_id,
         'release_authorized',false))
 where id=v_cs.id and status='blocked';
 update public.factory_runs
 set status='specialist_review_pending',
    metadata=metadata||jsonb_build_object('verified_invoker_recheck',
      jsonb_build_object('candidate_commit',p_candidate_commit,
        'security_job_id',p_security_job_id,'source','exact_sha_guardian',
        'release_authorized',false))
 where id=p_run_id and status='specialist_review_failed';

 return jsonb_build_object('status','specialist_review_pending',
   'run_id',p_run_id,'candidate_commit',p_candidate_commit,
   'security_job_id',p_security_job_id,'previous_failure_preserved',true,
   'new_review_required',true,'release_authorized',false);
end;
$body$;
revoke all on function public.factory_requeue_verified_invoker_security_once_v1(
 uuid,integer,text,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.factory_requeue_verified_invoker_security_once_v1(
 uuid,integer,text,uuid,jsonb) to service_role;
