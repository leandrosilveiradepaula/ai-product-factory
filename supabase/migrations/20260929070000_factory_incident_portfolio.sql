create table if not exists public.factory_project_scheduling (
 project_id uuid primary key references public.factory_projects(id) on delete cascade,
 priority text not null default 'P2' check (priority in ('P0','P1','P2','P3')),
 deadline timestamptz,
 customer_impact integer not null default 1 check (customer_impact between 0 and 5),
 max_active_workers integer not null default 4 check (max_active_workers between 1 and 32),
 paused boolean not null default false,
 note text,
 updated_at timestamptz not null default now()
);
alter table public.factory_project_scheduling enable row level security;
revoke all on public.factory_project_scheduling from public,anon,authenticated;
grant select,insert,update,delete on public.factory_project_scheduling to service_role;

create table if not exists public.factory_incidents (
 id uuid primary key default gen_random_uuid(),
 project_id uuid not null references public.factory_projects(id) on delete cascade,
 severity text not null check (severity in ('P0','P1','P2','P3')),
 status text not null default 'triage' check (status in (
   'triage','investigating','evidence','repair','targeted_validation','full_gates','resolved','blocked'
 )),
 title text not null,
 summary text not null,
 metadata jsonb not null default '{}'::jsonb,
 opened_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 resolved_at timestamptz
);
alter table public.factory_incidents enable row level security;
revoke all on public.factory_incidents from public,anon,authenticated;
grant select,insert,update,delete on public.factory_incidents to service_role;
create index if not exists idx_factory_incidents_project_status
 on public.factory_incidents(project_id,status,severity,opened_at);

create table if not exists public.factory_portfolio_decisions (
 id bigserial primary key,
 selected_project_id uuid references public.factory_projects(id) on delete set null,
 candidates jsonb not null default '[]'::jsonb,
 reason jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now()
);
alter table public.factory_portfolio_decisions enable row level security;
revoke all on public.factory_portfolio_decisions from public,anon,authenticated;
grant select,insert on public.factory_portfolio_decisions to service_role;

create or replace function public.factory_set_project_scheduling(
 p_project_key text,p_priority text default 'P2',p_deadline timestamptz default null,
 p_customer_impact integer default 1,p_max_active_workers integer default 4,
 p_paused boolean default false,p_note text default null
) returns jsonb
language plpgsql security invoker set search_path=''
as $$
declare v_project_id uuid;
begin
 if p_priority not in ('P0','P1','P2','P3') then raise exception 'invalid priority'; end if;
 if p_customer_impact<0 or p_customer_impact>5 then raise exception 'invalid customer impact'; end if;
 if p_max_active_workers<1 or p_max_active_workers>32 then raise exception 'invalid max active workers'; end if;
 select id into v_project_id from public.factory_projects where project_key=btrim(p_project_key) and is_active=true;
 if v_project_id is null then raise exception 'active project not found'; end if;
 insert into public.factory_project_scheduling(project_id,priority,deadline,customer_impact,max_active_workers,paused,note)
 values(v_project_id,p_priority,p_deadline,p_customer_impact,p_max_active_workers,p_paused,p_note)
 on conflict(project_id) do update set priority=excluded.priority,deadline=excluded.deadline,
   customer_impact=excluded.customer_impact,max_active_workers=excluded.max_active_workers,
   paused=excluded.paused,note=excluded.note,updated_at=now();
 return jsonb_build_object('project_id',v_project_id,'project_key',p_project_key,'priority',p_priority,
   'deadline',p_deadline,'customer_impact',p_customer_impact,'max_active_workers',p_max_active_workers,'paused',p_paused);
end;
$$;
revoke all on function public.factory_set_project_scheduling(text,text,timestamptz,integer,integer,boolean,text) from public,anon,authenticated;
grant execute on function public.factory_set_project_scheduling(text,text,timestamptz,integer,integer,boolean,text) to service_role;

