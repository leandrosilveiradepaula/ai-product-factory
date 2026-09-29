create table if not exists public.factory_specialist_lane_jobs (
 id uuid primary key default gen_random_uuid(),
 run_id uuid not null references public.factory_runs(id) on delete cascade,
 project_id uuid not null references public.factory_projects(id) on delete cascade,
 role text not null check (role in ('security','qa','operations')),
 candidate_commit text not null,
 status text not null default 'queued' check (status in ('queued','claimed','passed','failed','blocked')),
 required boolean not null default true,
 attempt_count integer not null default 0 check (attempt_count >= 0),
 lease_owner text,
 lease_expires_at timestamptz,
 findings jsonb not null default '[]'::jsonb,
 evidence jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 completed_at timestamptz,
 unique(run_id,role,candidate_commit)
);
alter table public.factory_specialist_lane_jobs enable row level security;
revoke all on public.factory_specialist_lane_jobs from public,anon,authenticated;
grant select,insert,update,delete on public.factory_specialist_lane_jobs to service_role;
create index if not exists idx_factory_specialist_lane_jobs_queue
 on public.factory_specialist_lane_jobs(role,status,created_at);
create index if not exists idx_factory_specialist_lane_jobs_run
 on public.factory_specialist_lane_jobs(run_id,status);

create or replace function public.factory_enqueue_specialist_lanes(p_run_id uuid)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
 v_run public.factory_runs%rowtype;
 v_project_id uuid;
 v_plan jsonb;
 v_role text;
 v_roles text[]:=array[]::text[];
 v_count integer:=0;
begin
 select r.* into v_run from public.factory_runs r where r.id=p_run_id for update;
 if not found then raise exception 'run not found'; end if;
 if nullif(v_run.candidate_commit,'') is null then raise exception 'candidate commit required'; end if;
 select t.project_id into v_project_id from public.factory_tasks t where t.id=v_run.task_id;
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
   insert into public.factory_specialist_lane_jobs(run_id,project_id,role,candidate_commit,status,required)
   values(p_run_id,v_project_id,v_role,v_run.candidate_commit,'queued',true)
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
$$;
revoke all on function public.factory_enqueue_specialist_lanes(uuid) from public,anon,authenticated;
grant execute on function public.factory_enqueue_specialist_lanes(uuid) to service_role;

