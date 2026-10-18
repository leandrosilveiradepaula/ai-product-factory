-- Privileged operator recovery of a browser infrastructure failure.
-- Review and authorize explicitly before applying in the live Control Plane.
begin;
create or replace function public.factory_resume_preview_browser_infrastructure_failure(
 p_run_id uuid,p_candidate_commit text,p_pr_number integer,p_verified_github jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare
 v_run public.factory_runs%rowtype;
 v_set public.factory_change_sets%rowtype;
 v_task public.factory_tasks%rowtype;
 v_control record;
 v_eval record;
 v_url text;
begin
 if p_run_id is null or p_pr_number<1 or p_candidate_commit !~ '^[0-9a-f]{40}$'
    or jsonb_typeof(p_verified_github) is distinct from 'object'
    or p_verified_github->>'pr_number' is distinct from p_pr_number::text
    or p_verified_github->>'head_sha' is distinct from p_candidate_commit
    or p_verified_github->>'pr_state' is distinct from 'open'
    or p_verified_github->>'merged' is distinct from 'false'
    or p_verified_github->>'vercel_state' is distinct from 'success'
 then raise exception 'verified GitHub evidence required' using errcode='PT400';
 end if;
 select * into v_set from public.factory_change_sets
 where release_run_id=p_run_id for update;
 if not found or v_set.status<>'ci_pending'
    or v_set.candidate_commit is distinct from p_candidate_commit
    or v_set.metadata->'integration_release_request'->>'pr_number' is distinct from p_pr_number::text
 then raise exception 'change set not eligible for recovery' using errcode='PT409';
 end if;
 select state,generation into v_control from public.factory_project_execution_controls
 where project_id=v_set.project_id for share;
 if not found or v_control.state is distinct from 'running'
    or v_set.metadata->'integration_epoch_receipt'->>'generation'
       is distinct from v_control.generation::text
 then raise exception 'project execution control does not permit recovery' using errcode='PT409';
 end if;
 select * into v_run from public.factory_runs where id=p_run_id for update;
 if not found or v_run.status<>'failed'
    or v_run.candidate_commit is distinct from p_candidate_commit
    or v_run.branch_name is distinct from v_set.integration_branch
 then raise exception 'run not eligible for recovery' using errcode='PT409';
 end if;
 select * into v_task from public.factory_tasks where id=v_run.task_id for update;
 if not found or v_task.status<>'failed'
    or v_task.project_id is distinct from v_set.project_id
 then raise exception 'task not eligible for recovery' using errcode='PT409';
 end if;
 if (select count(*) from public.factory_specialist_lane_jobs j
     where j.run_id=p_run_id and j.required)=0
    or exists(select 1 from public.factory_specialist_lane_jobs j
      where j.run_id=p_run_id and j.required
        and (j.status<>'passed' or j.candidate_commit is distinct from p_candidate_commit))
 then raise exception 'required specialist lanes are not all passed' using errcode='PT409';
 end if;
 if not exists (select 1 from public.factory_evaluations e
      where e.run_id=p_run_id and e.eval_type='quality_gate'
        and e.status='success' and e.baseline_ref=p_candidate_commit
        and e.result->>'passed'='true')
 then raise exception 'exact candidate quality gate missing' using errcode='PT409';
 end if;
 select e.id,e.status,e.baseline_ref,e.result into v_eval
 from public.factory_evaluations e
 where e.run_id=p_run_id and e.eval_type='browser_e2e'
 order by e.created_at desc limit 1;
 if not found or v_eval.status<>'failure'
    or coalesce(v_eval.result->>'detail','')
       not like '%Executable doesn''t exist at %chromium_headless_shell%'
 then raise exception 'browser failure is not the verified missing-executable incident'
 using errcode='PT409';
 end if;
 v_url:=v_eval.baseline_ref;
 if nullif(v_url,'') is null
    or v_url is distinct from p_verified_github->>'preview_url'
    or not exists(select 1 from public.factory_deployments d
      where d.run_id=p_run_id and d.environment='preview'
       and d.status='success'
       and d.metadata->>'candidate_commit'=p_candidate_commit
       and d.metadata->>'preview_url'=v_url)
    or exists(select 1 from public.factory_evaluations e
       where e.run_id=p_run_id and e.eval_type='browser_e2e'
         and e.status='success')
 then raise exception 'preview deployment evidence does not match exact failed browser evidence'
 using errcode='PT409';
 end if;
 update public.factory_runs
 set status='preview_ready',finished_at=null,last_error=null
 where id=p_run_id;
 update public.factory_tasks set status='integrated',updated_at=now()
 where id=v_task.id;
 insert into public.factory_audit_events(
   project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
 ) values(
   v_set.project_id,v_task.id,p_run_id,'system','preview-browser-recovery',
   'preview.browser_infrastructure_failure.resumed',
   p_verified_github||jsonb_build_object(
     'candidate_commit',p_candidate_commit,'browser_eval_id',v_eval.id,
     'reason','missing pinned Chrome executable in sanitized browser environment')
 );
 return jsonb_build_object(
   'run_id',p_run_id,'status','preview_ready','candidate_commit',p_candidate_commit,
   'original_browser_failure_preserved',true,'preview_url',v_url);
end;
$fn$;
revoke all on function public.factory_resume_preview_browser_infrastructure_failure(uuid,text,integer,jsonb)
 from public,anon,authenticated;
grant execute on function public.factory_resume_preview_browser_infrastructure_failure(uuid,text,integer,jsonb)
 to service_role;
commit;
