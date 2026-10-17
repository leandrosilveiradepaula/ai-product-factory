-- #894: operator-owned execution control. CANDIDATE: PRODUCTION MIGRATION NEEDS HUMAN GATE.
-- New project registration becomes draft. Historical active projects are explicitly
-- backfilled running to avoid silently interrupting already admitted workflows.
create table public.factory_project_execution_controls (
 project_id uuid primary key references public.factory_projects(id) on delete restrict,
 state text not null default 'draft'
  check (state in ('draft','running','pausing','paused','stopping','stopped')),
 version bigint not null default 0 check (version >= 0),
 generation bigint not null default 0 check (generation >= 0),
 updated_at timestamptz not null default now(),
 last_command_id uuid,
 last_actor uuid
);
create table public.factory_project_execution_commands (
 project_id uuid not null references public.factory_projects(id) on delete restrict,
 command_id uuid not null,
 command text not null,
 expected_version bigint not null,
 actor_id uuid not null,
 result jsonb not null,
 created_at timestamptz not null default now(),
 primary key (project_id,command_id)
);
alter table public.factory_project_execution_controls enable row level security;
alter table public.factory_project_execution_commands enable row level security;
revoke all on public.factory_project_execution_controls from public, anon, authenticated;
revoke all on public.factory_project_execution_commands from public, anon, authenticated;
grant select, insert, update on public.factory_project_execution_controls to service_role;
grant select, insert on public.factory_project_execution_commands to service_role;

-- Existing projects are not silently suspended or restarted on activation.
insert into public.factory_project_execution_controls(project_id,state,generation)
 select id,case when is_active then 'running' else 'stopped' end,
        case when is_active then 1 else 0 end
 from public.factory_projects
 on conflict (project_id) do nothing;

create function public.factory_create_project_execution_control()
returns trigger language plpgsql security invoker set search_path to '' as $f$
begin
 insert into public.factory_project_execution_controls(project_id,state,version,generation)
 values(new.id,'draft',0,0);
 return new;
end;
$f$;
create trigger factory_project_execution_control_on_insert
after insert on public.factory_projects
for each row execute function public.factory_create_project_execution_control();

-- One row lock serializes operator state changes against *new* DB claims.
-- Never rely on UI flags or cached project status to authorize work.
create function public.factory_assert_project_running(p_project_id uuid)
returns void language plpgsql security invoker set search_path to '' as $f$
declare v_state text;
begin
 select state into v_state from public.factory_project_execution_controls
 where project_id=p_project_id for share;
 if v_state is distinct from 'running' then
   raise exception 'project execution not authorized (%).',coalesce(v_state,'missing')
    using errcode='PT409';
 end if;
end;
$f$;
revoke all on function public.factory_create_project_execution_control() from public,anon,authenticated;
revoke all on function public.factory_assert_project_running(uuid) from public,anon,authenticated;
grant execute on function public.factory_create_project_execution_control() to service_role;
grant execute on function public.factory_assert_project_running(uuid) to service_role;

-- A defense-in-depth database claim fence applies to every executor route,
-- even older/unpatched workers. Terminal updates for quiescence stay allowed.
create function public.factory_guard_project_execution_dml()
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
      and new.lease_expires_at > now());
 elsif tg_table_name='factory_change_sets' then
   v_project_id:=new.project_id;
   v_guard := tg_op='INSERT' or
     (new.status is distinct from old.status and
      new.status not in ('completed','cancelled','failed','merged','blocked','superseded')) or
     (new.lease_owner is not null and
      (tg_op='INSERT' or new.lease_owner is distinct from old.lease_owner)) or
     (tg_op='UPDATE' and new.lease_expires_at is distinct from old.lease_expires_at
      and new.lease_expires_at > now());
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
create trigger factory_execution_guard_task before insert or update on public.factory_tasks
 for each row execute function public.factory_guard_project_execution_dml();
create trigger factory_execution_guard_run before insert or update on public.factory_runs
 for each row execute function public.factory_guard_project_execution_dml();
create trigger factory_execution_guard_change_set before insert or update on public.factory_change_sets
 for each row execute function public.factory_guard_project_execution_dml();
create trigger factory_execution_guard_agent before insert or update on public.factory_run_agent_assignments
 for each row execute function public.factory_guard_project_execution_dml();
