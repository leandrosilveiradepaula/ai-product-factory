create or replace function public.factory_bootstrap_console_admin(p_user_id uuid)
returns boolean
language plpgsql
security invoker
set search_path=''
as $$
begin
  if p_user_id is null then raise exception 'user_id is required'; end if;
  if exists(select 1 from public.factory_console_operators) then return false; end if;
  insert into public.factory_console_operators(user_id,role,is_active)
  values(p_user_id,'admin',true);
  return true;
exception when unique_violation then
  return false;
end;
$$;

create or replace function public.factory_upsert_console_operator(
  p_actor_user_id uuid,
  p_target_user_id uuid,
  p_role text,
  p_active boolean
) returns void
language plpgsql
security invoker
set search_path=''
as $$
begin
  if p_role not in ('operator','admin') then raise exception 'invalid role'; end if;
  if p_actor_user_id=p_target_user_id and p_active=false then raise exception 'admin cannot deactivate self'; end if;
  if not exists(
    select 1 from public.factory_console_operators
    where user_id=p_actor_user_id and role='admin' and is_active=true
  ) then raise exception 'admin authorization required'; end if;
  insert into public.factory_console_operators(user_id,role,is_active)
  values(p_target_user_id,p_role,p_active)
  on conflict(user_id) do update set role=excluded.role,is_active=excluded.is_active;
end;
$$;

revoke all on function public.factory_bootstrap_console_admin(uuid) from public,anon,authenticated;
grant execute on function public.factory_bootstrap_console_admin(uuid) to service_role;
revoke all on function public.factory_upsert_console_operator(uuid,uuid,text,boolean) from public,anon,authenticated;
grant execute on function public.factory_upsert_console_operator(uuid,uuid,text,boolean) to service_role;
