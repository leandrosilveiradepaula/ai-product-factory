-- Exact-SHA recovery of an original failed greenfield Preview. Atomic, one-shot,
-- no new Start/PR, no release authorization, no rewriting of old evidence.
-- Apply only after human approval of protected Factory Control Plane migration.
create or replace function public.factory_reconcile_failed_preview_candidate_v1(
  p_change_set_id uuid, p_run_id uuid, p_pr_number integer,
  p_previous_commit text, p_new_commit text, p_verified_evidence jsonb
) returns jsonb
language plpgsql security invoker set search_path='' as $body$
declare
 v_set public.factory_change_sets%rowtype;
 v_run public.factory_runs%rowtype;
 v_task public.factory_tasks%rowtype;
 v_project public.factory_projects%rowtype;
 v_report public.factory_release_reports%rowtype;
 v_control record;
 v_failure record;
 v_browser public.factory_project_state_snapshots%rowtype;
 v_request jsonb;
 v_epoch jsonb;
 v_doc jsonb;
 v_original text;
 v_prior jsonb;
 v_count integer;
 v_nonhuman integer;
begin
 if p_change_set_id is null or p_run_id is null or p_pr_number<1
  or p_previous_commit !~ '^[0-9a-f]{40}$'
  or p_new_commit !~ '^[0-9a-f]{40}$' or p_new_commit=p_previous_commit
  or jsonb_typeof(p_verified_evidence) is distinct from 'object'
  or p_verified_evidence->>'source' is distinct from 'github_actions_exact_sha'
  or p_verified_evidence->>'old_sha' is distinct from p_previous_commit
  or p_verified_evidence->>'new_sha' is distinct from p_new_commit
  or p_verified_evidence->>'pr_number' is distinct from p_pr_number::text
  or p_verified_evidence->>'compare_status' is distinct from 'ahead'
  or p_verified_evidence->>'behind_by' is distinct from '0'
  or coalesce((p_verified_evidence->>'ahead_by') ~ '^[1-9][0-9]*$',false) is false
  or p_verified_evidence->>'ci_state' is distinct from 'success'
  or p_verified_evidence->>'ci_source' is distinct from 'github_actions_checks'
  or p_verified_evidence->>'release_authorized' is distinct from 'false'
  or p_verified_evidence->>'new_specialist_approval_required' is distinct from 'true'
  or p_verified_evidence->>'recheck_dod_required' is distinct from 'true'
  or coalesce((p_verified_evidence->>'native_checks')~'^[1-9][0-9]*$',false) is false
  or coalesce((p_verified_evidence->>'native_workflows')~'^[1-9][0-9]*$',false) is false
  or coalesce((p_verified_evidence->>'browser_run_id')~'^[1-9][0-9]*$',false) is false
  or coalesce((p_verified_evidence->>'verifier_factory_sha')~'^[a-f0-9]{40}$',false) is false
  or coalesce((p_verified_evidence->>'browser_snapshot_id')~
    '^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$',false) is false
  or coalesce((p_verified_evidence->>'preview_url')~
    '^https://[a-z0-9][a-z0-9-]*[.]vercel[.]app$',false) is false
  or length(p_verified_evidence::text)>10000
 then raise exception 'exact-SHA recovery evidence invalid' using errcode='PT400'; end if;
 if (p_verified_evidence->>'ahead_by')::integer not between 1 and 32
   or (p_verified_evidence->>'native_checks')::integer<2
 then raise exception 'candidate history or native CI insufficient' using errcode='PT400'; end if;
 v_doc:=p_verified_evidence->'changed_files';
 if jsonb_typeof(v_doc) is distinct from 'array'
   or jsonb_array_length(v_doc) not between 1 and 300
 then raise exception 'bounded changed file inventory required' using errcode='PT400'; end if;
 for v_prior in select value from jsonb_array_elements(v_doc) loop
   if jsonb_typeof(v_prior) is distinct from 'string'
      or length(v_prior#>>'{}') not between 1 and 240
      or (v_prior#>>'{}') !~ '^[A-Za-z0-9_./-]+$'
      or (v_prior#>>'{}') ~ '(^/|//|(^|/)[.][.]?(/|$))'
   then raise exception 'invalid changed file path' using errcode='PT400'; end if;
 end loop;

 select * into v_set from public.factory_change_sets
 where id=p_change_set_id for update;
 if not found or v_set.status is distinct from 'ci_pending'
  or v_set.release_run_id is distinct from p_run_id
  or v_set.candidate_commit is distinct from p_previous_commit
  or v_set.integration_branch !~ '^factory/change-set-[a-f0-9-]+$'
  or v_set.lease_owner is not null or v_set.lease_expires_at is not null
 then raise exception 'old Change Set identity revoked' using errcode='PT409'; end if;

 select * into v_project from public.factory_projects
 where id=v_set.project_id for share;
 select state,generation into v_control
 from public.factory_project_execution_controls
 where project_id=v_set.project_id for share;
 if v_project.id is null or v_project.is_active is distinct from true
  or v_project.project_kind is distinct from 'greenfield'
  or v_project.repository is distinct from p_verified_evidence->>'repository'
  or v_project.manifest->'preview'->>'required' is distinct from 'true'
  or v_control.state is distinct from 'running' or v_control.generation<1
  or p_verified_evidence->>'branch' is distinct from v_set.integration_branch
 then raise exception 'project, preview policy or execution epoch invalid'
    using errcode='PT409'; end if;

 select * into v_run from public.factory_runs
 where id=p_run_id for update;
 if not found or v_run.task_id is distinct from v_set.root_task_id
  or v_run.status is distinct from 'failed'
  or v_run.candidate_commit is distinct from p_previous_commit
  or v_run.branch_name is distinct from v_set.integration_branch
  or v_run.lease_owner is not null or v_run.lease_expires_at is not null
  or v_run.metadata->>'source' is distinct from 'change-set'
  or v_run.metadata->>'change_set_id' is distinct from p_change_set_id::text
  or v_run.metadata->>'execution_generation' is distinct from v_control.generation::text
 then raise exception 'old failed delivery run identity revoked' using errcode='PT409'; end if;

 v_request:=v_set.metadata->'integration_release_request';
 v_epoch:=v_set.metadata->'integration_epoch_receipt';
 if v_request->>'candidate_commit' is distinct from p_previous_commit
  or v_request->>'pr_number' is distinct from p_pr_number::text
  or v_request->>'branch' is distinct from v_set.integration_branch
  or v_epoch->>'candidate_commit' is distinct from p_previous_commit
  or v_epoch->>'generation' is distinct from v_control.generation::text
  or v_epoch->>'project_id' is distinct from v_project.id::text
 then raise exception 'source epoch and integration PR receipt mismatch'
    using errcode='PT409'; end if;

 select * into v_task from public.factory_tasks
 where id=v_set.root_task_id for update;
 if v_task.id is null or v_task.project_id is distinct from v_project.id
  or v_task.status is distinct from 'failed'
 then raise exception 'original root task not terminal failed' using errcode='PT409'; end if;

 select * into v_report from public.factory_release_reports
 where run_id=p_run_id for share;
 if not found or v_report.project_id is distinct from v_project.id
  or v_report.status is distinct from 'blocked'
  or v_report.report->>'release_state' is distinct from 'blocked'
  or jsonb_typeof(v_report.report->'definition_of_done'->'missing') is distinct from 'array'
 then raise exception 'historical release DoD blocker missing' using errcode='PT409'; end if;
 select count(*) into v_nonhuman
 from jsonb_array_elements(v_report.report->'definition_of_done'->'missing') x
 where jsonb_typeof(x)='object' and x->'human_only'='false'::jsonb;
 if v_nonhuman<1 then raise exception 'cannot reuse human-only gate as CI recovery'
    using errcode='PT409'; end if;
 if exists(select 1 from public.factory_release_reports
    where run_id=p_run_id and status='released')
   or exists(select 1 from public.factory_human_gates
    where run_id=p_run_id and status='pending')
 then raise exception 'release or human gate already active' using errcode='PT409'; end if;

 select e.status,e.created_at,e.result into v_failure
 from public.factory_evaluations e
 where e.run_id=p_run_id and e.eval_type='browser_e2e'
 order by e.created_at desc,e.id desc limit 1;
 if not found or v_failure.status is distinct from 'failure'
  or not exists(select 1 from public.factory_audit_events a
    where a.run_id=p_run_id and a.event_type='preview.failed')
 then raise exception 'original terminal browser failure missing'
    using errcode='PT409'; end if;

 select * into v_browser
 from public.factory_project_state_snapshots
 where id=(p_verified_evidence->>'browser_snapshot_id')::uuid
 for share;
 if not found or v_browser.project_id is distinct from v_project.id
  or v_browser.run_id is not null
  or v_browser.observed_stage is distinct from 'verification'
  or v_browser.created_at<=v_failure.created_at
  or v_browser.evidence->>'candidate_commit' is distinct from p_new_commit
  or v_browser.evidence->>'target_repository' is distinct from v_project.repository
  or v_browser.evidence->'preview'->>'provider' is distinct from 'vercel'
  or v_browser.evidence->'preview'->>'status' is distinct from 'browser_verified'
  or v_browser.evidence->'preview'->>'url' is distinct from p_verified_evidence->>'preview_url'
  or v_browser.evidence->'preview'->>'browser_verifier_run_id'
       is distinct from p_verified_evidence->>'browser_run_id'
  or v_browser.evidence->'preview'->>'verifier_factory_commit'
       is distinct from p_verified_evidence->>'verifier_factory_sha'
  or v_browser.source_status->>'github_target' is distinct from 'verified'
  or v_browser.source_status->>'vercel_preview' is distinct from 'resolved'
  or v_browser.source_status->>'browser_visual_validation' is distinct from 'success'
 then raise exception 'independent new SHA browser proof missing'
    using errcode='PT409'; end if;

 select count(*),max(u.metadata->>'head_sha') into v_count,v_original
 from public.factory_tool_usage u
 where u.run_id=p_run_id and u.operation='create_pr'
  and u.metadata->>'pr'=p_pr_number::text
  and u.metadata->>'change_set_id'=p_change_set_id::text;
 if v_count<>1 or v_original !~ '^[0-9a-f]{40}$'
 then raise exception 'immutable original PR receipt missing' using errcode='PT409';end if;
 if v_original is distinct from p_previous_commit then
   select u.metadata into v_prior from public.factory_tool_usage u
   where u.run_id=p_run_id and u.operation='reconcile_pr_candidate'
   order by u.created_at desc,u.id desc limit 1;
   if not found or v_prior->>'previous_commit' is distinct from v_original
    or v_prior->>'candidate_commit' is distinct from p_previous_commit
    or v_prior->>'new_sha' is distinct from p_previous_commit
    or v_prior->>'pr_number' is distinct from p_pr_number::text
   then raise exception 'current candidate provenance chain broken'
      using errcode='PT409'; end if;
 end if;

 update public.factory_runs
 set status='ci_pending',candidate_commit=p_new_commit,finished_at=null,last_error=null,
     metadata=metadata||jsonb_build_object('failed_preview_recovery_v1',
       jsonb_build_object('previous_commit',p_previous_commit,
         'candidate_commit',p_new_commit,
         'original_failure_preserved',true,
         'previous_finished_at',v_run.finished_at,
         'browser_snapshot_id',v_browser.id,
         'new_specialists_required',true,
         'release_authorized',false,'recovery_at',now()))
 where id=p_run_id and status='failed';
 if not found then raise exception 'run changed during recovery' using errcode='PT409';end if;
 update public.factory_change_sets
 set candidate_commit=p_new_commit,updated_at=now(),
     metadata=jsonb_set(jsonb_set(v_set.metadata,
       '{integration_release_request,candidate_commit}',to_jsonb(p_new_commit),false),
       '{integration_epoch_receipt,candidate_commit}',to_jsonb(p_new_commit),false)
       ||jsonb_build_object('failed_preview_candidate_reconciliation_v1',
          jsonb_build_object('previous_commit',p_previous_commit,
            'candidate_commit',p_new_commit,'browser_snapshot_id',v_browser.id,
            'release_authorized',false,'recovery_at',now()))
 where id=p_change_set_id and status='ci_pending';
 if not found then raise exception 'Change Set changed during recovery' using errcode='PT409';end if;
 -- The code was integrated successfully before the PREVIEW failed; do not
 -- re-run Product/Start. Only the CI+specialist+Preview delivery stage resumes.
 update public.factory_tasks set status='integrated',updated_at=now()
 where id=v_set.root_task_id and status='failed';
 if not found then raise exception 'root task changed during recovery' using errcode='PT409';end if;

 insert into public.factory_tool_usage(run_id,tool_family,operation,usage_units,estimated_cost,metadata)
 values(p_run_id,'github','reconcile_pr_candidate',1,0,
  p_verified_evidence||jsonb_build_object(
    'change_set_id',p_change_set_id,'previous_commit',v_original,
    'original_head_sha',v_original,'old_sha',v_original,
    'candidate_commit',p_new_commit,'recovery_source','failed_preview',
    'release_authorized',false));
 insert into public.factory_audit_events(
  project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,v_set.root_task_id,p_run_id,'system',
  'verified-preview-recovery','preview.failed_candidate.reconciled',
  jsonb_build_object('change_set_id',p_change_set_id,
    'pr_number',p_pr_number,'previous_commit',p_previous_commit,
    'candidate_commit',p_new_commit,'browser_snapshot_id',v_browser.id,
    'historical_failures_preserved',true,
    'new_specialist_approval_required',true,'new_ci_required',true,
    'new_dod_review_required',true,'automatic_merge',false,
    'release_authorized',false,'paid_model_calls',0));
 return jsonb_build_object('status','ci_pending','run_id',p_run_id,
   'previous_commit',p_previous_commit,'candidate_commit',p_new_commit,
   'old_evidence_preserved',true,'release_authorized',false,
   'new_specialist_approval_required',true,'new_dod_review_required',true);
end;
$body$;

revoke all on function public.factory_reconcile_failed_preview_candidate_v1(
 uuid,uuid,integer,text,text,jsonb) from public,anon,authenticated;
grant execute on function public.factory_reconcile_failed_preview_candidate_v1(
 uuid,uuid,integer,text,text,jsonb) to service_role;
