alter table public.factory_tasks add column if not exists agent_role text;
alter table public.factory_tasks add column if not exists required_capabilities jsonb not null default '[]'::jsonb;
alter table public.factory_tasks add column if not exists scope_keys jsonb not null default '[]'::jsonb;

create table if not exists public.factory_agents (
 id uuid primary key default gen_random_uuid(),
 agent_key text not null unique,
 name text not null,
 role text not null,
 description text not null default '',
 capabilities jsonb not null default '[]'::jsonb,
 allowed_tools jsonb not null default '[]'::jsonb,
 model_policy jsonb not null default '{}'::jsonb,
 max_concurrency integer not null default 1 check (max_concurrency between 1 and 32),
 cost_budget_usd numeric check (cost_budget_usd is null or cost_budget_usd >= 0),
 is_active boolean not null default true,
 health_status text not null default 'idle' check (health_status in ('idle','working','blocked','degraded','disabled')),
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
alter table public.factory_agents enable row level security;
revoke all on public.factory_agents from public,anon,authenticated;
grant select,insert,update,delete on public.factory_agents to service_role;

create table if not exists public.factory_run_agent_assignments (
 id uuid primary key default gen_random_uuid(),
 run_id uuid not null unique references public.factory_runs(id) on delete cascade,
 agent_id uuid not null references public.factory_agents(id) on delete restrict,
 status text not null default 'assigned' check (status in ('assigned','claimed','completed','released','blocked')),
 assigned_at timestamptz not null default now(),
 claimed_at timestamptz,
 released_at timestamptz,
 metadata jsonb not null default '{}'::jsonb
);
alter table public.factory_run_agent_assignments enable row level security;
revoke all on public.factory_run_agent_assignments from public,anon,authenticated;
grant select,insert,update,delete on public.factory_run_agent_assignments to service_role;
create index if not exists idx_factory_run_agent_assignments_agent_status
 on public.factory_run_agent_assignments(agent_id,status);

create table if not exists public.factory_agent_scope_locks (
 id uuid primary key default gen_random_uuid(),
 project_id uuid not null references public.factory_projects(id) on delete cascade,
 run_id uuid not null references public.factory_runs(id) on delete cascade,
 agent_id uuid not null references public.factory_agents(id) on delete restrict,
 scope_key text not null,
 acquired_at timestamptz not null default now(),
 lease_expires_at timestamptz not null,
 released_at timestamptz,
 constraint factory_agent_scope_key_nonempty check (btrim(scope_key) <> '')
);
alter table public.factory_agent_scope_locks enable row level security;
revoke all on public.factory_agent_scope_locks from public,anon,authenticated;
grant select,insert,update,delete on public.factory_agent_scope_locks to service_role;
create index if not exists idx_factory_agent_scope_locks_active
 on public.factory_agent_scope_locks(project_id,scope_key,lease_expires_at)
 where released_at is null;

create or replace function public.factory_claim_agent_slot(
 p_run_id uuid,
 p_agent_key text,
 p_scope_keys jsonb default '[]'::jsonb,
 p_lease_seconds integer default 900
) returns uuid
language plpgsql security invoker set search_path='' as $$
declare
 v_agent public.factory_agents%rowtype;
 v_task public.factory_tasks%rowtype;
 v_project_id uuid;
 v_assignment_id uuid;
 v_active_count integer;
 v_scope text;
 v_conflict record;
begin
 if p_lease_seconds < 60 or p_lease_seconds > 7200 then raise exception 'invalid agent lease'; end if;
 if jsonb_typeof(coalesce(p_scope_keys,'[]'::jsonb)) <> 'array' then raise exception 'scope keys must be an array'; end if;

 select * into v_agent from public.factory_agents where agent_key=p_agent_key and is_active for update;
 if not found then raise exception 'active agent not found'; end if;

 select t.* into v_task from public.factory_runs r join public.factory_tasks t on t.id=r.task_id where r.id=p_run_id;
 if not found then raise exception 'run not found'; end if;
 v_project_id:=v_task.project_id;

 select count(*) into v_active_count
 from public.factory_run_agent_assignments a
 where a.agent_id=v_agent.id and a.status in ('assigned','claimed');
 if v_active_count >= v_agent.max_concurrency then raise exception 'agent concurrency exhausted'; end if;

 if exists(select 1 from public.factory_run_agent_assignments where run_id=p_run_id and status in ('assigned','claimed')) then
  raise exception 'run already assigned';
 end if;

 for v_scope in select value from jsonb_array_elements_text(coalesce(p_scope_keys,'[]'::jsonb))
 loop
  if btrim(v_scope)='' or v_scope like '%..%' then raise exception 'invalid scope key'; end if;
  select l.scope_key,l.run_id into v_conflict
  from public.factory_agent_scope_locks l
  where l.project_id=v_project_id
    and l.released_at is null
    and l.run_id <> p_run_id
    and (
      l.scope_key=v_scope
      or l.scope_key like v_scope || '/%'
      or v_scope like l.scope_key || '/%'
    )
  limit 1;
  if found then raise exception 'scope conflict with run % on %',v_conflict.run_id,v_conflict.scope_key; end if;
 end loop;

 insert into public.factory_run_agent_assignments(run_id,agent_id,status,claimed_at)
 values(p_run_id,v_agent.id,'claimed',now()) returning id into v_assignment_id;

 for v_scope in select value from jsonb_array_elements_text(coalesce(p_scope_keys,'[]'::jsonb))
 loop
  insert into public.factory_agent_scope_locks(project_id,run_id,agent_id,scope_key,lease_expires_at)
  values(v_project_id,p_run_id,v_agent.id,v_scope,now()+make_interval(secs=>p_lease_seconds));
 end loop;

 update public.factory_agents set health_status='working',updated_at=now() where id=v_agent.id;
 return v_assignment_id;
end;$$;
revoke all on function public.factory_claim_agent_slot(uuid,text,jsonb,integer) from public,anon,authenticated;
grant execute on function public.factory_claim_agent_slot(uuid,text,jsonb,integer) to service_role;

create or replace function public.factory_release_agent_slot(
 p_run_id uuid,
 p_status text default 'released'
) returns void
language plpgsql security invoker set search_path='' as $$
declare v_agent_id uuid;
begin
 if p_status not in ('completed','released','blocked') then raise exception 'invalid assignment release status'; end if;
 update public.factory_run_agent_assignments
 set status=p_status,released_at=now()
 where run_id=p_run_id and status in ('assigned','claimed')
 returning agent_id into v_agent_id;
 update public.factory_agent_scope_locks set released_at=now() where run_id=p_run_id and released_at is null;
 if v_agent_id is not null and not exists(
   select 1 from public.factory_run_agent_assignments
   where agent_id=v_agent_id and status in ('assigned','claimed')
 ) then
   update public.factory_agents set health_status='idle',updated_at=now() where id=v_agent_id and is_active;
 end if;
end;$$;
revoke all on function public.factory_release_agent_slot(uuid,text) from public,anon,authenticated;
grant execute on function public.factory_release_agent_slot(uuid,text) to service_role;

insert into public.factory_agents(agent_key,name,role,description,capabilities,allowed_tools,model_policy,max_concurrency,cost_budget_usd)
values
 ('product','Product & Planning','product','Discovery, specification, planning and dependency decomposition',
  '["discovery","specification","planning","dependency_graph"]'::jsonb,
  '["control_plane","github_read","model_primary"]'::jsonb,
  '{"preferred":"primary","codex":"disabled","deterministic_first":true}'::jsonb,1,0.50),
 ('development','Development','development','Implementation and code changes',
  '["implementation","migration_authoring","integration","debug"]'::jsonb,
  '["github_write","control_plane","supabase","model_primary","codex"]'::jsonb,
  '{"preferred":"primary","codex":"complex_only","deterministic_first":true}'::jsonb,3,1.50),
 ('ui','UI/UX','ui','Console/UI implementation, Figma fidelity and browser evidence',
  '["ui","ux","accessibility","figma","browser_evidence"]'::jsonb,
  '["github_write","figma","browser","vercel_read","model_primary","codex"]'::jsonb,
  '{"preferred":"primary","codex":"complex_only","deterministic_first":true}'::jsonb,2,0.75),
 ('security','Security','security','Auth, RLS, secrets, dependency and permission review',
  '["security_review","auth","rls","secrets","supply_chain"]'::jsonb,
  '["github_read","supabase","vercel_read","control_plane","model_primary"]'::jsonb,
  '{"preferred":"primary","codex":"exceptional","deterministic_first":true}'::jsonb,2,0.50),
 ('qa','QA & Evaluation','qa','Tests, evals, regression and quality gates',
  '["tests","evals","regression","quality_gate"]'::jsonb,
  '["github_read","github_actions","browser","control_plane","model_primary"]'::jsonb,
  '{"preferred":"deterministic","fallback":"primary","codex":"disabled"}'::jsonb,3,0.25),
 ('operations','Operations & Observability','operations','CI, deployments, quotas, costs, logs and operational health',
  '["ci","deployments","quotas","costs","logs","health"]'::jsonb,
  '["github_actions","vercel_read","supabase","control_plane"]'::jsonb,
  '{"preferred":"deterministic","fallback":"primary","codex":"disabled"}'::jsonb,2,0.25)
on conflict(agent_key) do update set
 name=excluded.name,role=excluded.role,description=excluded.description,
 capabilities=excluded.capabilities,allowed_tools=excluded.allowed_tools,
 model_policy=excluded.model_policy,max_concurrency=excluded.max_concurrency,
 cost_budget_usd=excluded.cost_budget_usd,updated_at=now();


create or replace function public.factory_schedule_run_agent(
 p_run_id uuid,
 p_preferred_role text default null,
 p_required_capabilities jsonb default '[]'::jsonb,
 p_scope_keys jsonb default '[]'::jsonb,
 p_lease_seconds integer default 900
) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare
 v_agent public.factory_agents%rowtype;
 v_cap text;
 v_assignment_id uuid;
begin
 if jsonb_typeof(coalesce(p_required_capabilities,'[]'::jsonb)) <> 'array' then raise exception 'required capabilities must be an array'; end if;

 select a.* into v_agent
 from public.factory_agents a
 where a.is_active=true
   and (p_preferred_role is null or a.role=p_preferred_role or a.agent_key=p_preferred_role)
   and not exists (
     select 1 from jsonb_array_elements_text(coalesce(p_required_capabilities,'[]'::jsonb)) r(value)
     where not (a.capabilities ? r.value)
   )
   and (
     select count(*) from public.factory_run_agent_assignments x
     where x.agent_id=a.id and x.status in ('assigned','claimed')
   ) < a.max_concurrency
 order by
   case when a.agent_key=p_preferred_role then 0 when a.role=p_preferred_role then 1 else 2 end,
   a.agent_key
 for update skip locked
 limit 1;

 if v_agent.id is null then raise exception 'no eligible agent slot'; end if;

 v_assignment_id:=public.factory_claim_agent_slot(
   p_run_id,v_agent.agent_key,coalesce(p_scope_keys,'[]'::jsonb),p_lease_seconds
 );

 return jsonb_build_object(
   'assignment_id',v_assignment_id,
   'agent_id',v_agent.id,
   'agent_key',v_agent.agent_key,
   'role',v_agent.role,
   'max_concurrency',v_agent.max_concurrency,
   'model_policy',v_agent.model_policy,
   'allowed_tools',v_agent.allowed_tools
 );
end;$$;
revoke all on function public.factory_schedule_run_agent(uuid,text,jsonb,jsonb,integer) from public,anon,authenticated;
grant execute on function public.factory_schedule_run_agent(uuid,text,jsonb,jsonb,integer) to service_role;


create or replace function public.factory_schedule_next_unassigned_run()
returns jsonb language plpgsql security invoker set search_path='' as $$
declare v_run public.factory_runs%rowtype;v_task public.factory_tasks%rowtype;v_result jsonb;
begin
 select r.* into v_run
 from public.factory_runs r
 join public.factory_tasks t on t.id=r.task_id
 where r.status='queued'
   and r.execution_route in ('direct','codex')
   and t.status='queued_execution'
   and not exists(
     select 1 from public.factory_run_agent_assignments a
     where a.run_id=r.id and a.status in ('assigned','claimed')
   )
 order by r.created_at
 for update of r skip locked
 limit 1;
 if v_run.id is null then return null; end if;

 select * into v_task from public.factory_tasks where id=v_run.task_id;
 v_result:=public.factory_schedule_run_agent(
   v_run.id,
   case
     when nullif(v_task.agent_role,'') is not null then v_task.agent_role
     when coalesce(v_task.required_capabilities,'[]'::jsonb)='[]'::jsonb then 'development'
     else null
   end,
   coalesce(v_task.required_capabilities,'[]'::jsonb),
   coalesce(v_task.scope_keys,'[]'::jsonb),
   900
 );
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_task.project_id,v_task.id,v_run.id,'system','agent-scheduler','agent.assigned',v_result);
 return v_result || jsonb_build_object('run_id',v_run.id,'task_id',v_task.id);
