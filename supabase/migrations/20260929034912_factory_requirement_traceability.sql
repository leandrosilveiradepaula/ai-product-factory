create table if not exists public.factory_requirements (
 id uuid primary key default gen_random_uuid(),
 project_id uuid not null references public.factory_projects(id) on delete cascade,
 requirement_key text not null,
 statement text not null,
 source_ref text not null,
 status text not null default 'active' check (status in ('active','superseded')),
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 unique(project_id,requirement_key)
);
create index if not exists idx_factory_requirements_project_status
 on public.factory_requirements(project_id,status,requirement_key);
alter table public.factory_requirements enable row level security;
revoke all on public.factory_requirements from public,anon,authenticated;
grant select,insert,update on public.factory_requirements to service_role;

create table if not exists public.factory_requirement_task_links (
 requirement_id uuid not null references public.factory_requirements(id) on delete cascade,
 task_id uuid not null references public.factory_tasks(id) on delete cascade,
 task_key text not null,
 created_at timestamptz not null default now(),
 primary key(requirement_id,task_id)
);
create index if not exists idx_factory_requirement_task_links_task
 on public.factory_requirement_task_links(task_id,requirement_id);
alter table public.factory_requirement_task_links enable row level security;
revoke all on public.factory_requirement_task_links from public,anon,authenticated;
grant select,insert,delete on public.factory_requirement_task_links to service_role;

create table if not exists public.factory_requirement_evidence (
 id uuid primary key default gen_random_uuid(),
 requirement_id uuid not null references public.factory_requirements(id) on delete cascade,
 run_id uuid references public.factory_runs(id) on delete set null,
 evidence_type text not null,
 status text not null check (status in ('passed','failed','blocked','observed')),
 evidence_ref text not null,
 metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(),
 unique(requirement_id,evidence_type,evidence_ref)
);
create index if not exists idx_factory_requirement_evidence_requirement
 on public.factory_requirement_evidence(requirement_id,created_at desc);
alter table public.factory_requirement_evidence enable row level security;
revoke all on public.factory_requirement_evidence from public,anon,authenticated;
grant select,insert,update on public.factory_requirement_evidence to service_role;

create table if not exists public.factory_definitions_of_done (
 id uuid primary key default gen_random_uuid(),
 project_id uuid not null references public.factory_projects(id) on delete cascade,
 source_run_id uuid not null references public.factory_runs(id) on delete cascade,
 change_set_id uuid references public.factory_change_sets(id) on delete set null,
 version integer not null,
 status text not null check (status in ('current','superseded')),
 checks jsonb not null,
 created_at timestamptz not null default now(),
 unique(project_id,version)
);
create index if not exists idx_factory_dod_project_version
 on public.factory_definitions_of_done(project_id,version desc);
alter table public.factory_definitions_of_done enable row level security;
revoke all on public.factory_definitions_of_done from public,anon,authenticated;
grant select,insert,update on public.factory_definitions_of_done to service_role;

create table if not exists public.factory_definition_of_done_evidence (
 id uuid primary key default gen_random_uuid(),
 definition_id uuid not null references public.factory_definitions_of_done(id) on delete cascade,
 run_id uuid references public.factory_runs(id) on delete set null,
 check_key text not null,
 evidence_type text not null,
 status text not null check (status in ('passed','failed','blocked','observed')),
 evidence_ref text not null,
 metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(),
 unique(definition_id,check_key,evidence_ref)
);
create index if not exists idx_factory_dod_evidence_definition
 on public.factory_definition_of_done_evidence(definition_id,created_at desc);
alter table public.factory_definition_of_done_evidence enable row level security;
revoke all on public.factory_definition_of_done_evidence from public,anon,authenticated;
grant select,insert,update on public.factory_definition_of_done_evidence to service_role;