create or replace function public.factory_claim_specialist_lane(
 p_role text,
 p_worker_id text,
 p_lease_seconds integer default 600
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_job public.factory_specialist_lane_jobs%rowtype;v_project public.factory_projects%rowtype;v_run public.factory_runs%rowtype;
begin
 if p_role not in ('security','qa','operations') then raise exception 'invalid specialist role'; end if;
 if nullif(btrim(p_worker_id),'') is null then raise exception 'worker id required'; end if;
 if p_lease_seconds<60 or p_lease_seconds>1800 then raise exception 'invalid lease'; end if;

 select * into v_job
 from public.factory_specialist_lane_jobs
 where role=p_role
   and attempt_count < 3
   and (
     status='queued'
     or (status='claimed' and lease_expires_at<=now())
   )
 order by created_at
 for update skip locked
 limit 1;
 if v_job.id is null then return null; end if;

 select * into v_run from public.factory_runs where id=v_job.run_id;
 if v_run.candidate_commit is distinct from v_job.candidate_commit then
   update public.factory_specialist_lane_jobs set status='blocked',completed_at=now(),updated_at=now(),
     findings=jsonb_build_array(jsonb_build_object('code','candidate_commit_mismatch','severity','critical'))
   where id=v_job.id;
   return null;
 end if;
 select * into v_project from public.factory_projects where id=v_job.project_id;

 update public.factory_specialist_lane_jobs
 set status='claimed',lease_owner=p_worker_id,lease_expires_at=now()+make_interval(secs=>p_lease_seconds),
     attempt_count=attempt_count+1,updated_at=now()
 where id=v_job.id;

 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 select v_job.project_id,r.task_id,v_job.run_id,'agent',p_role,'specialist.lane.claimed',
        jsonb_build_object('job_id',v_job.id,'candidate_commit',v_job.candidate_commit,'worker_id',p_worker_id)
 from public.factory_runs r where r.id=v_job.run_id;

 return jsonb_build_object(
   'job_id',v_job.id,'run_id',v_job.run_id,'project_key',v_project.project_key,'repository',v_project.repository,
   'role',v_job.role,'candidate_commit',v_job.candidate_commit,'manifest',v_project.manifest
 );
end;
$$;
revoke all on function public.factory_claim_specialist_lane(text,text,integer) from public,anon,authenticated;
grant execute on function public.factory_claim_specialist_lane(text,text,integer) to service_role;

create or replace function public.factory_complete_specialist_lane(
 p_job_id uuid,
 p_status text,
 p_findings jsonb default '[]'::jsonb,
 p_evidence jsonb default '{}'::jsonb
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_job public.factory_specialist_lane_jobs%rowtype;v_remaining integer;v_failed integer;v_run_status text;
begin
 if p_status not in ('passed','failed','blocked') then raise exception 'invalid specialist completion status'; end if;
 if jsonb_typeof(coalesce(p_findings,'[]'::jsonb))<>'array' then raise exception 'findings must be array'; end if;
 if jsonb_typeof(coalesce(p_evidence,'{}'::jsonb))<>'object' then raise exception 'evidence must be object'; end if;

 select * into v_job from public.factory_specialist_lane_jobs where id=p_job_id for update;
 if not found then raise exception 'specialist lane job not found'; end if;
 if v_job.status<>'claimed' then raise exception 'specialist lane job is not claimed'; end if;

 update public.factory_specialist_lane_jobs
 set status=p_status,findings=coalesce(p_findings,'[]'::jsonb),evidence=coalesce(p_evidence,'{}'::jsonb),
     completed_at=now(),updated_at=now(),lease_expires_at=null
 where id=p_job_id;

 insert into public.factory_evaluations(run_id,eval_type,status,baseline_ref,result)
 values(v_job.run_id,'specialist_'||v_job.role,p_status,v_job.candidate_commit,
   jsonb_build_object('job_id',p_job_id,'role',v_job.role,'findings',coalesce(p_findings,'[]'::jsonb),'evidence',coalesce(p_evidence,'{}'::jsonb)));

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
$$;
revoke all on function public.factory_complete_specialist_lane(uuid,text,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.factory_complete_specialist_lane(uuid,text,jsonb,jsonb) to service_role;


create or replace function public.factory_recover_specialist_lanes(p_max_attempts integer default 3)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_requeued integer:=0;v_blocked integer:=0;
begin
 if p_max_attempts<1 or p_max_attempts>10 then raise exception 'invalid max attempts'; end if;

 update public.factory_specialist_lane_jobs
 set status='queued',lease_owner=null,lease_expires_at=null,updated_at=now()
 where status='claimed' and lease_expires_at<=now() and attempt_count<p_max_attempts;
 get diagnostics v_requeued=row_count;

 update public.factory_specialist_lane_jobs
 set status='blocked',lease_owner=null,lease_expires_at=null,completed_at=now(),updated_at=now(),
     findings=case when findings='[]'::jsonb then jsonb_build_array(jsonb_build_object(
       'code','specialist_retry_exhausted','severity','critical','message','specialist lane exhausted retry attempts'
     )) else findings end
 where status='claimed' and lease_expires_at<=now() and attempt_count>=p_max_attempts;
 get diagnostics v_blocked=row_count;

 update public.factory_runs r
 set status='specialist_review_failed'
 where exists(
   select 1 from public.factory_specialist_lane_jobs j
   where j.run_id=r.id and j.required and j.status='blocked'
 );

 return jsonb_build_object('requeued',v_requeued,'blocked',v_blocked);
end;
$$;
revoke all on function public.factory_recover_specialist_lanes(integer) from public,anon,authenticated;
grant execute on function public.factory_recover_specialist_lanes(integer) to service_role;
