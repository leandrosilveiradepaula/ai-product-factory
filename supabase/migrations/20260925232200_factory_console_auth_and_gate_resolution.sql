create table if not exists public.factory_console_operators (
  user_id uuid primary key references auth.users(id) on delete cascade,
  role text not null check (role in ('operator','admin')),
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

alter table public.factory_console_operators enable row level security;
revoke all on table public.factory_console_operators from anon, authenticated;
grant select on table public.factory_console_operators to authenticated;

drop policy if exists factory_console_operators_select_self on public.factory_console_operators;
create policy factory_console_operators_select_self
on public.factory_console_operators
for select
to authenticated
using ((select auth.uid()) = user_id and is_active = true);

create or replace function public.factory_record_dispatch_decision(
  p_run_id uuid,
  p_route text,
  p_codex_level integer,
  p_codex_used boolean,
  p_human_gate boolean,
  p_gate_reasons jsonb
) returns void
language plpgsql
security invoker
set search_path=''
as $$
declare v_task_id uuid; v_project_id uuid;
begin
 if p_route not in ('direct','codex') then raise exception 'invalid route'; end if;
 select r.task_id,t.project_id into v_task_id,v_project_id
 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
 where r.id=p_run_id for update of r;
 if v_task_id is null then raise exception 'run not found'; end if;

 update public.factory_runs
 set execution_route=p_route,
     status=case when p_human_gate then 'awaiting_human' else 'queued' end,
     metadata=metadata||jsonb_build_object(
       'dispatch_pending',false,
       'codex_level',p_codex_level,
       'codex_used',p_codex_used,
       'human_gate_required',p_human_gate,
       'gate_reasons',coalesce(p_gate_reasons,'[]'::jsonb))
 where id=p_run_id;

 update public.factory_tasks
 set status=case when p_human_gate then 'awaiting_human' else 'queued_execution' end,
     updated_at=now()
 where id=v_task_id;

 insert into public.factory_decisions(project_id,task_id,decision_type,question,decision,decided_by)
 values(v_project_id,v_task_id,'execution_route',null,
   jsonb_build_object('route',p_route,'codex_level',p_codex_level,'codex_used',p_codex_used,'human_gate_required',p_human_gate,'gate_reasons',coalesce(p_gate_reasons,'[]'::jsonb)),
   'ai-product-factory');

 insert into public.factory_codex_usage(run_id,policy_level,invocation_count,reason,reported_usage)
 values(p_run_id,p_codex_level,0,coalesce(p_gate_reasons,'[]'::jsonb),'{}'::jsonb);

 if p_human_gate and not exists(
   select 1 from public.factory_human_gates where run_id=p_run_id and status='pending'
 ) then
   insert into public.factory_human_gates(run_id,gate_type,status,reasons)
   values(p_run_id,'execution_approval','pending',coalesce(p_gate_reasons,'[]'::jsonb));
 end if;
end;
$$;

revoke all on function public.factory_record_dispatch_decision(uuid,text,integer,boolean,boolean,jsonb) from public,anon,authenticated;
grant execute on function public.factory_record_dispatch_decision(uuid,text,integer,boolean,boolean,jsonb) to service_role;

create or replace function public.factory_resolve_human_gate(
  p_gate_id uuid,
  p_resolution text,
  p_resolved_by text,
  p_note text default null
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_gate public.factory_human_gates%rowtype; v_task_id uuid; v_project_id uuid;
begin
 if p_resolution not in ('approved','rejected') then raise exception 'invalid gate resolution'; end if;
 if nullif(btrim(p_resolved_by),'') is null then raise exception 'resolved_by is required'; end if;

 select * into v_gate from public.factory_human_gates where id=p_gate_id for update;
 if v_gate.id is null then raise exception 'gate not found'; end if;
 if v_gate.status <> 'pending' then raise exception 'gate already resolved'; end if;

 select r.task_id,t.project_id into v_task_id,v_project_id
 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
 where r.id=v_gate.run_id for update of r;
 if v_task_id is null then raise exception 'run not found'; end if;

 update public.factory_human_gates
 set status=p_resolution,
     resolved_at=now(),
     resolved_by=btrim(p_resolved_by),
     resolution=jsonb_build_object('resolution',p_resolution,'note',p_note)
 where id=p_gate_id;

 if p_resolution='approved' then
   update public.factory_runs set status='queued',
     metadata=metadata||jsonb_build_object('human_gate_required',false,'gate_resolution','approved')
   where id=v_gate.run_id;
   update public.factory_tasks set status='queued_execution',updated_at=now() where id=v_task_id;
 else
   update public.factory_runs set status='cancelled',finished_at=now(),
     metadata=metadata||jsonb_build_object('gate_resolution','rejected')
   where id=v_gate.run_id;
   update public.factory_tasks set status='cancelled',updated_at=now() where id=v_task_id;
 end if;

 insert into public.factory_decisions(project_id,task_id,decision_type,question,decision,decided_by)
 values(v_project_id,v_task_id,'human_gate_resolution',null,
   jsonb_build_object('gate_id',p_gate_id,'resolution',p_resolution,'note',p_note),
   btrim(p_resolved_by));

 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project_id,v_task_id,v_gate.run_id,'human',btrim(p_resolved_by),'human_gate.resolved',
   jsonb_build_object('gate_id',p_gate_id,'resolution',p_resolution,'note',p_note));

 return jsonb_build_object('gate_id',p_gate_id,'run_id',v_gate.run_id,'task_id',v_task_id,'resolution',p_resolution);
end;
$$;

revoke all on function public.factory_resolve_human_gate(uuid,text,text,text) from public,anon,authenticated;
grant execute on function public.factory_resolve_human_gate(uuid,text,text,text) to service_role;
