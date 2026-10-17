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
   if v_run->>'created' is distinct from 'true' then
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
