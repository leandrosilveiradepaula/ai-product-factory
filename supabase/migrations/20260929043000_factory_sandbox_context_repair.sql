create table if not exists public.factory_work_unit_context_packets (
 id uuid primary key default gen_random_uuid(),
 project_id uuid not null references public.factory_projects(id) on delete cascade,
 run_id uuid not null references public.factory_runs(id) on delete cascade,
 change_set_id uuid not null references public.factory_change_sets(id) on delete cascade,
 work_unit_id uuid not null references public.factory_change_set_work_units(id) on delete cascade,
 version integer not null default 1,
 packet_hash text not null check (packet_hash ~ '^[0-9a-f]{64}$'),
 packet jsonb not null,
 created_at timestamptz not null default now(),
 unique(run_id,version)
);
alter table public.factory_work_unit_context_packets enable row level security;
revoke all on public.factory_work_unit_context_packets from public,anon,authenticated;
grant select,insert on public.factory_work_unit_context_packets to service_role;
create index if not exists idx_factory_context_packets_change_set on public.factory_work_unit_context_packets(change_set_id,created_at);

create table if not exists public.factory_repair_jobs (
 id uuid primary key default gen_random_uuid(),
 project_id uuid not null references public.factory_projects(id) on delete cascade,
 change_set_id uuid not null references public.factory_change_sets(id) on delete cascade,
 source_run_id uuid not null references public.factory_runs(id) on delete cascade,
 specialist_job_id uuid not null references public.factory_specialist_lane_jobs(id) on delete cascade,
 source_role text not null check (source_role in ('security','qa')),
 cycle integer not null check (cycle between 1 and 3),
 max_cycles integer not null default 3 check (max_cycles between 1 and 3),
 owner_agent_key text not null default 'development',
 candidate_commit text not null,
 finding jsonb not null,
 write_scopes jsonb not null default '[]'::jsonb,
 status text not null default 'queued' check (status in ('queued','running','integrated','passed','exhausted','blocked')),
 task_id uuid references public.factory_tasks(id) on delete set null,
 work_unit_id uuid references public.factory_change_set_work_units(id) on delete set null,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 unique(specialist_job_id,cycle)
);
alter table public.factory_repair_jobs enable row level security;
revoke all on public.factory_repair_jobs from public,anon,authenticated;
grant select,insert,update on public.factory_repair_jobs to service_role;
create index if not exists idx_factory_repair_jobs_change_set on public.factory_repair_jobs(change_set_id,status,created_at);

create or replace function public.factory_work_unit_context_source(p_run_id uuid)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
 v_run public.factory_runs%rowtype;
 v_task public.factory_tasks%rowtype;
 v_project public.factory_projects%rowtype;
 v_unit public.factory_change_set_work_units%rowtype;
 v_set public.factory_change_sets%rowtype;
 v_team public.factory_execution_team_plans%rowtype;
 v_assignment jsonb;
 v_repair jsonb;
begin
 select * into v_run from public.factory_runs where id=p_run_id;
 if not found then raise exception 'run not found'; end if;
 select * into v_task from public.factory_tasks where id=v_run.task_id;
 select * into v_project from public.factory_projects where id=v_task.project_id;
 select * into v_unit from public.factory_change_set_work_units where run_id=p_run_id;
 if not found then raise exception 'change-set work unit not found'; end if;
 select * into v_set from public.factory_change_sets where id=v_unit.change_set_id;
 select * into v_team from public.factory_execution_team_plans where id=v_set.team_plan_id;
 select value into v_assignment
 from jsonb_array_elements(coalesce(v_team.plan->'task_assignments','[]'::jsonb))
 where value->>'task_key'=v_unit.plan_task_key limit 1;
 select jsonb_build_object(
   'repair_job_id',r.id,'cycle',r.cycle,'max_cycles',r.max_cycles,'source_role',r.source_role,
   'finding',r.finding,'write_scopes',r.write_scopes,'candidate_commit',r.candidate_commit
 ) into v_repair
 from public.factory_repair_jobs r where r.work_unit_id=v_unit.id order by r.created_at desc limit 1;
 return jsonb_build_object(
  'project_key',v_project.project_key,'repository',v_project.repository,'change_set_id',v_set.id,
  'work_unit_id',v_unit.id,'plan_task_key',v_unit.plan_task_key,'agent_key',v_unit.agent_key,'wave',v_unit.wave,
  'task',jsonb_build_object('title',v_task.title,'description',v_task.description,'acceptance_criteria',v_task.acceptance_criteria),
  'assignment',coalesce(v_assignment,jsonb_build_object(
    'task_key',v_unit.plan_task_key,'agent_key',v_unit.agent_key,'scope_keys',coalesce(v_repair->'write_scopes','[]'::jsonb),
    'required_capabilities',jsonb_build_array('implementation'),'depends_on','[]'::jsonb
  )),
  'repair',coalesce(v_repair,'{}'::jsonb),
  'constraints',jsonb_build_array(
    'Never include secrets, credentials or tokens in model context.',
    'Write only inside the explicit work-unit scopes.',
    'Do not merge or publish production.'
  )
 );
end;
$$;
revoke all on function public.factory_work_unit_context_source(uuid) from public,anon,authenticated;
grant execute on function public.factory_work_unit_context_source(uuid) to service_role;