end;$$;
revoke all on function public.factory_schedule_next_unassigned_run() from public,anon,authenticated;
grant execute on function public.factory_schedule_next_unassigned_run() to service_role;

create or replace function public.factory_claim_next_agent_direct_run(p_worker_id text,p_agent_key text default null)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare v_run public.factory_runs%rowtype;v_task public.factory_tasks%rowtype;v_project public.factory_projects%rowtype;v_branch text;v_agent_key text;
begin
 if nullif(btrim(p_worker_id),'') is null then raise exception 'worker_id is required';end if;
 select r,a2.agent_key into v_run,v_agent_key
 from public.factory_runs r
 join public.factory_tasks t on t.id=r.task_id
 join public.factory_run_agent_assignments ra on ra.run_id=r.id and ra.status in ('assigned','claimed')
 join public.factory_agents a2 on a2.id=ra.agent_id and a2.is_active=true
 where r.status='queued' and r.execution_route='direct' and t.status='queued_execution'
   and (p_agent_key is null or a2.agent_key=p_agent_key)
 order by r.created_at
 for update of r skip locked limit 1;
 if v_run.id is null then return null;end if;
 select * into v_task from public.factory_tasks where id=v_run.task_id for update;
 select * into v_project from public.factory_projects where id=v_task.project_id;
 v_branch:='factory/'||v_agent_key||'/task-'||v_task.id::text;
 update public.factory_runs set status='implementing',started_at=coalesce(started_at,now()),lease_owner=p_worker_id,
  lease_expires_at=now()+interval '15 minutes',attempt_count=attempt_count+1,last_error=null,
  metadata=metadata||jsonb_build_object('execution_worker_id',p_worker_id,'execution_claimed_at',now(),'agent_key',v_agent_key)
 where id=v_run.id;
 update public.factory_tasks set status='implementing',updated_at=now() where id=v_task.id;
 update public.factory_run_agent_assignments set status='claimed',claimed_at=coalesce(claimed_at,now()) where run_id=v_run.id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,v_task.id,v_run.id,'agent',v_agent_key,'execution.direct.claimed',jsonb_build_object('lease_minutes',15,'worker_id',p_worker_id));
 return jsonb_build_object('run_id',v_run.id,'task_id',v_task.id,'project_key',v_project.project_key,'repository',v_project.repository,
  'issue_number',null,'title',v_task.title,'description',v_task.description,'branch',v_branch,'agent_key',v_agent_key,
  'human_gate_required',coalesce((v_run.metadata->>'human_gate_required')::boolean,false));