revoke all on function public.factory_guard_project_execution_dml() from public,anon,authenticated;
grant execute on function public.factory_guard_project_execution_dml() to service_role;

-- Atomic registration WITHOUT an executable task or run.
create function public.factory_register_project_intake_v2(
 p_project_key text,p_name text,p_repository text,p_project_kind text,
 p_manifest jsonb,p_spec jsonb,p_draft_id uuid,p_operator_user_id uuid,
 p_expected_attachments integer
) returns jsonb language plpgsql security invoker set search_path to '' as $f$
declare v_id uuid;v_name text;v_repo text;v_kind text;v_manifest jsonb;
        v_spec jsonb;v_count integer;
begin
 if nullif(btrim(p_project_key),'') is null or nullif(btrim(p_name),'') is null
    or p_project_kind not in ('greenfield','existing')
    or p_draft_id is null or p_operator_user_id is null
    or p_expected_attachments is null or p_expected_attachments not between 0 and 10
    or jsonb_typeof(p_manifest) is distinct from 'object'
    or jsonb_typeof(p_spec) is distinct from 'object'
    or p_manifest->>'source' is distinct from 'factory-console'
    or p_manifest->>'onboarding_mode' is distinct from p_project_kind
    or p_manifest ?| array['bootstrap_request_id','bootstrap_attachment_count','bootstrap_operator_id']
 then raise exception 'invalid project registration' using errcode='PT400'; end if;
 perform pg_catalog.pg_advisory_xact_lock(
   pg_catalog.hashtextextended('factory-intake:'||btrim(p_project_key),0));
 select id,name,repository,project_kind,manifest
 into v_id,v_name,v_repo,v_kind,v_manifest
 from public.factory_projects where project_key=btrim(p_project_key)
 for update;
 if v_id is not null then
   select spec into v_spec from public.factory_product_specs
    where project_id=v_id and version=1 limit 1;
   if v_manifest->>'bootstrap_request_id' is distinct from p_draft_id::text
      or v_manifest->>'bootstrap_attachment_count' is distinct from p_expected_attachments::text
      or v_manifest->>'bootstrap_operator_id' is distinct from p_operator_user_id::text
      or v_name is distinct from btrim(p_name)
      or coalesce(v_repo,'') is distinct from coalesce(nullif(btrim(p_repository),''),'')
      or v_kind is distinct from p_project_kind
      or (v_manifest - 'bootstrap_request_id' - 'bootstrap_attachment_count'
           - 'bootstrap_operator_id') is distinct from p_manifest
      or v_spec is distinct from p_spec
   then raise exception 'project key belongs to different intake'
     using errcode='PT409';end if;
   select count(*) into v_count from public.factory_project_attachments
    where project_id=v_id and draft_id=p_draft_id
     and operator_user_id=p_operator_user_id and finalized_at is not null;
   if v_count is distinct from p_expected_attachments then
     raise exception 'replayed attachment mismatch' using errcode='PT409';end if;
   return jsonb_build_object('project_id',v_id,'created',false,
     'attachment_count',v_count,'request_id',p_draft_id,'state',
     (select state from public.factory_project_execution_controls where project_id=v_id));
 end if;
 v_id:=public.factory_create_project_intake(
   p_project_key,p_name,p_repository,p_project_kind,
   p_manifest||jsonb_build_object(
     'bootstrap_request_id',p_draft_id::text,
     'bootstrap_attachment_count',p_expected_attachments,
     'bootstrap_operator_id',p_operator_user_id::text),p_spec);
 v_count:=public.factory_finalize_project_attachments(
   p_draft_id,p_operator_user_id,v_id);
 if v_count is distinct from p_expected_attachments then
   raise exception 'attachment count changed' using errcode='PT409';end if;
 insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
 values(v_id,'human',p_operator_user_id::text,'project.registered_draft',
   jsonb_build_object('request_id',p_draft_id,'state','draft','attachment_count',v_count));
 return jsonb_build_object('project_id',v_id,'created',true,
   'attachment_count',v_count,'request_id',p_draft_id,'state','draft');
end;
$f$;
revoke all on function public.factory_register_project_intake_v2(
 text,text,text,text,jsonb,jsonb,uuid,uuid,integer) from public,anon,authenticated;
