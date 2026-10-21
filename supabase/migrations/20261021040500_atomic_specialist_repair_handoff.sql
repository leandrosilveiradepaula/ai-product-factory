-- Atomic specialist completion/repair and late Pause/Resume fencing.
-- Depends on 20261021030000 specialist lease and epoch migration.
-- Three existing SECURITY INVOKER functions, no added grants, policies,
-- tables, scheduled model calls, production merge or paid execution.
BEGIN;
CREATE OR REPLACE FUNCTION public.factory_enqueue_repair_from_specialist(p_job_id uuid, p_findings jsonb, p_max_cycles integer DEFAULT 3)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
 v_job public.factory_specialist_lane_jobs%rowtype;
 v_run public.factory_runs%rowtype;
 v_set public.factory_change_sets%rowtype;
 v_find jsonb;
 v_cycle integer;
 v_task_id uuid;
 v_unit_id uuid;
 v_repair_id uuid;
 v_wave integer;
 v_scopes jsonb;
 v_generation bigint;
 v_existing public.factory_repair_jobs%rowtype;
begin
 if p_max_cycles<1 or p_max_cycles>3 then raise exception 'repair max cycles must be between 1 and 3'; end if;
 if jsonb_typeof(coalesce(p_findings,'[]'::jsonb))<>'array' then raise exception 'findings must be array'; end if;
 select * into v_job from public.factory_specialist_lane_jobs where id=p_job_id for update;
 if not found then raise exception 'specialist job not found'; end if;
 -- Enforce the review's original generation under project-control locks
 -- before any branch can create a task or increment a repair cycle.
 select c.generation into v_generation
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
 if not found then raise exception 'repair source epoch revoked' using errcode='PT409'; end if;
 if v_job.status<>'failed' or v_job.findings is distinct from coalesce(p_findings,'[]'::jsonb) then
   raise exception 'repair requires completed failure with exact findings' using errcode='PT409';
 end if;
 if v_job.role not in ('security','qa') then
  return jsonb_build_object('created',false,'reason','role_not_auto_repairable');
 end if;
 select * into v_run from public.factory_runs where id=v_job.run_id;
 -- The job row is FOR UPDATE: repeat RPCs are idempotent even under race.
 select * into v_existing from public.factory_repair_jobs
 where specialist_job_id=p_job_id order by cycle asc limit 1 for update;
 if found then return jsonb_build_object(
   'created',false,'reason','already_enqueued','repair_job_id',v_existing.id,
   'task_id',v_existing.task_id,'work_unit_id',v_existing.work_unit_id,
   'cycle',v_existing.cycle,'max_cycles',v_existing.max_cycles,
   'status',v_existing.status);
 end if;
 if coalesce(v_run.metadata->>'change_set_id','')='' then
  return jsonb_build_object('created',false,'reason','no_change_set');
 end if;
 select * into v_set from public.factory_change_sets where id=(v_run.metadata->>'change_set_id')::uuid for update;
 if not found then return jsonb_build_object('created',false,'reason','change_set_not_found'); end if;
 if v_set.project_id is distinct from v_job.project_id then
   raise exception 'repair project mismatch' using errcode='PT409';
 end if;
 select count(*)+1 into v_cycle from public.factory_repair_jobs
 where change_set_id=v_set.id and source_role=v_job.role;
 if v_cycle>p_max_cycles then
  update public.factory_change_sets
  set status='blocked',metadata=metadata||jsonb_build_object('blocker','repair_cycles_exhausted','repair_source_role',v_job.role),updated_at=now()
  where id=v_set.id;
  insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  values(v_job.project_id,v_run.task_id,v_job.run_id,'system','repair-controller','repair.exhausted',
    jsonb_build_object('change_set_id',v_set.id,'source_role',v_job.role,'max_cycles',p_max_cycles));
  return jsonb_build_object('created',false,'reason','repair_cycles_exhausted','cycle',v_cycle);
 end if;
 select value into v_find from jsonb_array_elements(coalesce(p_findings,'[]'::jsonb)) limit 1;
 if v_find is null then return jsonb_build_object('created',false,'reason','no_findings'); end if;
 v_scopes=case when jsonb_typeof(v_find->'scope_keys')='array' then v_find->'scope_keys'
               when nullif(v_find->>'path','') is not null then jsonb_build_array(v_find->>'path')
               else coalesce(v_set.metadata->'integrated_files','[]'::jsonb) end;
 if jsonb_array_length(coalesce(v_scopes,'[]'::jsonb))=0 then
   update public.factory_change_sets
   set status='blocked',metadata=metadata||jsonb_build_object('blocker','repair_scope_unknown','repair_source_role',v_job.role),updated_at=now()
   where id=v_set.id;
   return jsonb_build_object('created',false,'reason','repair_scope_unknown');
 end if;
 v_wave=v_set.current_wave+1;
 insert into public.factory_tasks(project_id,parent_task_id,external_key,title,description,status,complexity,risk,acceptance_criteria,depends_on)
 values(v_job.project_id,v_set.root_task_id,'repair-'||replace(p_job_id::text,'-','')||'-'||v_cycle,
   'Repair '||v_job.role||' findings - cycle '||v_cycle,
   'Bounded repair generated from independent '||v_job.role||' findings. Fix only the recorded finding and assigned scopes.',
   'queued','medium','{}'::jsonb,jsonb_build_array(jsonb_build_object('finding',v_find,'source_role',v_job.role)),
   '[]'::jsonb)
 returning id into v_task_id;
 insert into public.factory_change_set_work_units(change_set_id,task_id,plan_task_key,agent_key,wave,status)
 values(v_set.id,v_task_id,'repair-'||v_job.role||'-'||v_cycle,'development',v_wave,'pending')
 returning id into v_unit_id;
 insert into public.factory_repair_jobs(project_id,change_set_id,source_run_id,specialist_job_id,source_role,cycle,max_cycles,
   owner_agent_key,candidate_commit,finding,write_scopes,status,task_id,work_unit_id)
 values(v_job.project_id,v_set.id,v_job.run_id,p_job_id,v_job.role,v_cycle,p_max_cycles,'development',
   v_job.candidate_commit,v_find,v_scopes,'queued',v_task_id,v_unit_id) returning id into v_repair_id;
 update public.factory_change_sets
 set status='building',current_wave=v_wave,release_run_id=null,attempt_count=0,lease_owner=null,lease_expires_at=null,
     metadata=metadata||jsonb_build_object('repair_cycle',v_cycle,'repair_source_role',v_job.role),updated_at=now()
 where id=v_set.id;
 update public.factory_runs set status='repair_pending',
   metadata=metadata||jsonb_build_object('repair_job_id',v_repair_id,'repair_cycle',v_cycle)
 where id=v_job.run_id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_job.project_id,v_task_id,v_job.run_id,'system','repair-controller','repair.queued',
   jsonb_build_object('repair_job_id',v_repair_id,'change_set_id',v_set.id,'cycle',v_cycle,'owner_agent_key','development',
     'write_scopes',v_scopes,'candidate_commit',v_job.candidate_commit));
 return jsonb_build_object('created',true,'repair_job_id',v_repair_id,'task_id',v_task_id,'work_unit_id',v_unit_id,
   'cycle',v_cycle,'max_cycles',p_max_cycles,'status','repair_pending');