end;$$;
revoke all on function public.factory_claim_next_agent_direct_run(text,text) from public,anon,authenticated;
grant execute on function public.factory_claim_next_agent_direct_run(text,text) to service_role;

create or replace function public.factory_claim_next_agent_codex_run(p_worker_id text,p_agent_key text default null)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare v_run public.factory_runs%rowtype;v_task public.factory_tasks%rowtype;v_project public.factory_projects%rowtype;v_branch text;v_agent_key text;
begin
 if nullif(btrim(p_worker_id),'') is null then raise exception 'worker_id is required';end if;
 select r,a2.agent_key into v_run,v_agent_key
 from public.factory_runs r
 join public.factory_tasks t on t.id=r.task_id
 join public.factory_run_agent_assignments ra on ra.run_id=r.id and ra.status in ('assigned','claimed')
 join public.factory_agents a2 on a2.id=ra.agent_id and a2.is_active=true
 where r.status='queued' and r.execution_route='codex' and t.status='queued_execution'
   and (p_agent_key is null or a2.agent_key=p_agent_key)
 order by r.created_at
 for update of r skip locked limit 1;
 if v_run.id is null then return null;end if;
 select * into v_task from public.factory_tasks where id=v_run.task_id for update;
 select * into v_project from public.factory_projects where id=v_task.project_id;
 v_branch:='factory/'||v_agent_key||'/task-'||v_task.id::text;
 update public.factory_runs set status='implementing',started_at=coalesce(started_at,now()),lease_owner=p_worker_id,
  lease_expires_at=now()+interval '15 minutes',attempt_count=attempt_count+1,last_error=null,
  metadata=metadata||jsonb_build_object('execution_worker_id',p_worker_id,'execution_claimed_at',now(),'agent_key',v_agent_key)
 where id=v_run.id;
 update public.factory_tasks set status='implementing',updated_at=now() where id=v_task.id;
 update public.factory_run_agent_assignments set status='claimed',claimed_at=coalesce(claimed_at,now()) where run_id=v_run.id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,v_task.id,v_run.id,'agent',v_agent_key,'execution.codex.claimed',jsonb_build_object('lease_minutes',15,'worker_id',p_worker_id));
 return jsonb_build_object('run_id',v_run.id,'task_id',v_task.id,'project_key',v_project.project_key,'repository',v_project.repository,
  'issue_number',null,'title',v_task.title,'description',v_task.description,'branch',v_branch,'agent_key',v_agent_key,
  'codex_level',coalesce((v_run.metadata->>'codex_level')::int,1),
  'human_gate_required',coalesce((v_run.metadata->>'human_gate_required')::boolean,false));
