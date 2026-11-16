-- Status-only, independently reverified rescue for a protected Preview OIDC origin mismatch.
-- A new first-party browser proof must postdate the latest failed browser evaluation. NO release, merge or model calls.
-- Requires a separate human-authorized production migration after code review.
begin;
create or replace function public.factory_resume_preview_oidc_origin_mismatch_once_v1(
 p_run_id uuid,p_candidate_commit text,p_pr_number integer,p_verified_github jsonb
) returns jsonb
language plpgsql security invoker set search_path='' as $fn$
declare
 v_set public.factory_change_sets%rowtype;
 v_run public.factory_runs%rowtype;
 v_task public.factory_tasks%rowtype;
 v_project public.factory_projects%rowtype;
 v_control record;
 v_eval record;
 v_snapshot record;
 v_url text;
begin
 if p_run_id is null or p_pr_number is null or p_pr_number<1
    or p_candidate_commit is null or p_candidate_commit !~ '^[0-9a-f]{40}$'
    or jsonb_typeof(p_verified_github) is distinct from 'object'
    or p_verified_github->>'pr_number' is distinct from p_pr_number::text
    or p_verified_github->>'head_sha' is distinct from p_candidate_commit
    or p_verified_github->>'pr_state' is distinct from 'open'
    or p_verified_github->>'draft' is distinct from 'false'
    or p_verified_github->>'merged' is distinct from 'false'
    or p_verified_github->>'vercel_state' is distinct from 'success'
    or coalesce(p_verified_github->>'factory_sha','') !~ '^[0-9a-f]{40}$'
 then raise exception 'verified GitHub identity required' using errcode='PT400'; end if;
 select * into v_set from public.factory_change_sets
 where release_run_id=p_run_id for update;
 if not found or v_set.status<>'ci_pending'
    or v_set.candidate_commit is distinct from p_candidate_commit
    or v_set.lease_owner is not null or v_set.lease_expires_at is not null
    or v_set.metadata->'integration_release_request'->>'pr_number' is distinct from p_pr_number::text
    or v_set.metadata->'integration_release_request'->>'candidate_commit' is distinct from p_candidate_commit
 then raise exception 'Change Set is not eligible' using errcode='PT409'; end if;
 select * into v_project from public.factory_projects where id=v_set.project_id and is_active=true;
 if not found or v_project.repository is distinct from p_verified_github->>'repository'
    or v_project.manifest->'preview'->>'required' is distinct from 'true'
 then raise exception 'active project and Preview policy required' using errcode='PT409'; end if;
 select state,generation into v_control from public.factory_project_execution_controls
 where project_id=v_project.id for share;
 if not found or v_control.state is distinct from 'running'
    or v_control.generation<1
    or v_set.metadata->'integration_epoch_receipt'->>'generation' is distinct from v_control.generation::text
 then raise exception 'execution epoch rejected' using errcode='PT409'; end if;
 select * into v_run from public.factory_runs where id=p_run_id for update;
 if not found or v_run.status<>'failed'
    or v_run.candidate_commit is distinct from p_candidate_commit
    or v_run.branch_name is distinct from v_set.integration_branch
    or v_run.branch_name is distinct from p_verified_github->>'head_ref'
    or v_run.lease_owner is not null or v_run.lease_expires_at is not null
    or v_run.metadata->>'change_set_id' is distinct from v_set.id::text
    or v_run.metadata->>'execution_generation' is distinct from v_control.generation::text
 then raise exception 'terminal delivery run mismatch' using errcode='PT409'; end if;
 select * into v_task from public.factory_tasks where id=v_run.task_id for update;
 if not found or v_task.status<>'failed' or v_task.project_id is distinct from v_project.id
    or v_task.id is distinct from v_set.root_task_id
 then raise exception 'root delivery task mismatch' using errcode='PT409'; end if;
 if (select count(*) from public.factory_specialist_lane_jobs j where j.run_id=p_run_id and j.required)=0
    or exists(select 1 from public.factory_specialist_lane_jobs j
      where j.run_id=p_run_id and j.required
        and (j.status<>'passed' or j.candidate_commit is distinct from p_candidate_commit))
 then raise exception 'required specialists not passed' using errcode='PT409'; end if;
 if not exists(select 1 from public.factory_evaluations e where e.run_id=p_run_id
      and e.eval_type='github_ci' and e.status='success' and e.baseline_ref=p_candidate_commit
      and e.result->>'head_sha'=p_candidate_commit and e.result->>'ci_state'='success'
      and e.result->>'pr'=p_pr_number::text)
    or not exists(select 1 from public.factory_evaluations e where e.run_id=p_run_id
      and e.eval_type='quality_gate' and e.status='success' and e.baseline_ref=p_candidate_commit
      and e.result->>'passed'='true')
 then raise exception 'exact SHA CI or quality gate missing' using errcode='PT409'; end if;
 select id,status,baseline_ref,result,created_at into v_eval
 from public.factory_evaluations where run_id=p_run_id and eval_type='browser_e2e'
 order by created_at desc,id desc limit 1;
 if not found or v_eval.status<>'failure'
    or v_eval.result->>'detail' is distinct from 'preview_application_origin_mismatch'
    or v_eval.result->'checks' is distinct from '["page_load"]'::jsonb
    or exists(select 1 from public.factory_evaluations e where e.run_id=p_run_id
       and e.eval_type='browser_e2e' and e.status='success')
    or exists(select 1 from public.factory_audit_events a where a.run_id=p_run_id
       and a.event_type='preview.oidc_origin_mismatch.browser_verified_resume')
 then raise exception 'not a bounded first-party OIDC origin incident' using errcode='PT409'; end if;
 v_url:=v_eval.baseline_ref;
 if v_url is null or v_url !~ '^https://[a-z0-9][a-z0-9-]*[.]vercel[.]app$'
    or v_eval.result->>'preview_url' is distinct from v_url
    or p_verified_github->>'preview_url' is distinct from v_url
    or not exists(select 1 from public.factory_deployments d where d.run_id=p_run_id
      and d.environment='preview' and d.status='success'
      and d.metadata->>'candidate_commit'=p_candidate_commit
      and d.metadata->>'preview_url'=v_url)
 then raise exception 'exact SHA Preview not proven' using errcode='PT409'; end if;
 -- Only accept a NEW separate successful SHA-bound Playwright witness created after
 -- THIS failure. Former PASS, provider READY, assertion, or SSO HTML is not proof.
 select s.id,s.created_at into v_snapshot from public.factory_project_state_snapshots s
 where s.project_id=v_project.id and s.run_id is null and s.observed_stage='verification'
   and s.created_at>v_eval.created_at
   and s.evidence->>'candidate_commit'=p_candidate_commit
   and s.evidence->>'target_repository'=v_project.repository
   and s.evidence->'preview'->>'url'=v_url
   and s.evidence->'preview'->>'status'='browser_verified'
   and s.evidence->'preview'->>'verifier_factory_commit'=p_verified_github->>'factory_sha'
   and coalesce(s.evidence->'preview'->>'browser_verifier_run_id','') ~ '^[1-9][0-9]{0,18}$'
   and coalesce(s.evidence->'preview'->>'browser_request_id','') ~ '^[0-9a-f-]{36}$'
   and s.source_status->>'github_target'='verified'
   and s.source_status->>'vercel_preview'='resolved'
   and s.source_status->>'browser_visual_validation'='success'
   and s.constraints->>'product_ready_inferred'='false'
   and s.constraints->>'production_merge_authorized'='false'
 order by s.created_at desc,s.id desc limit 1;
 if not found then raise exception 'independent first-party browser proof missing' using errcode='PT409'; end if;
 update public.factory_runs set status='preview_ready',finished_at=null,last_error=null
 where id=p_run_id and status='failed';
 update public.factory_tasks set status='integrated',updated_at=now()
 where id=v_task.id and status='failed';
 insert into public.factory_audit_events(
   project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
 ) values (
   v_project.id,v_task.id,p_run_id,'system','preview-oidc-origin-recovery',
   'preview.oidc_origin_mismatch.browser_verified_resume',
   jsonb_build_object('candidate_commit',p_candidate_commit,'pr_number',p_pr_number,
     'snapshot_id',v_snapshot.id,'failed_browser_eval_id',v_eval.id,
     'factory_sha',p_verified_github->>'factory_sha','original_browser_failure_preserved',true,
     'browser_e2e_result_overwritten',false,'release_authorized',false,'paid_calls',0)
 );
 return jsonb_build_object('run_id',p_run_id,'status','preview_ready',
   'candidate_commit',p_candidate_commit,'snapshot_id',v_snapshot.id,
   'original_browser_failure_preserved',true,'release_authorized',false);
end;
$fn$;
revoke all on function public.factory_resume_preview_oidc_origin_mismatch_once_v1(uuid,text,integer,jsonb)
 from public,anon,authenticated;
grant execute on function public.factory_resume_preview_oidc_origin_mismatch_once_v1(uuid,text,integer,jsonb)
 to service_role;
commit;