grant execute on function public.factory_register_project_intake_v2(
 text,text,text,text,jsonb,jsonb,uuid,uuid,integer) to service_role;
-- The old atomic register-and-run endpoint must not remain a bypass for
-- older Console deployments during migration rollout.
revoke execute on function public.factory_start_project_intake_v1(
 text,text,text,text,jsonb,jsonb,uuid,uuid,integer) from service_role;

-- An owned lease with unknown expiry cannot prove quiescence. The worker
-- must release it or take an explicitly audited recovery path.
create function public.factory_control_quiescent(p_project_id uuid)
returns boolean language sql stable security invoker set search_path to '' as $f$
 select not exists (
  select 1 from public.factory_runs r
  join public.factory_tasks t on t.id=r.task_id
  where t.project_id=p_project_id and r.lease_owner is not null
    and (r.lease_expires_at is null or r.lease_expires_at>now()) and
    r.status not in ('completed','cancelled','failed','merged','blocked','superseded')
 ) and not exists (
  select 1 from public.factory_change_sets cs
  where cs.project_id=p_project_id and cs.lease_owner is not null
    and (cs.lease_expires_at is null or cs.lease_expires_at>now())
    and cs.status not in ('completed','cancelled','failed','merged','blocked','superseded')
 )
$f$;
revoke all on function public.factory_control_quiescent(uuid) from public,anon,authenticated;
grant execute on function public.factory_control_quiescent(uuid) to service_role;

-- All state changes use operator-authenticated service role calls. Single project
-- lock + expected version + command id prevents lost updates and double start.
create function public.factory_control_project_v1(
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
 if v_next='stopped' then
   update public.factory_runs r set status='cancelled'
    from public.factory_tasks t where r.task_id=t.id and t.project_id=v_id
      and r.status in ('created','queued');
   update public.factory_tasks set status='cancelled',updated_at=now()
    where project_id=v_id and status in ('queued','queued_execution');
 end if;
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
revoke all on function public.factory_control_project_v1(
 text,text,uuid,bigint,uuid) from public,anon,authenticated;
grant execute on function public.factory_control_project_v1(
 text,text,uuid,bigint,uuid) to service_role;

-- Controller-only quiescence acknowledgement. Does not cancel external CI.
create function public.factory_settle_project_control_v1(p_project_key text)
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
 if v_state='stopping' then
   update public.factory_runs r set status='cancelled' from public.factory_tasks t
    where r.task_id=t.id and t.project_id=v_id and r.status in ('created','queued');
   update public.factory_tasks set status='cancelled',updated_at=now()
    where project_id=v_id and status in ('queued','queued_execution');
 end if;
 insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
 values(v_id,'system','project-controller',
   case when v_state='pausing' then 'project.control.paused' else 'project.control.stopped' end,
   jsonb_build_object('previous_state',v_state,'version',v_version+1));
 return jsonb_build_object('state',
  case when v_state='pausing' then 'paused' else 'stopped' end,
  'changed',true,'version',v_version+1);
end;
$f$;
revoke all on function public.factory_settle_project_control_v1(text)
 from public,anon,authenticated;
grant execute on function public.factory_settle_project_control_v1(text) to service_role;

-- A worker must revalidate its execution epoch immediately before every
-- model, network, GitHub or deployment side effect. A stale generation fails
-- closed even if the project was paused and later resumed.
create function public.factory_assert_project_execution_epoch(
 p_project_id uuid,p_generation bigint
) returns void language plpgsql security invoker set search_path to '' as $f$
declare v_state text;v_generation bigint;
begin
 if p_project_id is null or p_generation is null or p_generation < 1 then
   raise exception 'invalid execution epoch' using errcode='PT400';
 end if;
 select state,generation into v_state,v_generation
 from public.factory_project_execution_controls
 where project_id=p_project_id for share;
 if v_state is distinct from 'running'
    or v_generation is distinct from p_generation then
   raise exception 'project execution epoch revoked' using errcode='PT409';
 end if;
end;
$f$;
revoke all on function public.factory_assert_project_execution_epoch(uuid,bigint)
 from public,anon,authenticated;
grant execute on function public.factory_assert_project_execution_epoch(uuid,bigint)
 to service_role;