end;$$;
revoke all on function public.factory_claim_next_agent_codex_run(text,text) from public,anon,authenticated;
grant execute on function public.factory_claim_next_agent_codex_run(text,text) to service_role;


create or replace function public.factory_persist_product_stage(p_run_id uuid,p_stage text,p_output jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare v_task_id uuid;v_project_id uuid;v_version integer;v_created_tasks integer:=0;v_item jsonb;v_external_key text;
begin
 if p_stage not in ('discovery','specification','planning') then raise exception 'unsupported product stage';end if;
 select r.task_id,t.project_id into v_task_id,v_project_id
 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id where r.id=p_run_id;
 if v_project_id is null then raise exception 'run not found';end if;

 if p_stage='discovery' then
  update public.factory_product_specs set spec=jsonb_set(spec,'{discovery}',coalesce(p_output,'{}'::jsonb),true)
  where project_id=v_project_id and version=(select max(version) from public.factory_product_specs where project_id=v_project_id);
  update public.factory_projects set lifecycle_stage='specification',updated_at=now() where id=v_project_id;
 elsif p_stage='specification' then
  select coalesce(max(version),0)+1 into v_version from public.factory_product_specs where project_id=v_project_id;
  insert into public.factory_product_specs(project_id,version,status,spec)
  values(v_project_id,v_version,'candidate',coalesce(p_output,'{}'::jsonb));
  update public.factory_projects set lifecycle_stage='planning',updated_at=now() where id=v_project_id;
 else
  update public.factory_projects set lifecycle_stage='implementation',
   manifest=manifest||jsonb_build_object('engineering_plan',coalesce(p_output,'{}'::jsonb)),updated_at=now()
  where id=v_project_id;

  for v_item in select value from jsonb_array_elements(coalesce(p_output->'tasks','[]'::jsonb))
  loop
   v_external_key:='plan-'||substr(md5(coalesce(v_item->>'title',v_item::text)),1,16);
   if not exists(select 1 from public.factory_tasks where project_id=v_project_id and external_key=v_external_key) then
    insert into public.factory_tasks(
      project_id,parent_task_id,external_key,title,description,status,complexity,risk,
      acceptance_criteria,depends_on,agent_role,required_capabilities,scope_keys
    ) values(
      v_project_id,v_task_id,v_external_key,coalesce(nullif(v_item->>'title',''),'Planned task'),
      v_item->>'description','queued',
      case when v_item->>'complexity' in ('low','medium','high','very_high') then v_item->>'complexity' else 'medium' end,
      coalesce(v_item->'risk','{}'::jsonb),coalesce(v_item->'acceptance_criteria','[]'::jsonb),
      coalesce(v_item->'depends_on','[]'::jsonb),nullif(v_item->>'preferred_agent_role',''),
      coalesce(v_item->'required_capabilities','[]'::jsonb),coalesce(v_item->'scope_keys','[]'::jsonb)
    );
    v_created_tasks:=v_created_tasks+1;
   end if;
  end loop;
 end if;

 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project_id,v_task_id,p_run_id,'system','runtime-worker','product.stage.persisted',
  jsonb_build_object('stage',p_stage,'created_tasks',v_created_tasks));
 return jsonb_build_object('project_id',v_project_id,'stage',p_stage,'created_tasks',v_created_tasks);
