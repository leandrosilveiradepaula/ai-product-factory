-- Candidate migration: explicit human approval is required before applying.
-- Observe an external, verified Preview branch merge. NEVER merge or release prod.
begin;
create or replace function public.factory_observe_nonproduction_preview_merge(
 p_run_id uuid,p_pr_number integer,p_candidate_commit text,
 p_merge_sha text,p_base_ref text,p_verified_github jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare
 v_change public.factory_change_sets%rowtype;
 v_run public.factory_runs%rowtype;
 v_task public.factory_tasks%rowtype;
 v_report public.factory_release_reports%rowtype;
 v_control record;
 v_repo text;
 v_preview_url text;
 v_integration jsonb;
begin
 if p_run_id is null or p_pr_number<1
    or p_candidate_commit !~ '^[0-9a-f]{40}$'
    or p_merge_sha !~ '^[0-9a-f]{40}$'
    or p_candidate_commit=p_merge_sha
    or p_base_ref !~ '^preview/[A-Za-z0-9._/-]+$'
    or jsonb_typeof(p_verified_github) is distinct from 'object'
    or p_verified_github->>'pr_number' is distinct from p_pr_number::text
    or p_verified_github->>'candidate_commit' is distinct from p_candidate_commit
    or p_verified_github->>'head_sha' is distinct from p_candidate_commit
    or p_verified_github->>'merge_sha' is distinct from p_merge_sha
    or p_verified_github->>'base_ref' is distinct from p_base_ref
    or p_verified_github->>'merged' is distinct from 'true'
    or p_verified_github->>'merge_is_ancestor' is distinct from 'true'
    or p_verified_github->>'vercel_state' is distinct from 'success'
    or p_verified_github->>'production_released' is distinct from 'false'
    or p_verified_github->>'production_main_sha' !~ '^[0-9a-f]{40}$'
    or p_verified_github->>'production_main_sha'=p_merge_sha
    or p_verified_github->>'observed_base_tip' !~ '^[0-9a-f]{40}$'
 then raise exception 'invalid nonproduction GitHub merge evidence' using errcode='PT400';
 end if;

 select * into v_change from public.factory_change_sets
 where release_run_id=p_run_id for update;
 if not found then raise exception 'change set not found' using errcode='PT409'; end if;
 select state,generation into v_control from public.factory_project_execution_controls
 where project_id=v_change.project_id for share;
 if not found or v_control.state is distinct from 'running'
    or v_change.metadata->'integration_epoch_receipt'->>'generation'
       is distinct from v_control.generation::text
 then raise exception 'project execution control revoked' using errcode='PT409'; end if;
 select * into v_run from public.factory_runs where id=p_run_id for update;
 if not found or v_run.candidate_commit is distinct from p_candidate_commit
    or v_run.branch_name is distinct from v_change.integration_branch
    or v_change.candidate_commit is distinct from p_candidate_commit
 then raise exception 'run candidate or branch mismatch' using errcode='PT409'; end if;

 -- Repeating the same observation is safe, but not a new release.
 if v_run.status='integrated' and v_change.status='completed'
    and v_run.metadata->'nonproduction_integration'->>'merge_sha'=p_merge_sha
    and v_run.metadata->'nonproduction_integration'->>'base_ref'=p_base_ref
    and v_run.metadata->'nonproduction_integration'->>'candidate_commit'=p_candidate_commit
    and exists(select 1 from public.factory_audit_events e
       where e.run_id=p_run_id and e.event_type='change_set.nonproduction_merge.observed'
         and e.payload->>'merge_sha'=p_merge_sha)
 then
  return jsonb_build_object('run_id',p_run_id,'status','integrated','merge_sha',p_merge_sha,
       'release_completed',false,'idempotent',true);
 end if;
 if v_run.status<>'awaiting_release' or v_change.status<>'ci_pending'
    or v_change.metadata->'integration_release_request'->>'pr_number'
       is distinct from p_pr_number::text
    or v_change.metadata->'integration_release_request'->>'branch'
       is distinct from v_run.branch_name
    or v_change.metadata->'integration_release_request'->>'candidate_commit'
       is distinct from p_candidate_commit
    or p_verified_github->>'head_ref' is distinct from v_run.branch_name
 then raise exception 'change set release-readiness revoked' using errcode='PT409'; end if;
 select * into v_task from public.factory_tasks where id=v_run.task_id for update;
 if not found or v_task.project_id is distinct from v_change.project_id
    or v_task.status<>'integrated'
    or coalesce(v_task.risk->>'destructive_data_change','false')='true'
    or coalesce(v_task.risk->>'expands_sensitive_access','false')='true'
    or coalesce(v_task.risk->>'material_requirement_change','false')='true'
    or coalesce(v_task.risk->>'new_paid_service','false')='true'
 then raise exception 'unsafe nonproduction integration task' using errcode='PT409'; end if;
 select repository into v_repo from public.factory_projects where id=v_change.project_id;
 if v_repo is null or p_verified_github->>'repository' is distinct from v_repo
 then raise exception 'nonproduction GitHub repository mismatch' using errcode='PT409'; end if;

 select * into v_report from public.factory_release_reports
 where run_id=p_run_id order by created_at desc limit 1 for update;
 if not found or v_report.status<>'ready_for_human_release'
    or v_report.candidate_commit is distinct from p_candidate_commit
    or v_report.report->'blockers' is distinct from '[]'::jsonb
 then raise exception 'exact candidate readiness report not green' using errcode='PT409'; end if;
 if not exists(select 1 from public.factory_evaluations e
    where e.run_id=p_run_id and e.eval_type='github_ci'
      and e.status='success' and e.baseline_ref=p_candidate_commit)
    or not exists(select 1 from public.factory_evaluations e
    where e.run_id=p_run_id and e.eval_type='quality_gate'
      and e.status='success' and e.baseline_ref=p_candidate_commit
      and e.result->>'passed'='true')
    or not exists(select 1 from public.factory_specialist_lane_jobs j
      where j.run_id=p_run_id and j.required)
    or exists(select 1 from public.factory_specialist_lane_jobs j
      where j.run_id=p_run_id and j.required
        and (j.status<>'passed' or j.candidate_commit is distinct from p_candidate_commit))
 then raise exception 'CI, quality or specialist evidence missing' using errcode='PT409'; end if;
 select u.metadata->>'preview_url' into v_preview_url
 from public.factory_tool_usage u
 where u.run_id=p_run_id and u.operation='verified_preview_awaiting_human_merge'
   and u.metadata->>'pr'=p_pr_number::text
   and u.metadata->>'head_sha'=p_candidate_commit
 order by u.created_at desc limit 1;
 if nullif(v_preview_url,'') is null
    or not exists(select 1 from public.factory_evaluations e
       where e.run_id=p_run_id and e.eval_type='browser_e2e'
       and e.status='success' and e.baseline_ref=v_preview_url)
    or not exists(select 1 from public.factory_deployments d
       where d.run_id=p_run_id and d.environment='preview' and d.status='success'
       and d.metadata->>'candidate_commit'=p_candidate_commit
       and d.metadata->>'preview_url'=v_preview_url)
    or exists(select 1 from public.factory_evaluations e
       where e.run_id=p_run_id and e.eval_type='human_release' and e.status='passed')
 then raise exception 'preview evidence missing or production release already present'
 using errcode='PT409'; end if;

 v_integration=p_verified_github||jsonb_build_object(
    'environment','preview','preview_url',v_preview_url,
    'production_release_completed',false,'observed_at',now());
 update public.factory_runs
 set status='integrated',finished_at=now(),
     metadata=jsonb_set(coalesce(v_run.metadata,'{}'::jsonb),
       '{nonproduction_integration}',v_integration,true)
 where id=p_run_id;
 update public.factory_change_sets
 set status='completed',updated_at=now(),
     metadata=jsonb_set(coalesce(v_change.metadata,'{}'::jsonb),
       '{nonproduction_integration}',v_integration,true)
 where id=v_change.id;
 -- The existing readiness report must NOT be mistaken for production approval.
 update public.factory_release_reports
 set status='blocked',updated_at=now(),
     report=coalesce(v_report.report,'{}'::jsonb)||jsonb_build_object(
       'release_state','nonproduction_integrated',
       'blockers',jsonb_build_array('production requires a separate verified main-target release candidate'),
       'nonproduction_integration',v_integration)
 where id=v_report.id;
 perform public.factory_release_agent_scope_locks(p_run_id);
 insert into public.factory_tool_usage(
   run_id,tool_family,operation,usage_units,estimated_cost,metadata
 ) values(p_run_id,'github','nonproduction_merge_observed',1,0,v_integration);
 insert into public.factory_audit_events(
   project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
 ) values(v_change.project_id,v_run.task_id,p_run_id,'system','nonproduction-release-observer',
   'change_set.nonproduction_merge.observed',v_integration);
 return jsonb_build_object('run_id',p_run_id,'change_set_id',v_change.id,
   'status','integrated','merge_sha',p_merge_sha,'release_completed',false,
   'idempotent',false,'report_status','blocked');
end;
$fn$;
revoke all on function public.factory_observe_nonproduction_preview_merge(uuid,integer,text,text,text,jsonb)
 from public,anon,authenticated;
grant execute on function public.factory_observe_nonproduction_preview_merge(uuid,integer,text,text,text,jsonb)
 to service_role;
commit;
