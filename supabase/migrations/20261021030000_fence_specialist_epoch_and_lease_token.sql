-- Fail-closed specialist execution epoch and claim-token fencing (2026-10-21).
-- Four existing SECURITY INVOKER functions; no new grants, table, RLS policy,
-- paid agent or autonomous merge. The run's original epoch is pinned in the
-- specialist job's existing evidence JSON; recovery quarantines old epochs.
-- Each claim has a fresh token, so a stale worker cannot complete a re-claim.
-- The completion transaction holds the project control shared lock through
-- evaluation, run status and audit updates: operator Pause/Stop cannot race it.
BEGIN;
CREATE OR REPLACE FUNCTION public.factory_enqueue_specialist_lanes(p_run_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
 v_run public.factory_runs%rowtype;
 v_project_id uuid;
 v_plan jsonb;
 v_role text;
 v_roles text[]:=array[]::text[];
 v_count integer:=0;
 v_epoch bigint;
begin
 select r.* into v_run from public.factory_runs r where r.id=p_run_id for update;
 if not found then raise exception 'run not found'; end if;
 if nullif(v_run.candidate_commit,'') is null then raise exception 'candidate commit required'; end if;
 select t.project_id into v_project_id from public.factory_tasks t where t.id=v_run.task_id;
 perform public.factory_assert_project_running(v_project_id);
 select c.generation into v_epoch from public.factory_project_execution_controls c
 join public.factory_projects p on p.id=c.project_id
 where c.project_id=v_project_id and c.state='running' and c.generation>0
   and p.is_active=true for share of c,p;
 if not found or v_run.metadata->>'execution_generation' is distinct from v_epoch::text then
   raise exception 'specialist enqueue requires current run execution epoch' using errcode='PT409';
 end if;
 select plan into v_plan
 from public.factory_execution_team_plans
 where project_id=v_project_id and status='ready'
 order by version desc limit 1;
 if v_plan is null then raise exception 'ready execution team plan required'; end if;

 for v_role in
   select distinct role from (
     select x->>'role' role
     from jsonb_array_elements(coalesce(v_plan->'selected_agents','[]'::jsonb)) x
     where x->>'role' in ('security','qa','operations')
     union all
     select x->>'role' role
     from jsonb_array_elements(coalesce(v_plan->'advisory_specialist_lanes','[]'::jsonb)) x
     where x->>'role' in ('security','qa','operations')
   ) q
 loop
   v_roles:=array_append(v_roles,v_role);
   insert into public.factory_specialist_lane_jobs(run_id,project_id,role,candidate_commit,status,required,evidence)
   values(p_run_id,v_project_id,v_role,v_run.candidate_commit,'queued',true,
     jsonb_build_object('_factory_epoch',v_epoch))
   on conflict(run_id,role,candidate_commit) do nothing;
   if found then v_count:=v_count+1; end if;
 end loop;

 if coalesce(array_length(v_roles,1),0)=0 then
   update public.factory_runs set status='preview_ready',
     metadata=metadata||jsonb_build_object('specialist_lanes',jsonb_build_object('required',false,'roles','[]'::jsonb))
   where id=p_run_id;
 else
   update public.factory_runs set status='specialist_review_pending',
     metadata=metadata||jsonb_build_object('specialist_lanes',jsonb_build_object('required',true,'roles',to_jsonb(v_roles),'candidate_commit',v_run.candidate_commit))
   where id=p_run_id;
 end if;

 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 select v_project_id,r.task_id,p_run_id,'system','specialist-lane-router','specialist.lanes.enqueued',
        jsonb_build_object('roles',to_jsonb(v_roles),'created_jobs',v_count,'candidate_commit',v_run.candidate_commit)
 from public.factory_runs r where r.id=p_run_id;

 return jsonb_build_object('run_id',p_run_id,'roles',to_jsonb(v_roles),'created_jobs',v_count,
   'status',case when coalesce(array_length(v_roles,1),0)=0 then 'preview_ready' else 'specialist_review_pending' end);
end;
$function$;

CREATE OR REPLACE FUNCTION public.factory_claim_specialist_lane(p_role text, p_worker_id text, p_lease_seconds integer DEFAULT 600)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_job public.factory_specialist_lane_jobs%rowtype;v_project public.factory_projects%rowtype;v_run public.factory_runs%rowtype;
 v_epoch bigint;
 v_token text;
begin
 if p_role not in ('security','qa','operations') then raise exception 'invalid specialist role'; end if;
 if nullif(btrim(p_worker_id),'') is null then raise exception 'worker id required'; end if;
 if p_lease_seconds<60 or p_lease_seconds>1800 then raise exception 'invalid lease'; end if;

 select * into v_job
 from public.factory_specialist_lane_jobs j
 where j.role=p_role
   and exists(select 1 from public.factory_projects p
       join public.factory_project_execution_controls c on c.project_id=p.id
       where p.id=j.project_id and p.is_active=true and c.state='running' and c.generation>0
         and j.evidence->>'_factory_epoch'=c.generation::text
         and exists (
           select 1 from public.factory_runs r
           join public.factory_tasks t on t.id=r.task_id
           where r.id=j.run_id and t.project_id=j.project_id
             and r.metadata->>'execution_generation'=c.generation::text
             and r.candidate_commit=j.candidate_commit
         ) for share of c,p skip locked)
   and attempt_count < 3
   and (
     status='queued'
     or (status='claimed' and lease_expires_at<=now())
   )
 order by created_at
 for update skip locked
 limit 1;
 if v_job.id is null then return null; end if;
 perform public.factory_assert_project_running(v_job.project_id);
 select c.generation into v_epoch from public.factory_project_execution_controls c
 join public.factory_projects p on p.id=c.project_id
 where c.project_id=v_job.project_id and c.state='running' and c.generation>0
   and p.is_active=true for share of c,p;
 if not found or v_job.evidence->>'_factory_epoch' is distinct from v_epoch::text then
   raise exception 'specialist job belongs to revoked execution epoch' using errcode='PT409';
 end if;

 select * into v_run from public.factory_runs where id=v_job.run_id;
 if v_run.metadata->>'execution_generation' is distinct from v_epoch::text then
   raise exception 'specialist run belongs to revoked execution epoch' using errcode='PT409';
 end if;
 if v_run.candidate_commit is distinct from v_job.candidate_commit then
   update public.factory_specialist_lane_jobs set status='blocked',completed_at=now(),updated_at=now(),
     findings=jsonb_build_array(jsonb_build_object('code','candidate_commit_mismatch','severity','critical'))
   where id=v_job.id;
   return null;
 end if;
 select * into v_project from public.factory_projects where id=v_job.project_id;

 v_token:=gen_random_uuid()::text;
 update public.factory_specialist_lane_jobs
 set status='claimed',lease_owner=p_worker_id,lease_expires_at=now()+make_interval(secs=>p_lease_seconds),
     attempt_count=attempt_count+1,updated_at=now(),
     evidence=coalesce(evidence,'{}'::jsonb)||jsonb_build_object('_factory_claim_token',v_token)
 where id=v_job.id;

 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 select v_job.project_id,r.task_id,v_job.run_id,'agent',p_role,'specialist.lane.claimed',
        jsonb_build_object('job_id',v_job.id,'candidate_commit',v_job.candidate_commit,'worker_id',p_worker_id)
 from public.factory_runs r where r.id=v_job.run_id;

 return jsonb_build_object(
   'job_id',v_job.id,'run_id',v_job.run_id,'project_key',v_project.project_key,'repository',v_project.repository,
   'role',v_job.role,'candidate_commit',v_job.candidate_commit,'manifest',v_project.manifest,
   'claim_token',v_token,'execution_generation',v_epoch
 );
end;
$function$;

CREATE OR REPLACE FUNCTION public.factory_complete_specialist_lane(p_job_id uuid, p_status text, p_findings jsonb DEFAULT '[]'::jsonb, p_evidence jsonb DEFAULT '{}'::jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_job public.factory_specialist_lane_jobs%rowtype;v_remaining integer;v_failed integer;v_run_status text;
 v_epoch bigint;
begin
 if p_status not in ('passed','failed','blocked') then raise exception 'invalid specialist completion status'; end if;
 if jsonb_typeof(coalesce(p_findings,'[]'::jsonb))<>'array' then raise exception 'findings must be array'; end if;
 if jsonb_typeof(coalesce(p_evidence,'{}'::jsonb))<>'object' then raise exception 'evidence must be object'; end if;

 select * into v_job from public.factory_specialist_lane_jobs where id=p_job_id for update;
 if not found then raise exception 'specialist lane job not found'; end if;
 if v_job.status<>'claimed' then raise exception 'specialist lane job is not claimed'; end if;
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
 where run_id=v_job.run_id and required and status in ('failed','blocked');
 select count(*) into v_remaining from public.factory_specialist_lane_jobs
 where run_id=v_job.run_id and required and status in ('queued','claimed');

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

 return jsonb_build_object('job_id',p_job_id,'status',p_status,'run_status',v_run_status);
end;
$function$;

CREATE OR REPLACE FUNCTION public.factory_recover_specialist_lanes(p_max_attempts integer DEFAULT 3)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_requeued integer:=0;v_blocked integer:=0;v_quarantined integer:=0;
begin
 if p_max_attempts<1 or p_max_attempts>10 then raise exception 'invalid max attempts'; end if;
  perform 1 from public.factory_project_execution_controls c
  join public.factory_projects p on p.id=c.project_id
  where c.state='running' and c.generation>0 and p.is_active=true
  order by c.project_id for share of c,p skip locked;

 -- Quarantine a stale queued or claimed job rather than re-running external
 -- specialist checks under a newer project generation. Legacy/unmarked
 -- jobs fail closed until an operator explicitly reconciles provenance.
 with candidates as (
   select j.id
   from public.factory_specialist_lane_jobs j
   join public.factory_runs r on r.id=j.run_id
   join public.factory_tasks t on t.id=r.task_id and t.project_id=j.project_id
   join public.factory_projects p on p.id=j.project_id and p.is_active=true
   join public.factory_project_execution_controls c on c.project_id=p.id
   where c.state='running' and c.generation>0
     and j.status in ('queued','claimed')
     and (j.evidence->>'_factory_epoch' is distinct from c.generation::text
          or r.metadata->>'execution_generation' is distinct from c.generation::text)
   for update of j skip locked
   for share of c,p skip locked
 ), blocked as (
   update public.factory_specialist_lane_jobs j
   set status='blocked',lease_owner=null,lease_expires_at=null,
       completed_at=now(),updated_at=now(),
       findings=jsonb_build_array(jsonb_build_object(
         'code','specialist_execution_epoch_revoked','severity','critical',
         'message','specialist review requires operator reconciliation'))
   from candidates x where j.id=x.id
   returning j.id,j.project_id,j.run_id
 )
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 select b.project_id,r.task_id,b.run_id,'system','specialist-recovery',
       'specialist.lane.epoch_quarantined',
       jsonb_build_object('job_id',b.id,'automatic_replay',false)
 from blocked b join public.factory_runs r on r.id=b.run_id;
 get diagnostics v_quarantined=row_count;

 update public.factory_specialist_lane_jobs
 set status='queued',lease_owner=null,lease_expires_at=null,updated_at=now()
 where status='claimed' and lease_expires_at<=now() and attempt_count<p_max_attempts
   and exists(select 1 from public.factory_projects p
     join public.factory_project_execution_controls c on c.project_id=p.id
     join public.factory_runs r on r.id=public.factory_specialist_lane_jobs.run_id
     join public.factory_tasks t on t.id=r.task_id
     where p.id=public.factory_specialist_lane_jobs.project_id
       and t.project_id=p.id and p.is_active=true and c.state='running'
       and c.generation>0
       and public.factory_specialist_lane_jobs.evidence->>'_factory_epoch'=c.generation::text
       and r.metadata->>'execution_generation'=c.generation::text
       for share of c,p skip locked);
 get diagnostics v_requeued=row_count;

 update public.factory_specialist_lane_jobs
 set status='blocked',lease_owner=null,lease_expires_at=null,completed_at=now(),updated_at=now(),
     findings=case when findings='[]'::jsonb then jsonb_build_array(jsonb_build_object(
       'code','specialist_retry_exhausted','severity','critical','message','specialist lane exhausted retry attempts'
     )) else findings end
 where status='claimed' and lease_expires_at<=now() and attempt_count>=p_max_attempts
   and exists(select 1 from public.factory_projects p
     join public.factory_project_execution_controls c on c.project_id=p.id
     join public.factory_runs r on r.id=public.factory_specialist_lane_jobs.run_id
     join public.factory_tasks t on t.id=r.task_id
     where p.id=public.factory_specialist_lane_jobs.project_id
       and t.project_id=p.id and p.is_active=true and c.state='running'
       and c.generation>0
       and public.factory_specialist_lane_jobs.evidence->>'_factory_epoch'=c.generation::text
       and r.metadata->>'execution_generation'=c.generation::text
       for share of c,p skip locked);
 get diagnostics v_blocked=row_count;
 v_blocked:=v_blocked+v_quarantined;

 update public.factory_runs r
 set status='specialist_review_failed'
 where exists(
   select 1 from public.factory_specialist_lane_jobs j
   where j.run_id=r.id and j.required and j.status='blocked'
 ) and exists(select 1 from public.factory_tasks t where t.id=r.task_id and exists(select 1 from public.factory_projects p join public.factory_project_execution_controls c on c.project_id=p.id where p.id=t.project_id and p.is_active=true and c.state='running' and c.generation>0 for share of c,p));

 return jsonb_build_object('requeued',v_requeued,'blocked',v_blocked);
end;
$function$;
COMMIT;