create or replace function public.factory_open_incident(
 p_project_key text,p_severity text,p_title text,p_summary text,p_metadata jsonb default '{}'::jsonb
) returns jsonb
language plpgsql security invoker set search_path=''
as $$
declare v_project_id uuid;v_id uuid;
begin
 if p_severity not in ('P0','P1','P2','P3') then raise exception 'invalid incident severity'; end if;
 if nullif(btrim(p_title),'') is null or nullif(btrim(p_summary),'') is null then raise exception 'incident title and summary required'; end if;
 if jsonb_typeof(coalesce(p_metadata,'{}'::jsonb))<>'object' then raise exception 'incident metadata must be object'; end if;
 select id into v_project_id from public.factory_projects where project_key=btrim(p_project_key) and is_active=true;
 if v_project_id is null then raise exception 'active project not found'; end if;
 insert into public.factory_incidents(project_id,severity,title,summary,metadata)
 values(v_project_id,p_severity,btrim(p_title),btrim(p_summary),coalesce(p_metadata,'{}'::jsonb))
 returning id into v_id;
 insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
 values(v_project_id,'system','incident-controller','incident.opened',
   jsonb_build_object('incident_id',v_id,'severity',p_severity,'title',btrim(p_title)));
 return jsonb_build_object('incident_id',v_id,'project_id',v_project_id,'status','triage','severity',p_severity);
end;
$$;
revoke all on function public.factory_open_incident(text,text,text,text,jsonb) from public,anon,authenticated;
grant execute on function public.factory_open_incident(text,text,text,text,jsonb) to service_role;

create or replace function public.factory_transition_incident(
 p_incident_id uuid,p_to_status text,p_evidence jsonb default '{}'::jsonb
) returns jsonb
language plpgsql security invoker set search_path=''
as $$
declare v_inc public.factory_incidents%rowtype;v_allowed boolean:=false;
begin
 if jsonb_typeof(coalesce(p_evidence,'{}'::jsonb))<>'object' then raise exception 'incident evidence must be object'; end if;
 select * into v_inc from public.factory_incidents where id=p_incident_id for update;
 if not found then raise exception 'incident not found'; end if;
 v_allowed:=case v_inc.status
   when 'triage' then p_to_status in ('investigating','blocked')
   when 'investigating' then p_to_status in ('evidence','blocked')
   when 'evidence' then p_to_status in ('repair','targeted_validation','blocked')
   when 'repair' then p_to_status in ('targeted_validation','blocked')
   when 'targeted_validation' then p_to_status in ('full_gates','repair','blocked')
   when 'full_gates' then p_to_status in ('resolved','repair','blocked')
   when 'blocked' then p_to_status in ('triage','investigating')
   else false end;
 if not v_allowed then raise exception 'invalid incident transition from % to %',v_inc.status,p_to_status; end if;
 if p_to_status='resolved' and v_inc.status<>'full_gates' then raise exception 'incident resolution requires full gates'; end if;
 update public.factory_incidents
 set status=p_to_status,metadata=metadata||jsonb_build_object('last_evidence',coalesce(p_evidence,'{}'::jsonb)),
   updated_at=now(),resolved_at=case when p_to_status='resolved' then now() else null end
 where id=p_incident_id;
 insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
 values(v_inc.project_id,'system','incident-controller','incident.transitioned',
   jsonb_build_object('incident_id',p_incident_id,'from',v_inc.status,'to',p_to_status,'evidence',coalesce(p_evidence,'{}'::jsonb)));
 return jsonb_build_object('incident_id',p_incident_id,'from',v_inc.status,'status',p_to_status);