end;$$;
revoke all on function public.factory_persist_product_stage(uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.factory_persist_product_stage(uuid,text,jsonb) to service_role;


create or replace function public.factory_recover_expired_agent_slots()
returns jsonb language plpgsql security invoker set search_path='' as $$
declare v_released integer:=0;v_count integer:=0;v_agent uuid;
begin
 for v_agent in
  select distinct a.agent_id
  from public.factory_run_agent_assignments a
  join public.factory_runs r on r.id=a.run_id
  where a.status in ('assigned','claimed')
    and (
      r.status in ('completed','failed','merged','released','cancelled')
      or (r.lease_expires_at is not null and r.lease_expires_at <= now())
    )
 loop
  update public.factory_run_agent_assignments a
  set status='released',released_at=now()
  from public.factory_runs r
  where a.run_id=r.id and a.agent_id=v_agent and a.status in ('assigned','claimed')
    and (
      r.status in ('completed','failed','merged','released','cancelled')
      or (r.lease_expires_at is not null and r.lease_expires_at <= now())
    );
  get diagnostics v_count = row_count;
  v_released:=v_released+v_count;
  update public.factory_agent_scope_locks l set released_at=now()
  from public.factory_runs r
  where l.run_id=r.id and l.agent_id=v_agent and l.released_at is null
    and r.status in ('completed','failed','merged','released','cancelled');
  if not exists(select 1 from public.factory_run_agent_assignments where agent_id=v_agent and status in ('assigned','claimed')) then
   update public.factory_agents set health_status=case when is_active then 'idle' else 'disabled' end,updated_at=now() where id=v_agent;
  end if;
 end loop;
 return jsonb_build_object('released',v_released);
end;$$;
revoke all on function public.factory_recover_expired_agent_slots() from public,anon,authenticated;
grant execute on function public.factory_recover_expired_agent_slots() to service_role;


create or replace function public.factory_release_agent_scope_locks(p_run_id uuid)
returns integer language plpgsql security invoker set search_path='' as $$
declare v_count integer;
begin
 update public.factory_agent_scope_locks set released_at=now()
 where run_id=p_run_id and released_at is null;
 get diagnostics v_count = row_count;
 return v_count;
end;$$;
revoke all on function public.factory_release_agent_scope_locks(uuid) from public,anon,authenticated;
grant execute on function public.factory_release_agent_scope_locks(uuid) to service_role;