create or replace function public.factory_record_work_unit_context(
 p_run_id uuid,p_packet_hash text,p_packet jsonb
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_project_id uuid;v_change_set_id uuid;v_work_unit_id uuid;v_id uuid;
begin
 if p_packet_hash !~ '^[0-9a-f]{64}$' then raise exception 'invalid context packet hash'; end if;
 if jsonb_typeof(coalesce(p_packet,'{}'::jsonb))<>'object' then raise exception 'context packet must be object'; end if;
 if p_packet::text ~* '(sb_secret_|sk-(proj-)?[a-z0-9_-]{12,}|gh[pousr]_[a-z0-9]{12,}|BEGIN [A-Z ]*PRIVATE KEY|Bearer[[:space:]]+[A-Za-z0-9._~-]{16,})' then
   raise exception 'secret-like value rejected from context packet';
 end if;
 select t.project_id,u.change_set_id,u.id into v_project_id,v_change_set_id,v_work_unit_id
 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
 join public.factory_change_set_work_units u on u.run_id=r.id where r.id=p_run_id;
 if v_work_unit_id is null then raise exception 'work unit run not found'; end if;
 insert into public.factory_work_unit_context_packets(project_id,run_id,change_set_id,work_unit_id,version,packet_hash,packet)
 values(v_project_id,p_run_id,v_change_set_id,v_work_unit_id,1,p_packet_hash,p_packet)
 on conflict(run_id,version) do update set packet_hash=excluded.packet_hash,packet=excluded.packet
 returning id into v_id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 select v_project_id,r.task_id,p_run_id,'system','context-packet-builder','work_unit.context.recorded',
   jsonb_build_object('context_packet_id',v_id,'packet_hash',p_packet_hash,'change_set_id',v_change_set_id,'work_unit_id',v_work_unit_id)
 from public.factory_runs r where r.id=p_run_id;
 return jsonb_build_object('id',v_id,'packet_hash',p_packet_hash);
end;
$$;
revoke all on function public.factory_record_work_unit_context(uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.factory_record_work_unit_context(uuid,text,jsonb) to service_role;

create or replace function public.factory_enqueue_repair_from_specialist(p_job_id uuid,p_findings jsonb,p_max_cycles integer default 3)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
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
begin
 if p_max_cycles<1 or p_max_cycles>3 then raise exception 'repair max cycles must be between 1 and 3'; end if;
 if jsonb_typeof(coalesce(p_findings,'[]'::jsonb))<>'array' then raise exception 'findings must be array'; end if;
 select * into v_job from public.factory_specialist_lane_jobs where id=p_job_id for update;
 if not found then raise exception 'specialist job not found'; end if;
 if v_job.role not in ('security','qa') then
  return jsonb_build_object('created',false,'reason','role_not_auto_repairable');
 end if;
 select * into v_run from public.factory_runs where id=v_job.run_id;
 if coalesce(v_run.metadata->>'change_set_id','')='' then
  return jsonb_build_object('created',false,'reason','no_change_set');
 end if;
 select * into v_set from public.factory_change_sets where id=(v_run.metadata->>'change_set_id')::uuid for update;
 if not found then return jsonb_build_object('created',false,'reason','change_set_not_found'); end if;
 select count(*)+1 into v_cycle from public.factory_repair_jobs
 where change_set_id=v_set.id and source_role=v_job.role;
 if v_cycle>p_max_cycles then
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
$$;
revoke all on function public.factory_enqueue_repair_from_specialist(uuid,jsonb,integer) from public,anon,authenticated;
grant execute on function public.factory_enqueue_repair_from_specialist(uuid,jsonb,integer) to service_role;


create or replace function public.factory_set_repair_status(p_run_id uuid,p_status text)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_id uuid;
begin
 if p_status not in ('running','integrated','passed','exhausted','blocked') then raise exception 'invalid repair status'; end if;
 select r.id into v_id
 from public.factory_repair_jobs r
 join public.factory_change_set_work_units u on u.id=r.work_unit_id
 where u.run_id=p_run_id order by r.created_at desc limit 1;
 if v_id is null then return jsonb_build_object('updated',false); end if;
 update public.factory_repair_jobs set status=p_status,updated_at=now() where id=v_id;
 return jsonb_build_object('updated',true,'repair_job_id',v_id,'status',p_status);
end;
$$;
revoke all on function public.factory_set_repair_status(uuid,text) from public,anon,authenticated;
grant execute on function public.factory_set_repair_status(uuid,text) to service_role;

create or replace function public.factory_mark_repair_wave_integrated(
 p_change_set_id uuid,p_wave integer,p_candidate_commit text
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_count integer:=0;
begin
 if p_wave<1 then raise exception 'invalid wave'; end if;
 update public.factory_repair_jobs r
 set status='integrated',candidate_commit=p_candidate_commit,updated_at=now()
 from public.factory_change_set_work_units u
 where r.work_unit_id=u.id and r.change_set_id=p_change_set_id and u.wave=p_wave
   and r.status in ('queued','running');
 get diagnostics v_count=row_count;
 return jsonb_build_object('updated',v_count,'status','integrated','candidate_commit',p_candidate_commit);
end;
$$;
revoke all on function public.factory_mark_repair_wave_integrated(uuid,integer,text) from public,anon,authenticated;
grant execute on function public.factory_mark_repair_wave_integrated(uuid,integer,text) to service_role;
