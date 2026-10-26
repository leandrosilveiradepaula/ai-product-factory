-- Recover a failed, exact-SHA Preview browser test ONLY after a fresh, successful
-- non-mutating backend probe. This never sets browser_e2e=success or releases code.
-- Production application requires a separate authorized migration gate.
begin;

create or replace function public.factory_resume_preview_backend_unavailable_v1(
 p_run_id uuid,
 p_candidate_commit text,
 p_pr_number integer,
 p_verified_github jsonb,
 p_environment_probe jsonb
) returns jsonb
language plpgsql security invoker set search_path='' as $fn$
declare
 v_set public.factory_change_sets%rowtype;
 v_run public.factory_runs%rowtype;
 v_task public.factory_tasks%rowtype;
 v_project public.factory_projects%rowtype;
 v_control record;
 v_eval record;
 v_url text;
 v_checked_at timestamptz;
 v_prior_resumes integer;
begin
 if p_run_id is null or p_pr_number is null or p_pr_number < 1
    or p_candidate_commit is null or p_candidate_commit !~ '^[0-9a-f]{40}$'
    or jsonb_typeof(p_verified_github) is distinct from 'object'
    or jsonb_typeof(p_environment_probe) is distinct from 'object'
    or p_verified_github->>'pr_number' is distinct from p_pr_number::text
    or p_verified_github->>'head_sha' is distinct from p_candidate_commit
    or p_verified_github->>'pr_state' is distinct from 'open'
    or p_verified_github->>'merged' is distinct from 'false'
    or p_verified_github->>'vercel_state' is distinct from 'success'
 then
  raise exception 'exact current GitHub PR and Vercel evidence required' using errcode='PT400';
 end if;

 select * into v_set from public.factory_change_sets
 where release_run_id=p_run_id for update;
 if not found or v_set.status <> 'ci_pending'
    or v_set.candidate_commit is distinct from p_candidate_commit
    or v_set.lease_owner is not null or v_set.lease_expires_at is not null
    or v_set.metadata->'integration_release_request'->>'pr_number' is distinct from p_pr_number::text
    or v_set.metadata->'integration_release_request'->>'candidate_commit' is distinct from p_candidate_commit
 then
  raise exception 'change set not eligible for Preview environment recovery' using errcode='PT409';
 end if;

 select * into v_project from public.factory_projects
 where id=v_set.project_id;
 if not found or v_project.is_active is not true
    or v_project.repository is distinct from p_verified_github->>'repository'
 then
  raise exception 'project repository identity does not match' using errcode='PT409';
 end if;

 select state,generation into v_control from public.factory_project_execution_controls
 where project_id=v_set.project_id for share;
 if not found or v_control.state is distinct from 'running'
    or v_set.metadata->'integration_epoch_receipt'->>'generation'
       is distinct from v_control.generation::text
 then
  raise exception 'execution control prohibits recovery' using errcode='PT409';
 end if;

 select * into v_run from public.factory_runs where id=p_run_id for update;
 if not found or v_run.status <> 'failed'
    or v_run.candidate_commit is distinct from p_candidate_commit
    or v_run.branch_name is distinct from v_set.integration_branch
    or v_run.branch_name is distinct from p_verified_github->>'head_ref'
    or v_run.lease_owner is not null or v_run.lease_expires_at is not null
    or v_run.metadata->>'change_set_id' is distinct from v_set.id::text
    or v_run.metadata->>'execution_generation' is distinct from v_control.generation::text
 then
  raise exception 'delivery run or epoch is not eligible' using errcode='PT409';
 end if;

 select * into v_task from public.factory_tasks where id=v_run.task_id for update;
 if not found or v_task.status <> 'failed'
    or v_task.project_id is distinct from v_set.project_id
 then
  raise exception 'delivery task is not eligible' using errcode='PT409';
 end if;

 if (select count(*) from public.factory_specialist_lane_jobs j
       where j.run_id=p_run_id and j.required)=0
    or exists(select 1 from public.factory_specialist_lane_jobs j
       where j.run_id=p_run_id and j.required
         and (j.status <> 'passed' or j.candidate_commit is distinct from p_candidate_commit))
 then
  raise exception 'required specialists not verified' using errcode='PT409';
 end if;

 if not exists(select 1 from public.factory_evaluations e
     where e.run_id=p_run_id and e.eval_type='github_ci'
       and e.status='success' and e.baseline_ref=p_candidate_commit
       and e.result->>'head_sha'=p_candidate_commit
       and e.result->>'ci_state'='success'
       and e.result->>'pr'=p_pr_number::text)
    or not exists(select 1 from public.factory_evaluations e
     where e.run_id=p_run_id and e.eval_type='quality_gate'
       and e.status='success' and e.baseline_ref=p_candidate_commit
       and e.result->>'passed'='true')
 then
  raise exception 'exact native CI or quality gate is missing' using errcode='PT409';
 end if;

 select e.id,e.status,e.baseline_ref,e.result into v_eval
 from public.factory_evaluations e
 where e.run_id=p_run_id and e.eval_type='browser_e2e'
 order by e.created_at desc, e.id desc limit 1;
 if not found or v_eval.status <> 'failure'
    or position('http_503: fetch /api/session' in coalesce(v_eval.result->>'detail',''))=0
    or exists(select 1 from public.factory_evaluations e
       where e.run_id=p_run_id and e.eval_type='browser_e2e'
         and e.status='success')
 then
  raise exception 'not a verified backend-unavailable browser failure' using errcode='PT409';
 end if;

 v_url:=v_eval.baseline_ref;
 if v_url is null or v_url !~ '^https://[a-z0-9][a-z0-9-]*[.]vercel[.]app$'
    or v_eval.result->>'preview_url' is distinct from v_url
    or p_verified_github->>'preview_url' is distinct from v_url
    or not exists(select 1 from public.factory_deployments d
       where d.run_id=p_run_id and d.environment='preview'
         and d.status='success'
         and d.metadata->>'candidate_commit'=p_candidate_commit
         and d.metadata->>'preview_url'=v_url)
 then
  raise exception 'candidate Preview URL and deployment evidence mismatch' using errcode='PT409';
 end if;

 -- The unauthenticated health probe must be made after environment remediation.
 -- It carries ONLY status, content type, URL and timestamp (never credentials/body).
 if p_environment_probe->>'kind' is distinct from 'unauthenticated_json_session_probe'
    or p_environment_probe->>'candidate_commit' is distinct from p_candidate_commit
    or p_environment_probe->>'url' is distinct from v_url || '/api/session'
    or coalesce(p_environment_probe->>'http_status','') not in ('200','401')
    or coalesce(p_environment_probe->>'content_type','') !~ '^application/json(;.*)?
    or coalesce(p_environment_probe->>'checked_at','') !~ '^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}'
 then
  raise exception 'fresh non-mutating JSON session preflight required' using errcode='PT400';
 end if;
 begin
  v_checked_at:=(p_environment_probe->>'checked_at')::timestamptz;
 exception when invalid_datetime_format or datetime_field_overflow then
  raise exception 'invalid environment probe timestamp' using errcode='PT400';
 end;
 if v_checked_at > now()+interval '5 seconds'
    or v_checked_at < now()-interval '10 minutes'
 then
  raise exception 'environment probe expired or in the future' using errcode='PT400';
 end if;

 select count(*) into v_prior_resumes
 from public.factory_audit_events a
 where a.run_id=p_run_id and a.project_id=v_set.project_id
   and a.event_type='preview.backend_unavailable.resumed';
 if v_prior_resumes >= 2 then
  raise exception 'bounded Preview environment retry budget exhausted' using errcode='PT409';
 end if;

 update public.factory_runs set status='preview_ready',
   finished_at=null,last_error=null where id=p_run_id;
 update public.factory_tasks set status='integrated',
   updated_at=now() where id=v_task.id;
 insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
 ) values (
    v_set.project_id,v_task.id,p_run_id,'system','preview-environment-recovery',
    'preview.backend_unavailable.resumed',
    jsonb_build_object(
      'candidate_commit',p_candidate_commit,'pr_number',p_pr_number,
      'browser_failure_eval_id',v_eval.id,
      'probe_http_status',p_environment_probe->>'http_status',
      'probe_checked_at',p_environment_probe->>'checked_at',
      'preview_url',v_url,'original_failure_preserved',true,
      'browser_verified',false,'release_authorized',false)
 );
 return jsonb_build_object(
   'run_id',p_run_id,'status','preview_ready',
   'candidate_commit',p_candidate_commit,'original_failure_preserved',true,
   'browser_verified',false,'release_authorized',false,
   'attempt',v_prior_resumes+1);
end;
$fn$;

revoke all on function public.factory_resume_preview_backend_unavailable_v1(uuid,text,integer,jsonb,jsonb)
 from public,anon,authenticated;
grant execute on function public.factory_resume_preview_backend_unavailable_v1(uuid,text,integer,jsonb,jsonb)
 to service_role;
commit;
