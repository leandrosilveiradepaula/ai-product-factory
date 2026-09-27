alter table public.factory_runs
  add column if not exists lease_owner text,
  add column if not exists lease_expires_at timestamptz,
  add column if not exists attempt_count integer not null default 0,
  add column if not exists last_error text;

create or replace function public.factory_claim_next_run(p_worker_id text)
returns jsonb language plpgsql security invoker set search_path=''
as $$
declare v_run public.factory_runs%rowtype; v_task public.factory_tasks%rowtype; v_project public.factory_projects%rowtype;
begin
 if nullif(btrim(p_worker_id),'') is null then raise exception 'worker_id is required'; end if;
 select r.* into v_run from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
 where r.status in ('created','queued') and t.status='queued'
 order by r.created_at for update of r skip locked limit 1;
 if v_run.id is null then return null; end if;
 select * into v_task from public.factory_tasks where id=v_run.task_id for update;
 select * into v_project from public.factory_projects where id=v_task.project_id;
 update public.factory_runs set status='running',started_at=coalesce(started_at,now()),lease_owner=p_worker_id,
   lease_expires_at=now()+interval '15 minutes',attempt_count=attempt_count+1,last_error=null,
   metadata=metadata||jsonb_build_object('worker_id',p_worker_id,'claimed_at',now()) where id=v_run.id;
 update public.factory_tasks set status='running',updated_at=now() where id=v_task.id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,v_task.id,v_run.id,'system',p_worker_id,'run.claimed',jsonb_build_object('lease_minutes',15));
 return jsonb_build_object('run_id',v_run.id,'task_id',v_task.id,'project_id',v_project.id,'project_key',v_project.project_key,'stages',coalesce(v_run.metadata->'stages','[]'::jsonb),'context',jsonb_build_object('task',v_task.description,'manifest',v_project.manifest));
end;$$;

create or replace function public.factory_claim_next_direct_run(p_worker_id text)
returns jsonb language plpgsql security invoker set search_path=''
as $$
declare v_run public.factory_runs%rowtype;v_task public.factory_tasks%rowtype;v_project public.factory_projects%rowtype;v_branch text;
begin
 if nullif(btrim(p_worker_id),'') is null then raise exception 'worker_id is required';end if;
 select r.* into v_run from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
 where r.status='queued' and r.execution_route='direct' and t.status='queued_execution'
 order by r.created_at for update of r skip locked limit 1;
 if v_run.id is null then return null;end if;
 select * into v_task from public.factory_tasks where id=v_run.task_id for update;
 select * into v_project from public.factory_projects where id=v_task.project_id;
 v_branch:='factory/task-'||v_task.id::text;
 update public.factory_runs set status='implementing',started_at=coalesce(started_at,now()),lease_owner=p_worker_id,
   lease_expires_at=now()+interval '15 minutes',attempt_count=attempt_count+1,last_error=null,
   metadata=metadata||jsonb_build_object('execution_worker_id',p_worker_id,'execution_claimed_at',now()) where id=v_run.id;
 update public.factory_tasks set status='implementing',updated_at=now() where id=v_task.id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,v_task.id,v_run.id,'system',p_worker_id,'execution.direct.claimed',jsonb_build_object('lease_minutes',15));
 return jsonb_build_object('run_id',v_run.id,'task_id',v_task.id,'project_key',v_project.project_key,'repository',v_project.repository,'issue_number',null,'title',v_task.title,'description',v_task.description,'branch',v_branch,'human_gate_required',coalesce((v_run.metadata->>'human_gate_required')::boolean,false));
end;$$;

create or replace function public.factory_finish_run(p_run_id uuid,p_status text,p_error text default null)
returns void language plpgsql security invoker set search_path=''
as $$
declare v_task_id uuid;v_project_id uuid;v_task_status text;
begin
 if p_status not in ('completed','failed') then raise exception 'invalid terminal status';end if;
 select r.task_id,t.project_id into v_task_id,v_project_id from public.factory_runs r join public.factory_tasks t on t.id=r.task_id where r.id=p_run_id for update of r;
 if v_task_id is null then raise exception 'run not found';end if;
 v_task_status:=case when p_status='completed' then 'completed' else 'failed' end;
 update public.factory_runs set status=p_status,finished_at=now(),lease_owner=null,lease_expires_at=null,last_error=p_error,
   metadata=case when p_error is null then metadata else metadata||jsonb_build_object('error',p_error) end where id=p_run_id;
 update public.factory_tasks set status=v_task_status,updated_at=now() where id=v_task_id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project_id,v_task_id,p_run_id,'system','runtime-worker','run.'||p_status,jsonb_build_object('error',p_error));
end;$$;

create or replace function public.factory_recover_expired_runs(p_max_attempts integer default 3)
returns jsonb language plpgsql security invoker set search_path=''
as $$
declare rec record;v_requeued integer:=0;v_failed integer:=0;v_task_status text;
begin
 if p_max_attempts<1 then raise exception 'max attempts must be positive';end if;
 for rec in
  select r.id,r.task_id,r.execution_route,r.metadata,r.attempt_count,t.project_id
  from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
  where r.status in ('running','implementing') and r.lease_expires_at is not null and r.lease_expires_at<now()
  for update of r skip locked
 loop
  if rec.attempt_count>=p_max_attempts then
   update public.factory_runs set status='failed',finished_at=now(),lease_owner=null,lease_expires_at=null,last_error='lease expired after maximum attempts' where id=rec.id;
   update public.factory_tasks set status='failed',updated_at=now() where id=rec.task_id;
   v_failed:=v_failed+1;
  else
   v_task_status:=case when rec.metadata ? 'stages' then 'queued' else 'queued_execution' end;
   update public.factory_runs set status='queued',lease_owner=null,lease_expires_at=null,last_error='worker lease expired; requeued' where id=rec.id;
   update public.factory_tasks set status=v_task_status,updated_at=now() where id=rec.task_id;
   v_requeued:=v_requeued+1;
  end if;
  insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  values(rec.project_id,rec.task_id,rec.id,'system','lease-recovery','run.lease_recovered',
    jsonb_build_object('attempt_count',rec.attempt_count,'max_attempts',p_max_attempts,'terminal',rec.attempt_count>=p_max_attempts));
 end loop;
 return jsonb_build_object('requeued',v_requeued,'failed',v_failed);
end;$$;

revoke all on function public.factory_claim_next_run(text) from public,anon,authenticated;
grant execute on function public.factory_claim_next_run(text) to service_role;
revoke all on function public.factory_claim_next_direct_run(text) from public,anon,authenticated;
grant execute on function public.factory_claim_next_direct_run(text) to service_role;
revoke all on function public.factory_finish_run(uuid,text,text) from public,anon,authenticated;
grant execute on function public.factory_finish_run(uuid,text,text) to service_role;
revoke all on function public.factory_recover_expired_runs(integer) from public,anon,authenticated;
grant execute on function public.factory_recover_expired_runs(integer) to service_role;