end;
$function$;

CREATE OR REPLACE FUNCTION public.factory_close_repairs_after_specialist_pass(p_job_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_job public.factory_specialist_lane_jobs%rowtype;v_run public.factory_runs%rowtype;v_change_set_id uuid;v_count integer:=0;
 v_epoch bigint;
begin
 select * into v_job from public.factory_specialist_lane_jobs where id=p_job_id for update;
 if not found then raise exception 'specialist job not found'; end if;
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
 if not found then raise exception 'repair close epoch revoked' using errcode='PT409'; end if;
 if v_job.status<>'passed' or v_job.role not in ('security','qa') then
   raise exception 'repair close requires completed security or qa pass' using errcode='PT409';
 end if;
 select * into v_run from public.factory_runs where id=v_job.run_id;
 if coalesce(v_run.metadata->>'change_set_id','')='' then return jsonb_build_object('updated',0,'reason','no_change_set'); end if;
 v_change_set_id=(v_run.metadata->>'change_set_id')::uuid;
 update public.factory_repair_jobs
 set status='passed',candidate_commit=v_job.candidate_commit,updated_at=now()
 where change_set_id=v_change_set_id and project_id=v_job.project_id
   and source_role=v_job.role and status='integrated'
   and exists(select 1 from public.factory_change_sets s
     where s.id=v_change_set_id and s.project_id=v_job.project_id);
 get diagnostics v_count=row_count;
 if v_count>0 then
  insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  values(v_job.project_id,v_run.task_id,v_job.run_id,'agent',v_job.role,'repair.recheck.passed',
    jsonb_build_object('change_set_id',v_change_set_id,'source_role',v_job.role,'passed_repairs',v_count,
      'candidate_commit',v_job.candidate_commit));
 end if;
 return jsonb_build_object('updated',v_count,'status','passed','candidate_commit',v_job.candidate_commit);
end;
$function$;

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
$function$;
COMMIT;