end;
$$;
revoke all on function public.factory_transition_incident(uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.factory_transition_incident(uuid,text,jsonb) to service_role;

create or replace function public.factory_portfolio_candidates(p_limit integer default 20)
returns jsonb
language plpgsql security invoker set search_path=''
as $$
declare v_has_p0 boolean;v_rows jsonb;
begin
 if p_limit<1 or p_limit>100 then raise exception 'invalid portfolio candidate limit'; end if;
 select exists(
   select 1 from public.factory_incidents i
   where i.severity='P0' and i.status not in ('resolved','blocked')
 ) into v_has_p0;
 with project_state as (
  select
   p.id,p.project_key,
   coalesce(s.priority,'P2') priority,s.deadline,coalesce(s.customer_impact,1) customer_impact,
   coalesce(s.max_active_workers,4) max_active_workers,coalesce(s.paused,false) paused,
   min(case i.severity when 'P0' then 0 when 'P1' then 1 when 'P2' then 2 when 'P3' then 3 else 9 end)
     filter(where i.status not in ('resolved','blocked')) incident_rank,
   count(distinct r.id) filter(where r.status in ('queued','implementing','ci_pending','specialist_review_pending','preview_ready','repair_pending')) active_runs,
   exists(
    select 1 from public.factory_change_sets cs
    join public.factory_change_set_work_units u on u.change_set_id=cs.id
    where cs.project_id=p.id and cs.status in ('planned','building')
      and u.status='pending' and u.wave=cs.current_wave
   ) has_runnable_work
  from public.factory_projects p
  left join public.factory_project_scheduling s on s.project_id=p.id
  left join public.factory_incidents i on i.project_id=p.id
  left join public.factory_tasks t on t.project_id=p.id
  left join public.factory_runs r on r.task_id=t.id
  where p.is_active=true
  group by p.id,p.project_key,s.priority,s.deadline,s.customer_impact,s.max_active_workers,s.paused
 ), eligible as (
  select *,case priority when 'P0' then 0 when 'P1' then 1 when 'P2' then 2 else 3 end priority_rank
  from project_state
  where has_runnable_work and not paused and active_runs<max_active_workers
    and (not v_has_p0 or incident_rank=0)
 )
 select coalesce(jsonb_agg(jsonb_build_object(
   'project_id',id,'project_key',project_key,'priority',priority,'deadline',deadline,
   'customer_impact',customer_impact,'max_active_workers',max_active_workers,'active_runs',active_runs,
   'open_incident_severity',case incident_rank when 0 then 'P0' when 1 then 'P1' when 2 then 'P2' when 3 then 'P3' else null end,
   'soft_preemption_active',v_has_p0
 ) order by coalesce(incident_rank,9),priority_rank,deadline nulls last,customer_impact desc,project_key)
 , '[]'::jsonb) into v_rows
 from (select * from eligible order by coalesce(incident_rank,9),priority_rank,deadline nulls last,customer_impact desc,project_key limit p_limit) q;
 return v_rows;
end;
$$;
revoke all on function public.factory_portfolio_candidates(integer) from public,anon,authenticated;
grant execute on function public.factory_portfolio_candidates(integer) to service_role;

create or replace function public.factory_record_portfolio_decision(
 p_selected_project_key text,p_candidates jsonb,p_reason jsonb
) returns jsonb
language plpgsql security invoker set search_path=''
as $$
declare v_project_id uuid;v_id bigint;
begin
 if jsonb_typeof(coalesce(p_candidates,'[]'::jsonb))<>'array' then raise exception 'candidates must be array'; end if;
 if jsonb_typeof(coalesce(p_reason,'{}'::jsonb))<>'object' then raise exception 'reason must be object'; end if;
 if nullif(btrim(p_selected_project_key),'') is not null then
   select id into v_project_id from public.factory_projects where project_key=btrim(p_selected_project_key);
 end if;
 insert into public.factory_portfolio_decisions(selected_project_id,candidates,reason)
 values(v_project_id,coalesce(p_candidates,'[]'::jsonb),coalesce(p_reason,'{}'::jsonb)) returning id into v_id;
 return jsonb_build_object('decision_id',v_id,'selected_project_id',v_project_id);
end;
$$;
revoke all on function public.factory_record_portfolio_decision(text,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.factory_record_portfolio_decision(text,jsonb,jsonb) to service_role;
