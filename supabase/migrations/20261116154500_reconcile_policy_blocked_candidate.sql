-- Repair a blocked nonproduction candidate after its existing open PR advanced.
-- VERSIONED ONLY: service_role migration is a separate human approval gate.
-- This function NEVER marks a DoD check passed, deploys, merges, releases,
-- publishes a production change, or approves a paid service.
begin;
create or replace function public.factory_reconcile_policy_blocked_candidate_v1(
 p_change_set_id uuid, p_run_id uuid, p_pr_number integer,
 p_previous_commit text, p_new_commit text, p_verified_evidence jsonb
) returns jsonb
language plpgsql security invoker set search_path='' as $factory$
declare
 v_set public.factory_change_sets%rowtype;
 v_run public.factory_runs%rowtype;
 v_report public.factory_release_reports%rowtype;
 v_project public.factory_projects%rowtype;
 v_control record;
 v_request jsonb;
 v_epoch jsonb;
 v_missing jsonb;
 v_files jsonb;
 v_path jsonb;
 v_nonhuman integer;
 v_original_commit text;
 v_origin_count integer;
 v_prior_receipt jsonb;
begin
 if p_change_set_id is null or p_run_id is null or p_pr_number is null
    or p_pr_number < 1
    or p_previous_commit !~ '^[0-9a-f]{40}$'
    or p_new_commit !~ '^[0-9a-f]{40}$'
    or p_new_commit=p_previous_commit
    or jsonb_typeof(p_verified_evidence) is distinct from 'object'
    or p_verified_evidence->>'old_sha' is distinct from p_previous_commit
    or p_verified_evidence->>'new_sha' is distinct from p_new_commit
    or p_verified_evidence->>'pr_number' is distinct from p_pr_number::text
    or p_verified_evidence->>'compare_status' is distinct from 'ahead'
    or p_verified_evidence->>'behind_by' is distinct from '0'
    or coalesce((p_verified_evidence->>'ahead_by') ~ '^[1-9][0-9]*$',false) is false
    or length(coalesce(p_verified_evidence->>'reason','')) > 500
    or p_verified_evidence->>'ci_state' is distinct from 'success'
 then raise exception 'invalid blocked release candidate evidence' using errcode='PT400';
 end if;
 if (p_verified_evidence->>'ahead_by')::integer > 100 then
  raise exception 'candidate history exceeds bounded recovery' using errcode='PT400';
 end if;
 v_files:=p_verified_evidence->'changed_files';
 if jsonb_typeof(v_files) is distinct from 'array'
    or jsonb_array_length(v_files) not between 1 and 300 then
  raise exception 'bounded candidate file inventory required' using errcode='PT400';
 end if;
 for v_path in select value from jsonb_array_elements(v_files) loop
  if jsonb_typeof(v_path) is distinct from 'string'
     or length(v_path#>>'{}') not between 1 and 240
     or (v_path#>>'{}') ~ '(^/|\\|//|(^|/)\.\.?(/|$))'
  then raise exception 'unsafe candidate path' using errcode='PT400'; end if;
 end loop;

 select * into v_set from public.factory_change_sets
 where id=p_change_set_id for update;
 if not found or v_set.status<>'ci_pending'
    or v_set.release_run_id is distinct from p_run_id
    or v_set.candidate_commit is distinct from p_previous_commit
    or v_set.integration_branch in ('main','master')
    or v_set.integration_branch !~ '^factory/change-set-[a-f0-9-]+$'
    or v_set.lease_owner is not null or v_set.lease_expires_at is not null
 then raise exception 'nonproduction change set identity revoked' using errcode='PT409'; end if;

 select * into v_project from public.factory_projects
 where id=v_set.project_id for share;
 if not found or v_project.is_active is distinct from true
    or v_project.project_kind not in ('greenfield','existing')
    or v_project.repository is distinct from p_verified_evidence->>'repository'
 then raise exception 'active project identity revoked' using errcode='PT409'; end if;
 if p_verified_evidence->>'branch' is distinct from v_set.integration_branch then
  raise exception 'nonproduction branch mismatch' using errcode='PT409'; end if;
 select state,generation into v_control
 from public.factory_project_execution_controls
 where project_id=v_set.project_id for share;
 if not found or v_control.state is distinct from 'running'
    or v_control.generation<=0 then
  raise exception 'project generation revoked' using errcode='PT409'; end if;

 select * into v_run from public.factory_runs where id=p_run_id for update;
 if not found or v_run.task_id is distinct from v_set.root_task_id
    or v_run.status is distinct from 'release_policy_blocked'
    or v_run.candidate_commit is distinct from p_previous_commit
    or v_run.branch_name is distinct from v_set.integration_branch
    or v_run.lease_owner is not null or v_run.lease_expires_at is not null
    or v_run.metadata->>'source' is distinct from 'change-set'
    or v_run.metadata->>'change_set_id' is distinct from p_change_set_id::text
    or v_run.metadata->>'execution_generation' is distinct from v_control.generation::text
 then raise exception 'blocked release run identity revoked' using errcode='PT409'; end if;

 v_request:=v_set.metadata->'integration_release_request';
 v_epoch:=v_set.metadata->'integration_epoch_receipt';
 if jsonb_typeof(v_request) is distinct from 'object'
    or jsonb_typeof(v_epoch) is distinct from 'object'
    or v_request->>'candidate_commit' is distinct from p_previous_commit
    or v_request->>'branch' is distinct from v_set.integration_branch
    or v_request->>'pr_number' is distinct from p_pr_number::text
    or v_epoch->>'candidate_commit' is distinct from p_previous_commit
    or v_epoch->>'project_id' is distinct from v_set.project_id::text
    or v_epoch->>'generation' is distinct from v_control.generation::text
 then raise exception 'immutable integration epoch mismatch' using errcode='PT409'; end if;

 select * into v_report from public.factory_release_reports
 where run_id=p_run_id for update;
 if not found or v_report.project_id is distinct from v_set.project_id
    or v_report.status is distinct from 'blocked'
    or v_report.candidate_commit is distinct from p_previous_commit
    or v_report.report->>'candidate_commit' is distinct from p_previous_commit
    or v_report.report->>'release_state' is distinct from 'blocked'
    or jsonb_typeof(v_report.report->'definition_of_done'->'missing') is distinct from 'array'
 then raise exception 'prior release policy blocker absent' using errcode='PT409'; end if;
 v_missing:=v_report.report->'definition_of_done'->'missing';
 if jsonb_array_length(v_missing) not between 1 and 25 then
  raise exception 'invalid prior release blocker inventory' using errcode='PT409'; end if;
 select count(*) into v_nonhuman
 from jsonb_array_elements(v_missing) x
 where jsonb_typeof(x)='object' and x->'human_only'='false'::jsonb;
 if v_nonhuman<1 then
  raise exception 'human-only release blocker cannot requeue CI' using errcode='PT409'; end if;
 -- Verify original PR issuance and the FULL independently audited
 -- reconciliation chain; do not conflate original SHA with latest candidate.
 select count(*),max(u.metadata->>'head_sha')
 into v_origin_count,v_original_commit
 from public.factory_tool_usage u
 where u.run_id=p_run_id and u.operation='create_pr'
   and u.metadata->>'pr'=p_pr_number::text
   and u.metadata->>'change_set_id'=p_change_set_id::text;
 if v_origin_count<>1 or v_original_commit !~ '^[0-9a-f]{40}$'
 then raise exception 'immutable original PR receipt missing or ambiguous'
      using errcode='PT409'; end if;
 if v_original_commit is distinct from p_previous_commit then
   select u.metadata into v_prior_receipt
   from public.factory_tool_usage u
   where u.run_id=p_run_id and u.operation='reconcile_pr_candidate'
   order by u.created_at desc,u.id desc limit 1;
   if v_prior_receipt is null
     or v_prior_receipt->>'change_set_id' is distinct from p_change_set_id::text
     or v_prior_receipt->>'pr_number' is distinct from p_pr_number::text
     or v_prior_receipt->>'previous_commit' is distinct from v_original_commit
     or v_prior_receipt->>'old_sha' is distinct from v_original_commit
     or v_prior_receipt->>'new_sha' is distinct from p_previous_commit
     or v_prior_receipt->>'candidate_commit' is distinct from p_previous_commit
     or v_prior_receipt->>'compare_status' is distinct from 'ahead'
     or v_prior_receipt->>'behind_by' is distinct from '0'
     or v_prior_receipt->>'ci_conclusion' is distinct from 'success'
     or v_prior_receipt->>'repository' is distinct from v_project.repository
     or v_prior_receipt->>'branch' is distinct from v_set.integration_branch
   then raise exception 'previous candidate reconciliation chain invalid'
        using errcode='PT409'; end if;
 end if;

 -- Retain the blocked release report and every original evaluation and
 -- specialist review as historical evidence. New jobs MUST use the new SHA.
 update public.factory_runs
 set status='ci_pending',candidate_commit=p_new_commit,last_error=null,
     metadata=metadata||jsonb_build_object(
       'policy_blocked_candidate_recovery',
       jsonb_build_object('previous_commit',p_previous_commit,
          'candidate_commit',p_new_commit,'previous_status','release_policy_blocked',
          'release_authorized',false,'nonhuman_dod_still_pending',true,'at',now()))
 where id=p_run_id and status='release_policy_blocked';
 if not found then raise exception 'run changed during atomic recovery' using errcode='PT409'; end if;

 update public.factory_change_sets
 set candidate_commit=p_new_commit,updated_at=now(),
 metadata=jsonb_set(
   jsonb_set(v_set.metadata,
     '{integration_release_request,candidate_commit}',to_jsonb(p_new_commit),false),
     '{integration_epoch_receipt,candidate_commit}',to_jsonb(p_new_commit),false)
    ||jsonb_build_object('last_policy_blocked_candidate_reconciliation',
       jsonb_build_object('previous_commit',p_previous_commit,
          'candidate_commit',p_new_commit,'release_authorized',false,'at',now()))
 where id=p_change_set_id and status='ci_pending';
 if not found then raise exception 'change set changed during atomic recovery' using errcode='PT409'; end if;

 insert into public.factory_tool_usage(
  run_id,tool_family,operation,usage_units,estimated_cost,metadata
 ) values(p_run_id,'github','reconcile_pr_candidate',1,0,
    p_verified_evidence||jsonb_build_object(
      'change_set_id',p_change_set_id,
      'previous_commit',v_original_commit,
      'old_sha',v_original_commit,'original_head_sha',v_original_commit,
      'prior_candidate_commit',p_previous_commit,
      'candidate_commit',p_new_commit,
      'recovery_source','blocked_release_policy','release_authorized',false));
 insert into public.factory_audit_events(
  project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
 ) values(v_set.project_id,v_set.root_task_id,p_run_id,'system',
   'blocked-candidate-reconciler','change_set.blocked_release_candidate.reconciled',
   jsonb_build_object('change_set_id',p_change_set_id,'pr_number',p_pr_number,
      'previous_commit',p_previous_commit,'candidate_commit',p_new_commit,
      'old_evidence_preserved',true,'new_specialist_approval_required',true,
      'new_browser_evidence_required',true,'nonhuman_dod_still_pending',true,
      'automatic_merge',false,'release_authorized',false,'paid_model_calls',0));
 return jsonb_build_object('status','ci_pending','run_id',p_run_id,
    'previous_commit',p_previous_commit,'candidate_commit',p_new_commit,
    'release_authorized',false,'old_evidence_preserved',true,
    'new_specialist_approval_required',true,
    'nonhuman_dod_still_pending',true);
end;
$factory$;
revoke all on function public.factory_reconcile_policy_blocked_candidate_v1(uuid,uuid,integer,text,text,jsonb)
 from public,anon,authenticated;
grant execute on function public.factory_reconcile_policy_blocked_candidate_v1(uuid,uuid,integer,text,text,jsonb)
 to service_role;
commit;
