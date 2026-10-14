-- Make hierarchical agent scope claims atomic across *different* agents.
-- The original per-agent row locks do not prevent independent transactions
-- from reading uncommitted scope-lock inserts for the same project.
-- Transaction-scoped advisory lock serializes checks only for scoped work.
-- No data backfill, public API surface or cost/auth policy changes.

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

 -- Serialize scope conflict checks across agents of the same project.
 -- Row locks on individual agents do not protect overlapping hierarchical scopes.
 -- Advisory transaction lock is automatically released at commit/rollback.
 if jsonb_array_length(coalesce(p_scope_keys,'[]'::jsonb)) > 0 then
  perform pg_catalog.pg_advisory_xact_lock(
   pg_catalog.hashtextextended('factory:agent-scopes:' || v_project_id::text,0)
  );
 end if;

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
    and l.lease_expires_at > now()
    and l.run_id <> p_run_id
    and (
      l.scope_key=v_scope
      or starts_with(l.scope_key,v_scope || '/')
      or starts_with(v_scope,l.scope_key || '/')
    )
  limit 1;
  if found then raise exception 'scope conflict with run % on %',v_conflict.run_id,v_conflict.scope_key; end if;
 end loop;

 insert into public.factory_run_agent_assignments(run_id,agent_id,status,claimed_at)
 values(p_run_id,v_agent.id,'assigned',null) returning id into v_assignment_id;

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
