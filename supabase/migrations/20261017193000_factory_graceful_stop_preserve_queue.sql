-- Graceful STOP: preserve queued work and permit existing owners to renew live leases.
-- New claims remain denied by factory_assert_project_running.
-- IMPORTANT: execution-epoch fencing remains strict; workers must finish without
-- new external side effects while stopping. Full graceful completion needs
-- an explicit per-run epoch/lease capability in a subsequent revision.
create or replace function public.factory_guard_project_execution_dml()
returns trigger language plpgsql security invoker set search_path to '' as $f$
declare v_project_id uuid; v_guard boolean := false;
begin
 if tg_table_name='factory_tasks' then
   v_project_id:=new.project_id;
   v_guard := tg_op='INSERT' or
     (new.status is distinct from old.status and
      new.status not in ('completed','cancelled','failed','merged','integrated','blocked'));
 elsif tg_table_name='factory_runs' then
   select t.project_id into v_project_id from public.factory_tasks t where t.id=new.task_id;
   v_guard := tg_op='INSERT' or
     (new.status is distinct from old.status and
      new.status not in ('completed','cancelled','failed','merged','blocked','superseded')) or
     (new.lease_owner is not null and
      (tg_op='INSERT' or new.lease_owner is distinct from old.lease_owner)) or
     (tg_op='UPDATE' and new.lease_expires_at is distinct from old.lease_expires_at
      and new.lease_expires_at > now() and not (tg_op='UPDATE' and new.lease_owner is not distinct from old.lease_owner and old.lease_owner is not null and (old.lease_expires_at is null or old.lease_expires_at > now())));
 elsif tg_table_name='factory_change_sets' then
   v_project_id:=new.project_id;
   v_guard := tg_op='INSERT' or
     (new.status is distinct from old.status and
      new.status not in ('completed','cancelled','failed','merged','blocked','superseded')) or
     (new.lease_owner is not null and
      (tg_op='INSERT' or new.lease_owner is distinct from old.lease_owner)) or
     (tg_op='UPDATE' and new.lease_expires_at is distinct from old.lease_expires_at
      and new.lease_expires_at > now() and not (tg_op='UPDATE' and new.lease_owner is not distinct from old.lease_owner and old.lease_owner is not null and (old.lease_expires_at is null or old.lease_expires_at > now())));
 elsif tg_table_name='factory_run_agent_assignments' then
   select t.project_id into v_project_id from public.factory_runs r
    join public.factory_tasks t on t.id=r.task_id where r.id=new.run_id;
   v_guard := (tg_op='INSERT' and new.status in ('assigned','claimed')) or
      (tg_op='UPDATE' and new.status is distinct from old.status
       and new.status in ('assigned','claimed'));
 end if;
 if v_guard then
   if v_project_id is null then raise exception 'project ownership missing'
     using errcode='PT409'; end if;
   perform public.factory_assert_project_running(v_project_id);
 end if;
 return new;
end;
$f$;

create or replace function public.factory_control_project_v1(
 p_project_key text,p_command text,p_command_id uuid,
 p_expected_version bigint,p_actor_id uuid
) returns jsonb language plpgsql security invoker set search_path to '' as $f$
declare v_id uuid;v_state text;v_version bigint;v_generation bigint;
        v_next text;v_result jsonb;v_existing record;v_run jsonb;
