create table if not exists public.factory_agent_concurrency_decisions (
 id uuid primary key default gen_random_uuid(),
 agent_id uuid not null references public.factory_agents(id) on delete cascade,
 effective_concurrency integer not null check (effective_concurrency between 0 and 32),
 profile_ceiling integer not null check (profile_ceiling between 1 and 32),
 runnable_work integer not null check (runnable_work >= 0),
 pressure jsonb not null default '{}'::jsonb,
 reasons jsonb not null default '[]'::jsonb,
 source text not null default 'adaptive-concurrency-v1',
 created_at timestamptz not null default now(),
 constraint factory_agent_concurrency_pressure_no_secrets check (
   not (pressure ?| array['token','secret','password','api_key','authorization','credential'])
 )
);
create index if not exists idx_factory_agent_concurrency_decisions_agent_created
 on public.factory_agent_concurrency_decisions(agent_id,created_at desc);
alter table public.factory_agent_concurrency_decisions enable row level security;
revoke all on public.factory_agent_concurrency_decisions from public,anon,authenticated;
grant select,insert on public.factory_agent_concurrency_decisions to service_role;

create or replace function public.factory_record_agent_concurrency_decision(
 p_agent_key text,
 p_effective_concurrency integer,
 p_profile_ceiling integer,
 p_runnable_work integer,
 p_pressure jsonb,
 p_reasons jsonb
) returns uuid
language plpgsql
security invoker
set search_path=''
as $$
declare v_agent_id uuid;v_id uuid;
begin
 if p_effective_concurrency<0 or p_effective_concurrency>32 then raise exception 'invalid effective concurrency'; end if;
 if p_profile_ceiling<1 or p_profile_ceiling>32 then raise exception 'invalid profile ceiling'; end if;
 if p_runnable_work<0 then raise exception 'invalid runnable work'; end if;
 if jsonb_typeof(coalesce(p_pressure,'{}'::jsonb))<>'object' then raise exception 'pressure must be object'; end if;
 if jsonb_typeof(coalesce(p_reasons,'[]'::jsonb))<>'array' then raise exception 'reasons must be array'; end if;
 if coalesce(p_pressure,'{}'::jsonb) ?| array['token','secret','password','api_key','authorization','credential'] then
   raise exception 'secret-like pressure metadata is forbidden';
 end if;
 select id into v_agent_id from public.factory_agents where agent_key=p_agent_key and is_active;
 if v_agent_id is null then raise exception 'active agent not found'; end if;
 insert into public.factory_agent_concurrency_decisions(
  agent_id,effective_concurrency,profile_ceiling,runnable_work,pressure,reasons
 ) values(v_agent_id,p_effective_concurrency,p_profile_ceiling,p_runnable_work,coalesce(p_pressure,'{}'::jsonb),coalesce(p_reasons,'[]'::jsonb))
 returning id into v_id;
 return v_id;
end;
$$;
revoke all on function public.factory_record_agent_concurrency_decision(text,integer,integer,integer,jsonb,jsonb)
 from public,anon,authenticated;
grant execute on function public.factory_record_agent_concurrency_decision(text,integer,integer,integer,jsonb,jsonb)
 to service_role;

