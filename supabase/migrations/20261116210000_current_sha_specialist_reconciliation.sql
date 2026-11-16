-- Fail-closed multi-SHA specialist settlement.
-- The original failed specialist rows and evaluations remain immutable.
-- Every status decision is scoped to the exact reviewed candidate SHA.
begin;
CREATE OR REPLACE FUNCTION public.factory_complete_specialist_lane(p_job_id uuid, p_status text, p_findings jsonb DEFAULT '[]'::jsonb, p_evidence jsonb DEFAULT '{}'::jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_job public.factory_specialist_lane_jobs%rowtype;v_remaining integer;v_failed integer;v_run_status text;
 v_epoch bigint;
 v_repair jsonb:=null;
 v_recheck jsonb:=null;
begin
 if p_status not in ('passed','failed','blocked') then raise exception 'invalid specialist completion status'; end if;
 if jsonb_typeof(coalesce(p_findings,'[]'::jsonb))<>'array' then raise exception 'findings must be array'; end if;
 if jsonb_typeof(coalesce(p_evidence,'{}'::jsonb))<>'object' then raise exception 'evidence must be object'; end if;

 select * into v_job from public.factory_specialist_lane_jobs where id=p_job_id for update;
 if not found then raise exception 'specialist lane job not found'; end if;
 if v_job.status<>'claimed' then raise exception 'specialist lane job is not claimed' using errcode='PT409'; end if;
 -- The same transaction holds the project-control row until all evaluations,
 -- run status and audit writes commit. A racing Pause waits; a prior Pause
 -- or resumed generation revocation prevents every late completion effect.
 select c.generation into v_epoch
 from public.factory_project_execution_controls c
 join public.factory_projects p on p.id=c.project_id
 join public.factory_runs r on r.id=v_job.run_id
 join public.factory_tasks t on t.id=r.task_id
 where c.project_id=v_job.project_id and t.project_id=v_job.project_id
   and p.is_active=true and c.state='running' and c.generation>0
   and r.metadata->>'execution_generation'=c.generation::text
   and r.candidate_commit=v_job.candidate_commit
   and v_job.evidence->>'_factory_epoch'=c.generation::text
 for share of c,p;
 if not found then
   raise exception 'specialist completion revoked by project control or execution epoch'
   using errcode='PT409';
 end if;
 if v_job.lease_owner is null or v_job.lease_expires_at is null
    or v_job.lease_expires_at<=now()
    or nullif(v_job.evidence->>'_factory_claim_token','') is null
    or p_evidence->>'_factory_claim_token' is distinct from
       v_job.evidence->>'_factory_claim_token' then
   raise exception 'specialist completion has expired or mismatched claim token'
   using errcode='PT409';
 end if;

 update public.factory_specialist_lane_jobs
 set status=p_status,findings=coalesce(p_findings,'[]'::jsonb),
     evidence=(coalesce(p_evidence,'{}'::jsonb)-'_factory_claim_token')||jsonb_build_object('_factory_epoch',v_epoch),
     completed_at=now(),updated_at=now(),lease_expires_at=null
 where id=p_job_id;

 insert into public.factory_evaluations(run_id,eval_type,status,baseline_ref,result)
 values(v_job.run_id,'specialist_'||v_job.role,p_status,v_job.candidate_commit,
   jsonb_build_object('job_id',p_job_id,'role',v_job.role,'findings',coalesce(p_findings,'[]'::jsonb),
     'evidence',coalesce(p_evidence,'{}'::jsonb)-'_factory_claim_token'));

 select count(*) into v_failed from public.factory_specialist_lane_jobs
 where run_id=v_job.run_id and candidate_commit=v_job.candidate_commit and required and status in ('failed','blocked');
 select count(*) into v_remaining from public.factory_specialist_lane_jobs
 where run_id=v_job.run_id and candidate_commit=v_job.candidate_commit and required and status in ('queued','claimed');

 if v_failed>0 then
   v_run_status:='specialist_review_failed';
 elsif v_remaining=0 then
   v_run_status:='preview_ready';
 else
   v_run_status:='specialist_review_pending';
 end if;
 update public.factory_runs set status=v_run_status where id=v_job.run_id;

 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 select v_job.project_id,r.task_id,v_job.run_id,'agent',v_job.role,'specialist.lane.completed',
        jsonb_build_object('job_id',p_job_id,'status',p_status,'candidate_commit',v_job.candidate_commit,
          'findings_count',jsonb_array_length(coalesce(p_findings,'[]'::jsonb)),'run_status',v_run_status)
 from public.factory_runs r where r.id=v_job.run_id;

 -- Completion plus repair/recheck is one transaction: no Pause gap,
 -- lost-response retry or crash can materialize an extra work unit.
 if v_job.role in ('security','qa') and p_status='failed' then
   v_repair:=public.factory_enqueue_repair_from_specialist(
     p_job_id,coalesce(p_findings,'[]'::jsonb),3);
   if v_repair->>'created'='true' then v_run_status:='repair_pending'; end if;
 elsif v_job.role in ('security','qa') and p_status='passed' then
   v_recheck:=public.factory_close_repairs_after_specialist_pass(p_job_id);
 end if;
 return jsonb_build_object(
   'job_id',p_job_id,'status',p_status,'run_status',v_run_status,
   'post_review_applied',true,'repair',v_repair,'repair_recheck',v_recheck);
end;
$function$


-- Explicit reconciliation for previously completed, immutable current-SHA
-- reviews which were marked failed solely because an old SHA failed.
create or replace function public.factory_reconcile_passed_current_sha_specialists_v1(
    p_run_id uuid, p_expected_sha text
) returns jsonb
language plpgsql security invoker set search_path='' as $reconcile$
declare
    v_run public.factory_runs%rowtype;
    v_change_set public.factory_change_sets%rowtype;
    v_project_id uuid;
    v_generation bigint;
    v_current_count integer;
    v_required_count integer;
    v_passed_count integer;
    v_roles_count integer;
    v_stale_fail_count integer;
    v_marker jsonb;
begin
    if p_run_id is null or p_expected_sha !~ '^[a-f0-9]{40}$'
    then
        raise exception 'invalid exact SHA review identity' using errcode='PT400';
    end if;

    select r.* into v_run from public.factory_runs r
    where r.id=p_run_id for update;
    if not found or v_run.status is distinct from 'specialist_review_failed'
       or v_run.candidate_commit is distinct from p_expected_sha
       or v_run.metadata->>'source' is distinct from 'change-set'
       or v_run.metadata->'specialist_lanes'->>'required' is distinct from 'true'
       or v_run.metadata->'specialist_lanes'->>'candidate_commit' is distinct from p_expected_sha
       or v_run.lease_owner is not null or v_run.lease_expires_at is not null
    then
        raise exception 'run no longer in exact SHA historical review failure' using errcode='PT409';
    end if;
    select t.project_id into v_project_id
    from public.factory_tasks t where t.id=v_run.task_id;
    if not found then
        raise exception 'missing original run task' using errcode='PT409';
    end if;
    select c.generation into v_generation
    from public.factory_project_execution_controls c
    join public.factory_projects p on p.id=c.project_id
    where c.project_id=v_project_id and c.state='running'
      and c.generation>0 and p.is_active=true
    for share of c,p;
    if not found
      or v_run.metadata->>'execution_generation' is distinct from v_generation::text
    then
       raise exception 'project epoch revoked before review reconciliation' using errcode='PT409';
    end if;
    select * into v_change_set from public.factory_change_sets c
    where c.release_run_id=p_run_id and c.project_id=v_project_id
      and c.status='ci_pending' and c.candidate_commit=p_expected_sha
    for update;
    if not found or v_change_set.lease_owner is not null
      or v_change_set.lease_expires_at is not null
      or v_change_set.integration_branch in ('main','master')
      or v_run.branch_name is distinct from v_change_set.integration_branch
      or v_run.metadata->>'change_set_id' is distinct from v_change_set.id::text
    then
       raise exception 'change set no longer awaiting exact nonproduction candidate' using errcode='PT409';
    end if;
    -- Require three and only three independent, completed reviews at the
    -- current SHA, each with its own evidence and exactly one role.
    select count(*),
           count(*) filter(where j.required),
           count(*) filter(where j.required and j.status='passed'
                and j.completed_at is not null
                and j.lease_owner is null and j.lease_expires_at is null
                and j.evidence->>'_factory_epoch'=v_generation::text),
           count(distinct j.role) filter(where j.required and j.status='passed'
                and j.role in ('security','qa','operations'))
      into v_current_count,v_required_count,v_passed_count,v_roles_count
    from public.factory_specialist_lane_jobs j
    where j.run_id=p_run_id and j.candidate_commit=p_expected_sha;
    if v_current_count<>3 or v_required_count<>3
       or v_passed_count<>3 or v_roles_count<>3
    then
       raise exception 'current SHA still lacks independent specialist PASS proofs'
       using errcode='PT409';
    end if;

    -- Must be a genuine historical-SHA contamination, not a shortcut
    -- around a current-SHA failure. Old outcomes stay recorded unchanged.
    select count(*) into v_stale_fail_count
    from public.factory_specialist_lane_jobs j
    where j.run_id=p_run_id and j.candidate_commit<>p_expected_sha
      and j.required and j.status in ('failed','blocked');
    if v_stale_fail_count=0 then
       raise exception 'no historical SHA failure to reconcile'
       using errcode='PT409';
    end if;
    if exists(select 1 from public.factory_repair_jobs j
        where j.source_run_id=p_run_id and j.status in ('queued','claimed','running','blocked'))
    then raise exception 'unfinished repair cannot be bypassed' using errcode='PT409';
    end if;
    v_marker=jsonb_build_object(
        'run_id',p_run_id,'candidate_sha',p_expected_sha,
        'historical_failed_rows',v_stale_fail_count,
        'reviewed_roles',jsonb_build_array('security','qa','operations'),
        'release_authorized',false);
    update public.factory_runs
      set status='preview_ready',
          metadata=metadata||jsonb_build_object(
             'current_sha_specialist_reconciliation_v1',v_marker||jsonb_build_object('recorded_at',now()))
    where id=p_run_id and status='specialist_review_failed'
      and candidate_commit=p_expected_sha;
    if not found then raise exception 'stale run review reconciliation' using errcode='PT409'; end if;
    insert into public.factory_audit_events(
       project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
    values(v_project_id,v_run.task_id,p_run_id,'system',
       'exact-sha-specialist-reconciliation',
       'specialist.current_sha_passed.reconciled',
       v_marker||jsonb_build_object('change_set_id',v_change_set.id,
          'old_evidence_preserved',true,'new_preview_required',true,
          'production_merge_permitted',false,'paid_calls',0));
    return jsonb_build_object(
       'status','preview_ready','run_id',p_run_id,
       'candidate_commit',p_expected_sha,'old_evidence_preserved',true,
       'new_preview_required',true,'release_authorized',false);
end;
$reconcile$;
revoke all on function public.factory_reconcile_passed_current_sha_specialists_v1(uuid,text)
    from public,anon,authenticated;
grant execute on function public.factory_reconcile_passed_current_sha_specialists_v1(uuid,text)
    to service_role;
commit;