begin
 if nullif(btrim(p_project_key),'') is null or p_actor_id is null or
    p_command_id is null or p_expected_version is null or p_expected_version<0
    or p_command not in ('start','pause','resume','stop','restart') then
    raise exception 'invalid project control command' using errcode='PT400';
 end if;
 select id into v_id from public.factory_projects
  where project_key=btrim(p_project_key) and is_active for update;
 if v_id is null then raise exception 'project not found' using errcode='PT404';end if;
 select * into v_existing from public.factory_project_execution_commands
  where project_id=v_id and command_id=p_command_id;
 if found then
   if v_existing.command is distinct from p_command
      or v_existing.expected_version is distinct from p_expected_version
      or v_existing.actor_id is distinct from p_actor_id then
      raise exception 'control command id reused' using errcode='PT409';
   end if;
   return v_existing.result;
 end if;
 select state,version,generation into v_state,v_version,v_generation
  from public.factory_project_execution_controls
  where project_id=v_id for update;
 if v_state is null or v_version is distinct from p_expected_version then
   raise exception 'stale or missing project control' using errcode='PT409';end if;
 if p_command='start' and v_state='draft' then v_next:='running';
 elsif p_command='pause' and v_state='running' then
   v_next:=case when public.factory_control_quiescent(v_id) then 'paused' else 'pausing' end;
 elsif p_command='resume' and v_state='paused' then v_next:='running';
 elsif p_command='stop' and v_state in ('running','pausing','paused') then
   v_next:=case when public.factory_control_quiescent(v_id) then 'stopped' else 'stopping' end;
 elsif p_command='restart' and v_state='stopped' then v_next:='running';
 else raise exception 'invalid lifecycle transition' using errcode='PT409';end if;
 if p_command in ('start','resume','restart') then
   v_generation:=v_generation+1;
 end if;
 update public.factory_project_execution_controls set
  state=v_next,version=version+1,generation=v_generation,
  updated_at=now(),last_command_id=p_command_id,last_actor=p_actor_id
 where project_id=v_id and version=v_version;
 if not found then raise exception 'lost control version lock' using errcode='PT409';end if;
 if p_command in ('start','restart') then
   v_run:=public.factory_enqueue_project_bootstrap(p_project_key);
   if v_run->>'created' is distinct from 'true' and p_command='start' then
     raise exception 'start did not create new bootstrap' using errcode='PT409';
   end if;
 end if;
 v_result:=jsonb_build_object('project_id',v_id,'state',v_next,'version',v_version+1,
    'generation',v_generation,'command',p_command,'created',true,
    'run_id',v_run->>'run_id','task_id',v_run->>'task_id');
 insert into public.factory_project_execution_commands(
   project_id,command_id,command,expected_version,actor_id,result)
 values(v_id,p_command_id,p_command,p_expected_version,p_actor_id,v_result);
 insert into public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_id,(v_run->>'run_id')::uuid,'human',p_actor_id::text,
   'project.control.'||p_command,
   jsonb_build_object('command_id',p_command_id,'previous_state',v_state,
     'next_state',v_next,'version',v_version+1,'generation',v_generation));
 return v_result;
end;
$f$;

create or replace function public.factory_settle_project_control_v1(p_project_key text)
returns jsonb language plpgsql security invoker set search_path to '' as $f$
declare v_id uuid;v_state text;v_version bigint;
begin
 select p.id,c.state,c.version into v_id,v_state,v_version
 from public.factory_projects p join public.factory_project_execution_controls c
 on c.project_id=p.id where p.project_key=btrim(p_project_key)
 for update of p,c;
 if v_id is null then raise exception 'project not found' using errcode='PT404';end if;
 if v_state not in ('pausing','stopping') or not public.factory_control_quiescent(v_id)
 then return jsonb_build_object('state',v_state,'changed',false,'version',v_version);end if;
 update public.factory_project_execution_controls set
   state=case when v_state='pausing' then 'paused' else 'stopped' end,
   version=version+1,updated_at=now() where project_id=v_id;
 insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
 values(v_id,'system','project-controller',
   case when v_state='pausing' then 'project.control.paused' else 'project.control.stopped' end,
   jsonb_build_object('previous_state',v_state,'version',v_version+1));
 return jsonb_build_object('state',
  case when v_state='pausing' then 'paused' else 'stopped' end,
  'changed',true,'version',v_version+1);
end;
$f$;

