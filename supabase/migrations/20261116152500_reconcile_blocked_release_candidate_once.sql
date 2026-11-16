-- One-shot development candidate recovery AFTER a blocked policy review.
-- Migration is a PRODUCTION CONTROL PLANE gate: do not apply without separate
-- operator authorization. No application DB, RLS changes, merge or release.
-- Immutable original PR and historical QA/Preview/release-block evidence remain.
begin;

create or replace function public.factory_reconcile_blocked_release_candidate_once_v1(
    p_change_set_id uuid,
    p_run_id uuid,
    p_pr_number integer,
    p_prior_candidate text,
    p_new_candidate text,
    p_github_evidence jsonb
) returns jsonb
language plpgsql security invoker set search_path = '' as $reconcile$
declare
    v_set public.factory_change_sets%rowtype;
    v_run public.factory_runs%rowtype;
    v_project public.factory_projects%rowtype;
    v_task public.factory_tasks%rowtype;
    v_report public.factory_release_reports%rowtype;
    v_control record;
    v_original_sha text;
    v_prior_receipt jsonb;
    v_request jsonb;
    v_epoch jsonb;
    v_proof jsonb;
    v_check jsonb;
begin
    if p_change_set_id is null or p_run_id is null
       or p_pr_number is null or p_pr_number < 1
       or p_prior_candidate is null
       or p_prior_candidate !~ '^[a-f0-9]{40}$'
       or p_new_candidate is null
       or p_new_candidate !~ '^[a-f0-9]{40}$'
       or p_prior_candidate = p_new_candidate
       or jsonb_typeof(p_github_evidence) is distinct from 'object'
       or p_github_evidence->>'source' is distinct from 'github_actions_exact_sha'
       or p_github_evidence->>'pr_number' is distinct from p_pr_number::text
       or p_github_evidence->>'pr_head_sha' is distinct from p_new_candidate
       or p_github_evidence->>'branch_head_sha' is distinct from p_new_candidate
       or p_github_evidence->>'ci_sha' is distinct from p_new_candidate
       or p_github_evidence->>'prior_candidate_commit' is distinct from p_prior_candidate
       or p_github_evidence->>'new_sha' is distinct from p_new_candidate
       or p_github_evidence->>'pr_state' is distinct from 'open'
       or p_github_evidence->>'pr_merged' is distinct from 'false'
       or p_github_evidence->>'pr_draft' is distinct from 'false'
       or p_github_evidence->>'pr_base' is distinct from 'main'
       or p_github_evidence->>'compare_status' is distinct from 'ahead'
       or p_github_evidence->>'prior_compare_status' is distinct from 'ahead'
       or p_github_evidence->>'behind_by' is distinct from '0'
       or p_github_evidence->>'prior_behind_by' is distinct from '0'
       or coalesce((p_github_evidence->>'ahead_by') ~ '^[1-9][0-9]*$',false) is false
       or coalesce((p_github_evidence->>'prior_ahead_by') ~ '^[1-9][0-9]*$',false) is false
       or (p_github_evidence->>'ahead_by')::integer > 200
       or (p_github_evidence->>'prior_ahead_by')::integer > 100
       or coalesce((p_github_evidence->>'ci_run_id') ~ '^[1-9][0-9]{0,15}$',false) is false
       or jsonb_typeof(p_github_evidence->'ci_checks') is distinct from 'array'
       or jsonb_array_length(p_github_evidence->'ci_checks') not between 1 and 50
    then
        raise exception 'invalid independently verified CI candidate proof' using errcode='PT400';
    end if;
    -- Requiring every native check to be successful is only an admission
    -- preflight. CI and specialists MUST run again on the new SHA.
    for v_check in select value from jsonb_array_elements(p_github_evidence->'ci_checks')
    loop
        if jsonb_typeof(v_check) is distinct from 'object'
           or nullif(btrim(v_check->>'name'),'') is null
           or v_check->>'app' is distinct from 'github-actions'
           or v_check->>'status' is distinct from 'completed'
           or v_check->>'conclusion' is distinct from 'success'
           or v_check->>'head_sha' is distinct from p_new_candidate
        then raise exception 'CI check proof is incomplete' using errcode='PT400'; end if;
    end loop;

    select * into v_set from public.factory_change_sets
    where id=p_change_set_id for update;
    if not found or v_set.status is distinct from 'ci_pending'
       or v_set.release_run_id is distinct from p_run_id
       or v_set.candidate_commit is distinct from p_prior_candidate
       or v_set.integration_branch is null
       or v_set.integration_branch !~ '^factory/(change-set|journey)-[0-9a-f-]+$'
       or v_set.lease_owner is not null or v_set.lease_expires_at is not null
       or v_set.current_wave < 2
    then raise exception 'Change Set not eligible for postreview CI recovery' using errcode='PT409'; end if;
    select * into v_project from public.factory_projects where id=v_set.project_id for share;
    if not found or v_project.is_active is distinct from true
       or v_project.repository is distinct from p_github_evidence->>'repository'
       or v_project.project_kind not in ('existing','greenfield')
    then raise exception 'active project repository mismatch' using errcode='PT409'; end if;
    select state,generation into v_control
    from public.factory_project_execution_controls
    where project_id=v_project.id for share;
    if not found or v_control.state is distinct from 'running' or v_control.generation<1
    then raise exception 'project execution control revoked' using errcode='PT409'; end if;
    select * into v_run from public.factory_runs where id=p_run_id for update;
    if not found or v_run.task_id is distinct from v_set.root_task_id
       or v_run.status is distinct from 'release_policy_blocked'
       or v_run.candidate_commit is distinct from p_prior_candidate
       or v_run.branch_name is distinct from v_set.integration_branch
       or v_run.lease_owner is not null or v_run.lease_expires_at is not null
       or v_run.metadata->>'source' is distinct from 'change-set'
       or v_run.metadata->>'change_set_id' is distinct from v_set.id::text
       or v_run.metadata->>'execution_generation' is distinct from v_control.generation::text
    then raise exception 'blocked run identity or lease mismatch' using errcode='PT409'; end if;
    select * into v_task from public.factory_tasks where id=v_run.task_id for share;
    if not found or v_task.project_id is distinct from v_project.id
       or v_task.status is distinct from 'integrated'
    then raise exception 'integrated root task required' using errcode='PT409'; end if;
    select * into v_report from public.factory_release_reports
    where run_id=p_run_id for share;
    if not found or v_report.status is distinct from 'blocked'
       or v_report.candidate_commit is distinct from p_prior_candidate
       or v_report.report->>'release_state' is distinct from 'blocked'
    then raise exception 'previous release must be genuinely blocked' using errcode='PT409'; end if;
    v_request:=v_set.metadata->'integration_release_request';
    v_epoch:=v_set.metadata->'integration_epoch_receipt';
    if jsonb_typeof(v_request) is distinct from 'object'
       or v_request->>'candidate_commit' is distinct from p_prior_candidate
       or v_request->>'branch' is distinct from v_set.integration_branch
       or v_request->>'pr_number' is distinct from p_pr_number::text
       or v_request->>'issue_number' is null
       or jsonb_typeof(v_epoch) is distinct from 'object'
       or v_epoch->>'candidate_commit' is distinct from p_prior_candidate
       or v_epoch->>'project_id' is distinct from v_project.id::text
       or v_epoch->>'generation' is distinct from v_control.generation::text
       or coalesce((v_epoch->>'wave') ~ '^[0-9]+$',false) is false
       or (v_epoch->>'wave')::integer not between 2 and 1000
       or p_github_evidence->>'branch' is distinct from v_set.integration_branch
    then raise exception 'immutable integration epoch mismatch' using errcode='PT409'; end if;

    -- The original create_pr receipt is preserved after any prior CI
    -- candidate reconciliation. New receipt aliases from ORIGINAL -> NEW
    -- for existing queue consumers, and binds PRIOR -> NEW separately.
    select u.metadata->>'head_sha' into v_original_sha
    from public.factory_tool_usage u
    where u.run_id=p_run_id and u.operation='create_pr'
      and u.metadata->>'pr'=p_pr_number::text
      and u.metadata->>'change_set_id'=v_set.id::text
    order by u.created_at desc,u.id desc limit 1;
    if v_original_sha is null or v_original_sha !~ '^[a-f0-9]{40}$'
    then raise exception 'original immutable PR receipt missing' using errcode='PT409'; end if;
    select u.metadata into v_prior_receipt
    from public.factory_tool_usage u
    where u.run_id=p_run_id and u.operation='reconcile_pr_candidate'
    order by u.created_at desc,u.id desc limit 1;
    if v_prior_receipt is null then
        if v_original_sha is distinct from p_prior_candidate
        then raise exception 'unexplained previous candidate divergence' using errcode='PT409'; end if;
    elsif v_prior_receipt->>'previous_commit' is distinct from v_original_sha
       or v_prior_receipt->>'old_sha' is distinct from v_original_sha
       or v_prior_receipt->>'new_sha' is distinct from p_prior_candidate
       or v_prior_receipt->>'candidate_commit' is distinct from p_prior_candidate
       or v_prior_receipt->>'compare_status' is distinct from 'ahead'
       or v_prior_receipt->>'change_set_id' is distinct from v_set.id::text
    then raise exception 'existing candidate receipt chain invalid' using errcode='PT409'; end if;
    if p_github_evidence->>'original_head_sha' is distinct from v_original_sha
       or p_github_evidence->>'old_sha' is distinct from v_original_sha
       or p_github_evidence->>'new_sha' is distinct from p_new_candidate
       or p_github_evidence->>'pr_head_sha' is distinct from p_new_candidate
       or p_github_evidence->>'pr_base' is distinct from 'main'
    then raise exception 'GitHub ancestry differs from immutable PR lineage' using errcode='PT409'; end if;

    -- No historical evaluation, specialist job, release report, deployment
    -- or human gate is modified here. A new admission cycle is mandatory.
    v_proof := p_github_evidence || jsonb_build_object(
      'change_set_id',v_set.id,
      'previous_commit',v_original_sha,
      'candidate_commit',p_new_candidate,
      'prior_candidate_commit',p_prior_candidate,
      'prior_release_report_blocked',true,
      'replayed_specialist_pass',false,
      'replayed_browser_pass',false,
      'release_authorized',false,
      'paid_model_calls',0
    );
    update public.factory_runs
      set status='ci_pending',candidate_commit=p_new_candidate,
          last_error=null,finished_at=null,
          metadata=(v_run.metadata-'specialist_lanes')||
            jsonb_build_object('postreview_candidate_reconciliation',
              jsonb_build_object('old_sha',p_prior_candidate,
                'new_sha',p_new_candidate,
                'original_head_sha',v_original_sha,
                'at',now(),'release_authorized',false))
    where id=p_run_id and status='release_policy_blocked'
      and candidate_commit=p_prior_candidate and lease_owner is null;
    if not found then raise exception 'run CAS lost' using errcode='PT409'; end if;
    update public.factory_change_sets
      set candidate_commit=p_new_candidate,
          metadata=jsonb_set(jsonb_set(
            v_set.metadata,'{integration_release_request,candidate_commit}',
            to_jsonb(p_new_candidate),false),
            '{integration_epoch_receipt,candidate_commit}',to_jsonb(p_new_candidate),false)
            ||jsonb_build_object('postreview_candidate_reconciliation',
                jsonb_build_object('old_sha',p_prior_candidate,
                  'new_sha',p_new_candidate,'at',now(),'release_authorized',false)),
          updated_at=now()
    where id=v_set.id and status='ci_pending'
      and candidate_commit=p_prior_candidate and lease_owner is null;
    if not found then raise exception 'Change Set CAS lost' using errcode='PT409'; end if;
    insert into public.factory_tool_usage(
       run_id,tool_family,operation,usage_units,estimated_cost,metadata)
    values (p_run_id,'github','reconcile_pr_candidate',1,0,v_proof);
    insert into public.factory_audit_events(
       project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
    values (v_project.id,v_task.id,p_run_id,
       'system','postreview-candidate-reconciler',
       'change_set.blocked_release_candidate.reconciled',v_proof);
    return jsonb_build_object(
        'status','ci_pending','run_id',p_run_id,'change_set_id',v_set.id,
        'previous_commit',p_prior_candidate,'original_head_sha',v_original_sha,
        'candidate_commit',p_new_candidate,
        'fresh_ci_required',true,'fresh_specialists_required',true,
        'fresh_preview_required',true,'prior_evidence_preserved',true,
        'release_authorized',false,'writes',4,'paid_model_calls',0
    );
end;
$reconcile$;

revoke all on function public.factory_reconcile_blocked_release_candidate_once_v1(
    uuid,uuid,integer,text,text,jsonb) from public,anon,authenticated;
grant execute on function public.factory_reconcile_blocked_release_candidate_once_v1(
    uuid,uuid,integer,text,text,jsonb) to service_role;
commit;
