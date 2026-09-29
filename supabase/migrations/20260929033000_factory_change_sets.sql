create table if not exists public.factory_change_sets (
 id uuid primary key default gen_random_uuid(),
 project_id uuid not null references public.factory_projects(id) on delete cascade,
 team_plan_id uuid not null references public.factory_execution_team_plans(id) on delete cascade,
 root_task_id uuid not null references public.factory_tasks(id) on delete restrict,
 status text not null default 'planned' check (status in ('planned','building','integrating','review_ready','ci_pending','blocked','completed','superseded')),
 source_commit text,
 integration_branch text,
 candidate_commit text,
 current_wave integer not null default 1 check (current_wave >= 1),
 release_run_id uuid references public.factory_runs(id) on delete set null,
 attempt_count integer not null default 0 check (attempt_count >= 0),
 lease_owner text,
 lease_expires_at timestamptz,
 metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 unique(team_plan_id)
);
alter table public.factory_change_sets enable row level security;
revoke all on public.factory_change_sets from public,anon,authenticated;
grant select,insert,update,delete on public.factory_change_sets to service_role;
create index if not exists idx_factory_change_sets_project_status
 on public.factory_change_sets(project_id,status,created_at);

create table if not exists public.factory_change_set_work_units (
 id uuid primary key default gen_random_uuid(),
 change_set_id uuid not null references public.factory_change_sets(id) on delete cascade,
 task_id uuid not null references public.factory_tasks(id) on delete cascade,
 plan_task_key text not null,
 agent_key text not null,
 wave integer not null check (wave >= 1),
 status text not null default 'pending' check (status in ('pending','queued','running','completed','integrated','failed','blocked')),
 run_id uuid references public.factory_runs(id) on delete set null,
 base_commit text,
 branch_name text,
 output_commit text,
 changed_files jsonb not null default '[]'::jsonb,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 unique(change_set_id,task_id),
 unique(change_set_id,plan_task_key)
);
alter table public.factory_change_set_work_units enable row level security;
revoke all on public.factory_change_set_work_units from public,anon,authenticated;
grant select,insert,update,delete on public.factory_change_set_work_units to service_role;
create index if not exists idx_factory_change_set_work_units_wave
 on public.factory_change_set_work_units(change_set_id,wave,status);

create or replace function public.factory_materialize_change_set(p_team_plan_id uuid)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
 v_team public.factory_execution_team_plans%rowtype;
 v_root_task_id uuid;
 v_change_set_id uuid;
 v_item jsonb;
 v_task_id uuid;
 v_external_key text;
 v_wave integer;
 v_count integer:=0;