-- Authorize only the original owner of a claimed run while draining.
create function public.factory_assert_claimed_run_epoch(p_project_id uuid,p_generation bigint,p_run_id uuid,p_worker_id text)
returns void language plpgsql security invoker set search_path to '' as $f$
declare v_state text;v_generation bigint;v_run record;
begin
 if p_project_id is null or p_generation is null or p_generation<1 or p_run_id is null or nullif(btrim(p_worker_id),'') is null then
  raise exception 'invalid claimed run capability' using errcode='PT400';end if;
 select state,generation into v_state,v_generation from public.factory_project_execution_controls where project_id=p_project_id for share;
 if v_generation is distinct from p_generation or v_state not in ('running','pausing','stopping') then
  raise exception 'claimed run epoch revoked' using errcode='PT409';end if;
 select r.status,r.lease_owner,r.lease_expires_at,r.metadata into v_run
 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
 where r.id=p_run_id and t.project_id=p_project_id;
 if not found or v_run.status is distinct from 'running'
 or v_run.lease_owner is distinct from p_worker_id
 or (v_run.lease_expires_at is not null and v_run.lease_expires_at<=now())
 or v_run.metadata->>'execution_generation' is distinct from p_generation::text then
  raise exception 'claimed run capability revoked' using errcode='PT409';end if;
end;
$f$;
revoke all on function public.factory_assert_claimed_run_epoch(uuid,bigint,uuid,text) from public,anon,authenticated;
grant execute on function public.factory_assert_claimed_run_epoch(uuid,bigint,uuid,text) to service_role;

-- Claim stamps durable ownership so draining waits for the claimed worker.
create or replace function public.factory_claim_next_run(p_worker_id text)
returns jsonb language plpgsql security invoker set search_path='' as $f$
declare v_run public.factory_runs%rowtype;v_task public.factory_tasks%rowtype;
 v_project public.factory_projects%rowtype;v_generation bigint;
begin
 if nullif(btrim(p_worker_id),'') is null then
  raise exception 'worker_id is required' using errcode='PT400';
 end if;
 select r.* into v_run from public.factory_runs r
 join public.factory_tasks t on t.id=r.task_id
 join public.factory_project_execution_controls c on c.project_id=t.project_id
 where r.status in ('created','queued') and t.status='queued'
   and c.state='running'
 order by r.created_at for update of c skip locked limit 1;
 if v_run.id is null then return null;end if;
 -- Acquire control first, then the task and run rows, matching operator lock order.
 select * into v_task from public.factory_tasks where id=v_run.task_id for update;
 -- Another claimant may have won while we waited for the task lock.
 if v_task.status is distinct from 'queued' then return null;end if;
 select * into v_run from public.factory_runs where id=v_run.id for update;
 if v_run.status not in ('created','queued') then return null;end if;
 select * into v_project from public.factory_projects where id=v_task.project_id;
 select generation into v_generation from public.factory_project_execution_controls
 where project_id=v_project.id for share;
 perform public.factory_assert_project_execution_epoch(v_project.id,v_generation);
 update public.factory_runs set status='running',lease_owner=p_worker_id,lease_expires_at=null,started_at=coalesce(started_at,now()),
  metadata=coalesce(metadata,'{}'::jsonb)||jsonb_build_object(
   'worker_id',p_worker_id,'claimed_at',now(),'execution_generation',v_generation)
 where id=v_run.id;
 update public.factory_tasks set status='running',updated_at=now() where id=v_task.id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,v_task.id,v_run.id,'system',p_worker_id,'run.claimed',
 jsonb_build_object('execution_generation',v_generation));
 return jsonb_build_object('run_id',v_run.id,'task_id',v_task.id,
  'project_id',v_project.id,'project_key',v_project.project_key,
  'execution_generation',v_generation,
  'stages',coalesce(v_run.metadata->'stages','[]'::jsonb),
  'context',jsonb_build_object('task',v_task.description,'manifest',v_project.manifest));
end;
$f$;
