-- Authorized operator commands atomically record a durable wake; no DRAFT auto-start.
begin;
create table public.factory_project_control_wakes (
 id uuid primary key default gen_random_uuid(),
 project_id uuid not null,
 command_id uuid not null,
 command text not null check(command in ('start','resume','restart')),
 generation bigint not null check(generation>0),
 status text not null default 'pending'
   check(status in ('pending','claimed','dispatched','observed','suppressed','exhausted')),
 attempts integer not null default 0 check(attempts between 0 and 5),
 next_attempt_at timestamptz not null default now(),
 lease_owner text, lease_until timestamptz,
 last_result text,
 created_at timestamptz not null default now(),updated_at timestamptz not null default now(),
 unique(project_id,command_id),
 foreign key(project_id,command_id) references public.factory_project_execution_commands(project_id,command_id) on delete restrict,
 check((status='claimed' and lease_owner is not null and lease_until is not null)
    or (status<>'claimed' and lease_owner is null and lease_until is null))
);
create index factory_project_control_wakes_due on public.factory_project_control_wakes(next_attempt_at)
 where status in ('pending','claimed');
alter table public.factory_project_control_wakes enable row level security;
revoke all on public.factory_project_control_wakes from public,anon,authenticated;
grant select,insert,update on public.factory_project_control_wakes to service_role;

create function public.factory_record_project_control_wake()
returns trigger language plpgsql security invoker set search_path='' as $$
declare c record;
begin
 if new.command not in ('start','resume','restart') then return new;end if;
 select state,generation,version into c from public.factory_project_execution_controls
 where project_id=new.project_id;
 if not found or c.state<>'running'
    or c.version is distinct from (new.result->>'version')::bigint
    or c.generation is distinct from (new.result->>'generation')::bigint
    or new.result->>'command' is distinct from new.command
    or new.result->>'state' is distinct from 'running'
 then raise exception 'wake command lacks an atomic running transition';end if;
 insert into public.factory_project_control_wakes(project_id,command_id,command,generation)
 values(new.project_id,new.command_id,new.command,c.generation);
 return new;
end;
$$;
revoke all on function public.factory_record_project_control_wake() from public,anon,authenticated;
grant execute on function public.factory_record_project_control_wake() to service_role;
create trigger factory_project_control_wake_committed after insert on public.factory_project_execution_commands
for each row execute function public.factory_record_project_control_wake();

create function public.factory_claim_project_control_wake(
 p_owner text,p_command_id uuid default null
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare w public.factory_project_control_wakes%rowtype;c record;
begin
 if p_owner !~ '^[a-zA-Z0-9_.:-]{3,128}$' then raise exception 'invalid owner';end if;
 select * into w from public.factory_project_control_wakes
 where (p_command_id is null or command_id=p_command_id)
   and ((status='pending' and next_attempt_at<=now())
     or (status='claimed' and lease_until<=now()))
 order by created_at,id for update skip locked limit 1;
 if not found then return null;end if;
 select state,generation into c from public.factory_project_execution_controls
 where project_id=w.project_id for share;
 if not found or c.state<>'running' or c.generation<>w.generation
    or not exists(select 1 from public.factory_projects
                  where id=w.project_id and is_active)
 then
  update public.factory_project_control_wakes set status='suppressed',
    lease_owner=null,lease_until=null,last_result='revoked',updated_at=now() where id=w.id;
  return jsonb_build_object('status','suppressed','id',w.id);
 end if;
 if w.attempts>=5 then
  update public.factory_project_control_wakes set status='exhausted',
    lease_owner=null,lease_until=null,last_result='attempt_limit',updated_at=now() where id=w.id;
  return jsonb_build_object('status','exhausted','id',w.id);
 end if;
 update public.factory_project_control_wakes set status='claimed',attempts=attempts+1,
 lease_owner=p_owner,lease_until=now()+interval '90 seconds',updated_at=now()
 where id=w.id;
 return jsonb_build_object('id',w.id,'status','claimed','attempt',w.attempts+1,
 'generation',w.generation);
end;
$$;
revoke all on function public.factory_claim_project_control_wake(text,uuid) from public,anon,authenticated;
grant execute on function public.factory_claim_project_control_wake(text,uuid) to service_role;

create function public.factory_ack_project_control_wake(
 p_id uuid,p_owner text,p_result text
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare w public.factory_project_control_wakes%rowtype;c record;next_state text;
begin
 if p_id is null or p_owner !~ '^[a-zA-Z0-9_.:-]{3,128}$'
    or p_result not in ('dispatched','observed','failed') then
    raise exception 'invalid acknowledgement';end if;
 select * into w from public.factory_project_control_wakes where id=p_id for update;
 if not found or w.status<>'claimed' or w.lease_owner is distinct from p_owner
    or w.lease_until<=now() then raise exception 'lost wake lease';end if;
 select state,generation into c from public.factory_project_execution_controls
 where project_id=w.project_id for share;
 next_state:=case when c.state is distinct from 'running' or c.generation<>w.generation then 'suppressed'
 when p_result in ('dispatched','observed') then p_result
 when w.attempts>=5 then 'exhausted' else 'pending' end;
 update public.factory_project_control_wakes set status=next_state,lease_owner=null,
 lease_until=null,last_result=p_result,updated_at=now(),
 next_attempt_at=case when next_state='pending'
 then now()+make_interval(secs=>least(900,30*(2^least(w.attempts,5))::int))
 else next_attempt_at end where id=w.id;
 insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
 values(w.project_id,'system','control-wake','project.control.wake_observed',
 jsonb_build_object('id',w.id,'command_id',w.command_id,'status',next_state,
 'attempt',w.attempts,'generation',w.generation));
 return jsonb_build_object('id',w.id,'status',next_state,'attempt',w.attempts);
end;
$$;
revoke all on function public.factory_ack_project_control_wake(uuid,text,text) from public,anon,authenticated;
grant execute on function public.factory_ack_project_control_wake(uuid,text,text) to service_role;
commit;