begin
 select * into v_team from public.factory_execution_team_plans where id=p_team_plan_id for update;
 if not found then raise exception 'team plan not found'; end if;
 if v_team.status<>'ready' then raise exception 'team plan must be ready'; end if;
 select r.task_id into v_root_task_id from public.factory_runs r where r.id=v_team.source_run_id;
 if v_root_task_id is null then raise exception 'team plan source run not found'; end if;

 insert into public.factory_change_sets(project_id,team_plan_id,root_task_id,status,metadata)
 values(v_team.project_id,v_team.id,v_root_task_id,'planned',
   jsonb_build_object('team_plan_version',v_team.version,'selection_policy',v_team.plan->>'selection_policy'))
 on conflict(team_plan_id) do update set updated_at=now()
 returning id into v_change_set_id;

 delete from public.factory_change_set_work_units
 where change_set_id=v_change_set_id and status='pending';

 for v_item in
   select value from jsonb_array_elements(coalesce(v_team.plan->'task_assignments','[]'::jsonb))
 loop
   if coalesce(v_item->>'execution_lane','')<>'builder' then continue; end if;
   if coalesce(v_item->>'task_key','')='' then raise exception 'builder task missing task_key'; end if;
   v_external_key:='plan-'||substr(md5(coalesce(v_item->>'title',v_item::text)),1,16);
   select id into v_task_id
   from public.factory_tasks
   where project_id=v_team.project_id and external_key=v_external_key
   limit 1;
   if v_task_id is null then raise exception 'planned task not found for change-set task %',v_item->>'task_key'; end if;
   v_wave=coalesce((v_item->>'wave')::integer,1);
   insert into public.factory_change_set_work_units(change_set_id,task_id,plan_task_key,agent_key,wave,status)
   values(v_change_set_id,v_task_id,v_item->>'task_key',v_item->>'agent_key',v_wave,'pending')
   on conflict(change_set_id,task_id) do update set
     plan_task_key=excluded.plan_task_key,agent_key=excluded.agent_key,wave=excluded.wave,updated_at=now();
   v_count:=v_count+1;
 end loop;

 if v_count=0 then update public.factory_change_sets set status='review_ready',updated_at=now() where id=v_change_set_id; end if;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_team.project_id,v_root_task_id,v_team.source_run_id,'system','change-set-planner','change_set.materialized',
   jsonb_build_object('change_set_id',v_change_set_id,'builder_work_units',v_count,'team_plan_id',v_team.id));
 return jsonb_build_object('change_set_id',v_change_set_id,'builder_work_units',v_count,'status',case when v_count=0 then 'review_ready' else 'planned' end);
end;
$$;
revoke all on function public.factory_materialize_change_set(uuid) from public,anon,authenticated;
grant execute on function public.factory_materialize_change_set(uuid) to service_role;