create or replace function public.factory_record_requirement_trace(
 p_project_id uuid,
 p_source_run_id uuid,
 p_source_ref text,
 p_requirements jsonb
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
 v_locked uuid;
 v_item jsonb;
 v_req_id uuid;
 v_task_id uuid;
 v_total integer:=0;
 v_linked integer:=0;
begin
 if jsonb_typeof(coalesce(p_requirements,'[]'::jsonb))<>'array' then
  raise exception 'requirements must be array';
 end if;
 if nullif(btrim(p_source_ref),'') is null then raise exception 'source_ref required'; end if;
 select id into v_locked from public.factory_projects where id=p_project_id for update;
 if v_locked is null then raise exception 'project not found'; end if;
 if not exists(
  select 1 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
  where r.id=p_source_run_id and t.project_id=p_project_id
 ) then raise exception 'source run does not belong to project'; end if;

 update public.factory_requirements set status='superseded',updated_at=now()
 where project_id=p_project_id and status='active';

 for v_item in select value from jsonb_array_elements(coalesce(p_requirements,'[]'::jsonb))
 loop
  if nullif(btrim(v_item->>'requirement_key'),'') is null then raise exception 'requirement_key required'; end if;
  if nullif(btrim(v_item->>'statement'),'') is null then raise exception 'requirement statement required'; end if;
  if nullif(btrim(v_item->>'task_external_key'),'') is null then raise exception 'task_external_key required'; end if;

  insert into public.factory_requirements(project_id,requirement_key,statement,source_ref,status)
  values(p_project_id,v_item->>'requirement_key',v_item->>'statement',p_source_ref,'active')
  on conflict(project_id,requirement_key) do update set
   statement=excluded.statement,source_ref=excluded.source_ref,status='active',updated_at=now()
  returning id into v_req_id;

  delete from public.factory_requirement_task_links where requirement_id=v_req_id;
  select id into v_task_id from public.factory_tasks
   where project_id=p_project_id and external_key=v_item->>'task_external_key' limit 1;
  if v_task_id is not null then
   insert into public.factory_requirement_task_links(requirement_id,task_id,task_key)
   values(v_req_id,v_task_id,coalesce(nullif(v_item->>'task_key',''),v_item->>'task_external_key'))
   on conflict do nothing;
   v_linked:=v_linked+1;
  end if;
  v_total:=v_total+1;
 end loop;

 insert into public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
 values(p_project_id,p_source_run_id,'system','requirement-trace','requirements.trace.recorded',
  jsonb_build_object('source_ref',p_source_ref,'requirements',v_total,'linked',v_linked));

 return jsonb_build_object('requirements',v_total,'linked',v_linked,'unlinked',v_total-v_linked);
end;
$$;
revoke all on function public.factory_record_requirement_trace(uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.factory_record_requirement_trace(uuid,uuid,text,jsonb) to service_role;

create or replace function public.factory_record_definition_of_done(
 p_project_id uuid,
 p_source_run_id uuid,
 p_change_set_id uuid,
 p_checks jsonb
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
 v_locked uuid;
 v_version integer;
 v_id uuid;
 v_req_count integer;
 v_link_count integer;
 v_check jsonb;
begin
 if jsonb_typeof(coalesce(p_checks,'[]'::jsonb))<>'array' then raise exception 'checks must be array'; end if;
 select id into v_locked from public.factory_projects where id=p_project_id for update;
 if v_locked is null then raise exception 'project not found'; end if;
 if not exists(
  select 1 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
  where r.id=p_source_run_id and t.project_id=p_project_id
 ) then raise exception 'source run does not belong to project'; end if;
 if p_change_set_id is not null and not exists(
  select 1 from public.factory_change_sets where id=p_change_set_id and project_id=p_project_id
 ) then raise exception 'change set does not belong to project'; end if;

 select coalesce(max(version),0)+1 into v_version from public.factory_definitions_of_done where project_id=p_project_id;
 update public.factory_definitions_of_done set status='superseded'
 where project_id=p_project_id and status='current';
 insert into public.factory_definitions_of_done(project_id,source_run_id,change_set_id,version,status,checks)
 values(p_project_id,p_source_run_id,p_change_set_id,v_version,'current',coalesce(p_checks,'[]'::jsonb))
 returning id into v_id;

 select count(*) into v_req_count from public.factory_requirements where project_id=p_project_id and status='active';
 select count(distinct r.id) into v_link_count
 from public.factory_requirements r
 where r.project_id=p_project_id and r.status='active'
   and exists(select 1 from public.factory_requirement_task_links l where l.requirement_id=r.id);

 for v_check in select value from jsonb_array_elements(coalesce(p_checks,'[]'::jsonb))
 loop
  if nullif(btrim(v_check->>'key'),'') is null or nullif(btrim(v_check->>'evidence_type'),'') is null then
   raise exception 'DoD check key and evidence_type are required';
  end if;
  if v_check->>'evidence_type'='requirements_traceable' and v_req_count>0 and v_req_count=v_link_count then
   insert into public.factory_definition_of_done_evidence(
     definition_id,run_id,check_key,evidence_type,status,evidence_ref,metadata
   ) values(
     v_id,p_source_run_id,v_check->>'key','requirements_traceable','passed',
     'run:'||p_source_run_id::text||':planning',
     jsonb_build_object('requirements',v_req_count,'linked',v_link_count)
   ) on conflict do nothing;
  end if;
 end loop;

 insert into public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
 values(p_project_id,p_source_run_id,'system','definition-of-done','definition_of_done.recorded',
  jsonb_build_object('definition_id',v_id,'version',v_version,'check_count',jsonb_array_length(coalesce(p_checks,'[]'::jsonb))));

 return jsonb_build_object('id',v_id,'version',v_version,'check_count',jsonb_array_length(coalesce(p_checks,'[]'::jsonb)));
end;
$$;
revoke all on function public.factory_record_definition_of_done(uuid,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.factory_record_definition_of_done(uuid,uuid,uuid,jsonb) to service_role;

create or replace function public.factory_record_delivery_evidence(
 p_run_id uuid,
 p_evidence_type text,
 p_status text,
 p_evidence_ref text,
 p_metadata jsonb default '{}'::jsonb
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
 v_project_id uuid;
 v_task_id uuid;
 v_definition_id uuid;
 v_check jsonb;
 v_req record;
 v_req_count integer:=0;
 v_dod_count integer:=0;
begin
 if nullif(btrim(p_evidence_type),'') is null then raise exception 'evidence_type required'; end if;
 if p_status not in ('passed','failed','blocked','observed') then raise exception 'invalid evidence status'; end if;
 if nullif(btrim(p_evidence_ref),'') is null then raise exception 'evidence_ref required'; end if;
 if jsonb_typeof(coalesce(p_metadata,'{}'::jsonb))<>'object' then raise exception 'metadata must be object'; end if;
 if coalesce(p_metadata,'{}'::jsonb) ?| array['token','secret','password','api_key','authorization','credential'] then
  raise exception 'secret-like evidence metadata is forbidden';
 end if;

 select t.project_id,r.task_id into v_project_id,v_task_id
 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
 where r.id=p_run_id;
 if v_project_id is null then raise exception 'run not found'; end if;

 for v_req in
  select distinct req.id
  from public.factory_requirements req
  join public.factory_requirement_task_links l on l.requirement_id=req.id
  where req.project_id=v_project_id and req.status='active'
    and (
      l.task_id=v_task_id
      or l.task_id in (
        select u.task_id
        from public.factory_change_sets cs
        join public.factory_change_set_work_units u on u.change_set_id=cs.id
        where cs.release_run_id=p_run_id
      )
    )
 loop
  insert into public.factory_requirement_evidence(requirement_id,run_id,evidence_type,status,evidence_ref,metadata)
  values(v_req.id,p_run_id,p_evidence_type,p_status,p_evidence_ref,coalesce(p_metadata,'{}'::jsonb))
  on conflict(requirement_id,evidence_type,evidence_ref) do update set
   status=excluded.status,metadata=excluded.metadata;
  v_req_count:=v_req_count+1;
 end loop;

 select id into v_definition_id
 from public.factory_definitions_of_done
 where project_id=v_project_id and status='current'
 order by version desc limit 1;
 if v_definition_id is not null then
  for v_check in
   select value from jsonb_array_elements(
     (select checks from public.factory_definitions_of_done where id=v_definition_id)
   )
  loop
   if v_check->>'evidence_type'=p_evidence_type then
    insert into public.factory_definition_of_done_evidence(
      definition_id,run_id,check_key,evidence_type,status,evidence_ref,metadata
    ) values(
      v_definition_id,p_run_id,v_check->>'key',p_evidence_type,p_status,p_evidence_ref,coalesce(p_metadata,'{}'::jsonb)
    )
    on conflict(definition_id,check_key,evidence_ref) do update set
      status=excluded.status,metadata=excluded.metadata;
    v_dod_count:=v_dod_count+1;
   end if;
  end loop;
 end if;

 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project_id,v_task_id,p_run_id,'system','delivery-evidence','delivery.evidence.recorded',
  jsonb_build_object('evidence_type',p_evidence_type,'status',p_status,'evidence_ref',p_evidence_ref,
    'requirements_linked',v_req_count,'dod_checks_linked',v_dod_count));

 return jsonb_build_object('requirements_linked',v_req_count,'dod_checks_linked',v_dod_count);
end;
$$;
revoke all on function public.factory_record_delivery_evidence(uuid,text,text,text,jsonb) from public,anon,authenticated;
grant execute on function public.factory_record_delivery_evidence(uuid,text,text,text,jsonb) to service_role;

create or replace function public.factory_get_definition_of_done_readiness(p_project_id uuid)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
 v_definition public.factory_definitions_of_done%rowtype;
 v_check jsonb;
 v_missing jsonb:='[]'::jsonb;
 v_satisfied jsonb:='[]'::jsonb;
 v_has boolean;
begin
 select * into v_definition from public.factory_definitions_of_done
 where project_id=p_project_id and status='current' order by version desc limit 1;
 if not found then return jsonb_build_object('ready',false,'definition_id',null,'missing',jsonb_build_array('definition_of_done'),'satisfied','[]'::jsonb); end if;

 for v_check in select value from jsonb_array_elements(v_definition.checks)
 loop
  select exists(
    select 1 from public.factory_definition_of_done_evidence e
    where e.definition_id=v_definition.id
      and e.check_key=v_check->>'key'
      and e.evidence_type=v_check->>'evidence_type'
      and e.status='passed'
  ) into v_has;
  if v_has then
    v_satisfied:=v_satisfied||jsonb_build_array(v_check->>'key');
  else
    v_missing:=v_missing||jsonb_build_array(jsonb_build_object(
      'key',v_check->>'key','phase',v_check->>'phase','reason',v_check->>'reason',
      'evidence_type',v_check->>'evidence_type','human_only',coalesce((v_check->>'human_only')::boolean,false)
    ));
  end if;
 end loop;

 return jsonb_build_object(
  'ready',jsonb_array_length(v_missing)=0,
  'definition_id',v_definition.id,
  'version',v_definition.version,
  'satisfied',v_satisfied,
  'missing',v_missing
 );
end;
$$;
revoke all on function public.factory_get_definition_of_done_readiness(uuid) from public,anon,authenticated;
grant execute on function public.factory_get_definition_of_done_readiness(uuid) to service_role;