create or replace function public.factory_bind_change_set_source(
 p_run_id uuid,p_source_commit text,p_integration_branch text,p_work_branch text
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_unit public.factory_change_set_work_units%rowtype;v_set public.factory_change_sets%rowtype;
begin
 if nullif(btrim(p_source_commit),'') is null then raise exception 'source commit required'; end if;
 if nullif(btrim(p_integration_branch),'') is null then raise exception 'integration branch required'; end if;
 if nullif(btrim(p_work_branch),'') is null then raise exception 'work branch required'; end if;
 select * into v_unit from public.factory_change_set_work_units where run_id=p_run_id for update;
 if not found then raise exception 'change-set work unit not found'; end if;
 select * into v_set from public.factory_change_sets where id=v_unit.change_set_id for update;
 if v_set.source_commit is null then
   update public.factory_change_sets set source_commit=p_source_commit,candidate_commit=p_source_commit,
     integration_branch=p_integration_branch,status='building',updated_at=now()
   where id=v_set.id;
   v_set.source_commit:=p_source_commit;v_set.candidate_commit:=p_source_commit;v_set.integration_branch:=p_integration_branch;
 elsif v_set.source_commit<>p_source_commit then
   raise exception 'change-set source commit mismatch';
 elsif v_set.integration_branch<>p_integration_branch then
   raise exception 'change-set integration branch mismatch';
 end if;
 if v_unit.wave<>v_set.current_wave then raise exception 'work unit is not in current wave'; end if;
 update public.factory_change_set_work_units
 set base_commit=v_set.candidate_commit,branch_name=p_work_branch,status='running',updated_at=now()
 where id=v_unit.id;
 return jsonb_build_object('change_set_id',v_set.id,'work_unit_id',v_unit.id,'base_commit',v_set.candidate_commit,
   'source_commit',v_set.source_commit,'integration_branch',v_set.integration_branch,'wave',v_unit.wave);
end;
$$;
revoke all on function public.factory_bind_change_set_source(uuid,text,text,text) from public,anon,authenticated;
grant execute on function public.factory_bind_change_set_source(uuid,text,text,text) to service_role;

create or replace function public.factory_complete_change_set_work_unit(
 p_run_id uuid,p_output_commit text,p_changed_files jsonb
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_unit public.factory_change_set_work_units%rowtype;
begin
 if nullif(btrim(p_output_commit),'') is null then raise exception 'output commit required'; end if;
 if jsonb_typeof(coalesce(p_changed_files,'[]'::jsonb))<>'array' then raise exception 'changed files must be array'; end if;
 select * into v_unit from public.factory_change_set_work_units where run_id=p_run_id for update;
 if not found then raise exception 'change-set work unit not found'; end if;
 if v_unit.status<>'running' then raise exception 'work unit is not running'; end if;
 update public.factory_change_set_work_units
 set status='completed',output_commit=p_output_commit,changed_files=coalesce(p_changed_files,'[]'::jsonb),updated_at=now()
 where id=v_unit.id;
 update public.factory_runs set status='completed',candidate_commit=p_output_commit,finished_at=now(),lease_owner=null,lease_expires_at=null where id=p_run_id;
 update public.factory_tasks set status='work_unit_completed',updated_at=now() where id=v_unit.task_id;
 return jsonb_build_object('change_set_id',v_unit.change_set_id,'work_unit_id',v_unit.id,'status','completed');
end;
$$;
revoke all on function public.factory_complete_change_set_work_unit(uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.factory_complete_change_set_work_unit(uuid,text,jsonb) to service_role;

create or replace function public.factory_claim_change_set_integration(p_worker_id text,p_lease_seconds integer default 600)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_set public.factory_change_sets%rowtype;v_project public.factory_projects%rowtype;v_units jsonb;
begin
 if nullif(btrim(p_worker_id),'') is null then raise exception 'worker id required'; end if;
 select s.* into v_set
 from public.factory_change_sets s
 where s.status in ('building','integrating')
   and s.attempt_count < 3
   and (s.lease_expires_at is null or s.lease_expires_at<=now())
   and exists(select 1 from public.factory_change_set_work_units u where u.change_set_id=s.id and u.wave=s.current_wave)
   and not exists(select 1 from public.factory_change_set_work_units u where u.change_set_id=s.id and u.wave=s.current_wave and u.status<>'completed')
 order by s.created_at
 for update skip locked limit 1;
 if not found then return null; end if;
 select * into v_project from public.factory_projects where id=v_set.project_id;
 select jsonb_agg(jsonb_build_object(
   'work_unit_id',u.id,'task_id',u.task_id,'plan_task_key',u.plan_task_key,'agent_key',u.agent_key,
   'base_commit',u.base_commit,'branch_name',u.branch_name,'output_commit',u.output_commit,'changed_files',u.changed_files
 ) order by u.plan_task_key) into v_units
 from public.factory_change_set_work_units u
 where u.change_set_id=v_set.id and u.wave=v_set.current_wave and u.status='completed';
 update public.factory_change_sets set status='integrating',lease_owner=p_worker_id,
   lease_expires_at=now()+make_interval(secs=>p_lease_seconds),attempt_count=attempt_count+1,updated_at=now()
 where id=v_set.id;
 return jsonb_build_object('change_set_id',v_set.id,'project_key',v_project.project_key,'repository',v_project.repository,
   'source_commit',v_set.source_commit,'candidate_commit',v_set.candidate_commit,'integration_branch',v_set.integration_branch,
   'current_wave',v_set.current_wave,'work_units',coalesce(v_units,'[]'::jsonb));
end;
$$;
revoke all on function public.factory_claim_change_set_integration(text,integer) from public,anon,authenticated;
grant execute on function public.factory_claim_change_set_integration(text,integer) to service_role;

create or replace function public.factory_complete_change_set_integration(
 p_change_set_id uuid,p_candidate_commit text,p_changed_files jsonb
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_set public.factory_change_sets%rowtype;v_next_wave integer;v_status text;
begin
 if nullif(btrim(p_candidate_commit),'') is null then raise exception 'candidate commit required'; end if;
 select * into v_set from public.factory_change_sets where id=p_change_set_id for update;
 if not found then raise exception 'change set not found'; end if;
 if v_set.status<>'integrating' then raise exception 'change set is not integrating'; end if;
 update public.factory_change_set_work_units set status='integrated',updated_at=now()
 where change_set_id=v_set.id and wave=v_set.current_wave and status='completed';
 update public.factory_tasks t set status='integrated',updated_at=now()
 where exists(
   select 1 from public.factory_change_set_work_units u
   where u.change_set_id=v_set.id and u.wave=v_set.current_wave and u.task_id=t.id and u.status='integrated'
 );
 select min(wave) into v_next_wave from public.factory_change_set_work_units where change_set_id=v_set.id and status='pending';
 if v_next_wave is null then
   v_status:='review_ready';
   update public.factory_change_sets set status=v_status,candidate_commit=p_candidate_commit,
     lease_owner=null,lease_expires_at=null,metadata=metadata||jsonb_build_object('integrated_files',coalesce(p_changed_files,'[]'::jsonb)),updated_at=now()
   where id=v_set.id;
 else
   v_status:='building';
   update public.factory_change_sets set status=v_status,candidate_commit=p_candidate_commit,current_wave=v_next_wave,
     lease_owner=null,lease_expires_at=null,updated_at=now()
   where id=v_set.id;
 end if;
 return jsonb_build_object('change_set_id',v_set.id,'status',v_status,'candidate_commit',p_candidate_commit,'current_wave',coalesce(v_next_wave,v_set.current_wave));
end;
$$;
revoke all on function public.factory_complete_change_set_integration(uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.factory_complete_change_set_integration(uuid,text,jsonb) to service_role;

create or replace function public.factory_dispatch_next_planned_task(p_project_key text)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_project_id uuid;v_team_status text;v_task public.factory_tasks%rowtype;v_run_id uuid;v_unit public.factory_change_set_work_units%rowtype;v_set public.factory_change_sets%rowtype;
begin
 select id into v_project_id from public.factory_projects where project_key=btrim(p_project_key) and is_active=true;
 if v_project_id is null then raise exception 'active project not found'; end if;
 select status into v_team_status from public.factory_execution_team_plans where project_id=v_project_id order by version desc limit 1;
 if v_team_status is distinct from 'ready' then return null; end if;
 select u.* into v_unit
 from public.factory_change_set_work_units u join public.factory_change_sets s on s.id=u.change_set_id
 where s.project_id=v_project_id and s.status in ('planned','building') and u.status='pending' and u.wave=s.current_wave
 order by u.created_at for update of u skip locked limit 1;
 if v_unit.id is null then return null; end if;
 select * into v_set from public.factory_change_sets where id=v_unit.change_set_id;
 select * into v_task from public.factory_tasks where id=v_unit.task_id for update;
 insert into public.factory_runs(task_id,status,metadata)
 values(v_task.id,'created',jsonb_build_object('dispatch_pending',true,'source','change-set','change_set_id',v_set.id,'work_unit_id',v_unit.id,'wave',v_unit.wave))
 returning id into v_run_id;
 update public.factory_tasks set status='dispatching',updated_at=now() where id=v_task.id;
 update public.factory_change_set_work_units set status='queued',run_id=v_run_id,updated_at=now() where id=v_unit.id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project_id,v_task.id,v_run_id,'system','backlog-dispatcher','change_set.work_unit.dispatched',
   jsonb_build_object('change_set_id',v_set.id,'work_unit_id',v_unit.id,'wave',v_unit.wave,'team_plan_status',v_team_status));
 return jsonb_build_object(
  'run_id',v_run_id,'task_id',v_task.id,'project_id',v_project_id,'project_key',p_project_key,
  'title',v_task.title,'description',v_task.description,'complexity',v_task.complexity,'risk',v_task.risk,
  'metadata',jsonb_build_object('acceptance_criteria',v_task.acceptance_criteria,'depends_on',v_task.depends_on,
    'change_set_id',v_set.id,'work_unit_id',v_unit.id,'wave',v_unit.wave,'agent_key',v_unit.agent_key)
 );
end;
$$;
revoke all on function public.factory_dispatch_next_planned_task(text) from public,anon,authenticated;
grant execute on function public.factory_dispatch_next_planned_task(text) to service_role;

create or replace function public.factory_claim_next_agent_direct_run(p_worker_id text,p_agent_key text default null,p_run_id uuid default null)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare v_run public.factory_runs%rowtype;v_task public.factory_tasks%rowtype;v_project public.factory_projects%rowtype;v_unit public.factory_change_set_work_units%rowtype;v_branch text;v_agent_key text;
begin
 if nullif(btrim(p_worker_id),'') is null then raise exception 'worker_id is required';end if;
 select r.* into v_run
 from public.factory_runs r
 join public.factory_tasks t on t.id=r.task_id
 join public.factory_run_agent_assignments ra on ra.run_id=r.id and ra.status in ('assigned','claimed')
 join public.factory_agents a2 on a2.id=ra.agent_id and a2.is_active=true
 where r.status='queued' and r.execution_route='direct' and t.status='queued_execution'
   and (p_agent_key is null or a2.agent_key=p_agent_key) and (p_run_id is null or r.id=p_run_id)
 order by r.created_at for update of r skip locked limit 1;
 if v_run.id is null then return null;end if;
 select a2.agent_key into v_agent_key from public.factory_run_agent_assignments ra
 join public.factory_agents a2 on a2.id=ra.agent_id and a2.is_active=true
 where ra.run_id=v_run.id and ra.status in ('assigned','claimed') order by ra.assigned_at desc limit 1;
 if v_agent_key is null then raise exception 'active agent assignment not found'; end if;
 select * into v_task from public.factory_tasks where id=v_run.task_id for update;
 select * into v_project from public.factory_projects where id=v_task.project_id;
 select * into v_unit from public.factory_change_set_work_units where run_id=v_run.id;
 if v_unit.id is null then raise exception 'change-set work unit not found'; end if;
 v_branch:='factory/cs-'||substr(v_unit.change_set_id::text,1,8)||'/'||regexp_replace(v_unit.plan_task_key,'[^a-zA-Z0-9_-]+','-','g');
 update public.factory_runs set status='implementing',started_at=coalesce(started_at,now()),lease_owner=p_worker_id,
  lease_expires_at=now()+interval '15 minutes',attempt_count=attempt_count+1,last_error=null,
  metadata=metadata||jsonb_build_object('execution_worker_id',p_worker_id,'execution_claimed_at',now(),'agent_key',v_agent_key)
 where id=v_run.id;
 update public.factory_tasks set status='implementing',updated_at=now() where id=v_task.id;
 update public.factory_run_agent_assignments set status='claimed',claimed_at=coalesce(claimed_at,now()) where run_id=v_run.id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,v_task.id,v_run.id,'agent',v_agent_key,'execution.direct.claimed',
   jsonb_build_object('lease_minutes',15,'worker_id',p_worker_id,'change_set_id',v_unit.change_set_id,'work_unit_id',v_unit.id));
 return jsonb_build_object('run_id',v_run.id,'task_id',v_task.id,'project_key',v_project.project_key,'repository',v_project.repository,
  'issue_number',null,'title',v_task.title,'description',v_task.description,'branch',v_branch,'agent_key',v_agent_key,
  'change_set_id',v_unit.change_set_id,'work_unit_id',v_unit.id,'wave',v_unit.wave,
  'human_gate_required',coalesce((v_run.metadata->>'human_gate_required')::boolean,false));
end;$$;
revoke all on function public.factory_claim_next_agent_direct_run(text,text,uuid) from public,anon,authenticated;
grant execute on function public.factory_claim_next_agent_direct_run(text,text,uuid) to service_role;

create or replace function public.factory_claim_next_agent_codex_run(p_worker_id text,p_agent_key text default null,p_run_id uuid default null)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare v_run public.factory_runs%rowtype;v_task public.factory_tasks%rowtype;v_project public.factory_projects%rowtype;v_unit public.factory_change_set_work_units%rowtype;v_branch text;v_agent_key text;
begin
 if nullif(btrim(p_worker_id),'') is null then raise exception 'worker_id is required';end if;
 select r.* into v_run from public.factory_runs r
 join public.factory_tasks t on t.id=r.task_id
 join public.factory_run_agent_assignments ra on ra.run_id=r.id and ra.status in ('assigned','claimed')
 join public.factory_agents a2 on a2.id=ra.agent_id and a2.is_active=true
 where r.status='queued' and r.execution_route='codex' and t.status='queued_execution'
   and (p_agent_key is null or a2.agent_key=p_agent_key) and (p_run_id is null or r.id=p_run_id)
 order by r.created_at for update of r skip locked limit 1;
 if v_run.id is null then return null;end if;
 select a2.agent_key into v_agent_key from public.factory_run_agent_assignments ra
 join public.factory_agents a2 on a2.id=ra.agent_id and a2.is_active=true
 where ra.run_id=v_run.id and ra.status in ('assigned','claimed') order by ra.assigned_at desc limit 1;
 if v_agent_key is null then raise exception 'active agent assignment not found'; end if;
 select * into v_task from public.factory_tasks where id=v_run.task_id for update;
 select * into v_project from public.factory_projects where id=v_task.project_id;
 select * into v_unit from public.factory_change_set_work_units where run_id=v_run.id;
 if v_unit.id is null then raise exception 'change-set work unit not found'; end if;
 v_branch:='factory/cs-'||substr(v_unit.change_set_id::text,1,8)||'/'||regexp_replace(v_unit.plan_task_key,'[^a-zA-Z0-9_-]+','-','g');
 update public.factory_runs set status='implementing',started_at=coalesce(started_at,now()),lease_owner=p_worker_id,
  lease_expires_at=now()+interval '15 minutes',attempt_count=attempt_count+1,last_error=null,
  metadata=metadata||jsonb_build_object('execution_worker_id',p_worker_id,'execution_claimed_at',now(),'agent_key',v_agent_key)
 where id=v_run.id;
 update public.factory_tasks set status='implementing',updated_at=now() where id=v_task.id;
 update public.factory_run_agent_assignments set status='claimed',claimed_at=coalesce(claimed_at,now()) where run_id=v_run.id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,v_task.id,v_run.id,'agent',v_agent_key,'execution.codex.claimed',
   jsonb_build_object('lease_minutes',15,'worker_id',p_worker_id,'change_set_id',v_unit.change_set_id,'work_unit_id',v_unit.id));
 return jsonb_build_object('run_id',v_run.id,'task_id',v_task.id,'project_key',v_project.project_key,'repository',v_project.repository,
  'issue_number',null,'title',v_task.title,'description',v_task.description,'branch',v_branch,'agent_key',v_agent_key,
  'change_set_id',v_unit.change_set_id,'work_unit_id',v_unit.id,'wave',v_unit.wave,
  'codex_level',coalesce((v_run.metadata->>'codex_level')::int,1),
  'human_gate_required',coalesce((v_run.metadata->>'human_gate_required')::boolean,false));
end;$$;
revoke all on function public.factory_claim_next_agent_codex_run(text,text,uuid) from public,anon,authenticated;
grant execute on function public.factory_claim_next_agent_codex_run(text,text,uuid) to service_role;

create or replace function public.factory_prepare_change_set_release(
 p_change_set_id uuid,p_issue_number integer,p_issue_url text,p_pr_number integer,p_candidate_commit text,p_branch text
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_set public.factory_change_sets%rowtype;v_run_id uuid;
begin
 if p_issue_number<1 or p_pr_number<1 then raise exception 'valid issue and PR numbers are required'; end if;
 select * into v_set from public.factory_change_sets where id=p_change_set_id for update;
 if not found then raise exception 'change set not found'; end if;
 if v_set.status<>'review_ready' then raise exception 'change set is not review ready'; end if;
 if v_set.candidate_commit is distinct from p_candidate_commit then raise exception 'release candidate mismatch'; end if;
 insert into public.factory_runs(task_id,status,candidate_commit,branch_name,metadata)
 values(v_set.root_task_id,'ci_pending',p_candidate_commit,p_branch,
   jsonb_build_object('source','change-set','change_set_id',v_set.id,'github_issue',jsonb_build_object('number',p_issue_number,'url',p_issue_url),'human_gate_required',false))
 returning id into v_run_id;
 insert into public.factory_tool_usage(run_id,tool_family,operation,usage_units,estimated_cost,metadata)
 values(v_run_id,'github','create_pr',1,0,jsonb_build_object('pr',p_pr_number,'head_sha',p_candidate_commit,'change_set_id',v_set.id));
 update public.factory_change_sets set status='ci_pending',release_run_id=v_run_id,updated_at=now() where id=v_set.id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_set.project_id,v_set.root_task_id,v_run_id,'system','change-set-integrator','change_set.release_candidate.created',
   jsonb_build_object('change_set_id',v_set.id,'pr',p_pr_number,'candidate_commit',p_candidate_commit,'branch',p_branch));
 return jsonb_build_object('change_set_id',v_set.id,'release_run_id',v_run_id,'status','ci_pending');
end;
$$;
revoke all on function public.factory_prepare_change_set_release(uuid,integer,text,integer,text,text) from public,anon,authenticated;
grant execute on function public.factory_prepare_change_set_release(uuid,integer,text,integer,text,text) to service_role;


create or replace function public.factory_recover_change_sets(p_max_attempts integer default 3)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_requeued integer:=0;v_blocked integer:=0;v_integrators integer:=0;
begin
 if p_max_attempts<1 or p_max_attempts>10 then raise exception 'invalid max attempts'; end if;

 update public.factory_change_set_work_units u
 set status='queued',updated_at=now()
 from public.factory_runs r
 where u.run_id=r.id and u.status='running' and r.status='queued';
 get diagnostics v_requeued=row_count;

 update public.factory_change_set_work_units u
 set status='failed',updated_at=now()
 from public.factory_runs r
 where u.run_id=r.id and u.status in ('running','queued') and r.status='failed';

 update public.factory_change_sets s
 set status='blocked',lease_owner=null,lease_expires_at=null,updated_at=now(),
     metadata=metadata||jsonb_build_object('blocker','builder_retry_exhausted')
 where s.status in ('planned','building','integrating')
   and exists(select 1 from public.factory_change_set_work_units u where u.change_set_id=s.id and u.status in ('failed','blocked'));
 get diagnostics v_blocked=row_count;

 update public.factory_change_sets
 set status='building',lease_owner=null,lease_expires_at=null,updated_at=now()
 where status='integrating' and lease_expires_at<=now() and attempt_count<p_max_attempts;
 get diagnostics v_integrators=row_count;

 update public.factory_change_sets
 set status='blocked',lease_owner=null,lease_expires_at=null,updated_at=now(),
     metadata=metadata||jsonb_build_object('blocker','integration_retry_exhausted')
 where status='integrating' and lease_expires_at<=now() and attempt_count>=p_max_attempts;
 get diagnostics v_blocked=v_blocked+row_count;

 return jsonb_build_object('work_units_requeued',v_requeued,'integrations_requeued',v_integrators,'blocked',v_blocked);
end;
$$;
revoke all on function public.factory_recover_change_sets(integer) from public,anon,authenticated;
grant execute on function public.factory_recover_change_sets(integer) to service_role;
