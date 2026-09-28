create table if not exists public.factory_project_database_oauth (
  database_id uuid primary key references public.factory_project_databases(id) on delete cascade,
  vault_access_secret_id uuid not null,
  vault_refresh_secret_id uuid,
  token_type text not null default 'bearer',
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.factory_project_database_oauth enable row level security;
revoke all on table public.factory_project_database_oauth from public,anon,authenticated;
grant select,insert,update,delete on table public.factory_project_database_oauth to service_role;

create or replace function public.factory_store_project_database_oauth(
 p_database_id uuid,p_access_token text,p_refresh_token text,p_token_type text,p_expires_at timestamptz
) returns void language plpgsql security definer set search_path='' as $$
declare v_access uuid;v_refresh uuid;v_old public.factory_project_database_oauth%rowtype;
begin
 if nullif(btrim(p_access_token),'') is null then raise exception 'access token required';end if;
 select * into v_old from public.factory_project_database_oauth where database_id=p_database_id;
 if found then
   perform vault.delete_secret(v_old.vault_access_secret_id);
   if v_old.vault_refresh_secret_id is not null then perform vault.delete_secret(v_old.vault_refresh_secret_id);end if;
 end if;
 v_access:=vault.create_secret(p_access_token,null,'Factory project Supabase OAuth access token');
 if nullif(btrim(coalesce(p_refresh_token,'')),'') is not null then
   v_refresh:=vault.create_secret(p_refresh_token,null,'Factory project Supabase OAuth refresh token');
 end if;
 insert into public.factory_project_database_oauth(database_id,vault_access_secret_id,vault_refresh_secret_id,token_type,expires_at,updated_at)
 values(p_database_id,v_access,v_refresh,coalesce(nullif(p_token_type,''),'bearer'),p_expires_at,now())
 on conflict(database_id) do update set vault_access_secret_id=excluded.vault_access_secret_id,
 vault_refresh_secret_id=excluded.vault_refresh_secret_id,token_type=excluded.token_type,expires_at=excluded.expires_at,updated_at=now();
end;$$;
revoke all on function public.factory_store_project_database_oauth(uuid,text,text,text,timestamptz) from public,anon,authenticated;
grant execute on function public.factory_store_project_database_oauth(uuid,text,text,text,timestamptz) to service_role;

create or replace function public.factory_get_project_database_oauth_access_token(p_database_id uuid)
returns text language sql security definer set search_path='' as $$
 select ds.decrypted_secret
 from public.factory_project_database_oauth o join vault.decrypted_secrets ds on ds.id=o.vault_access_secret_id
 where o.database_id=p_database_id;
$$;
revoke all on function public.factory_get_project_database_oauth_access_token(uuid) from public,anon,authenticated;
grant execute on function public.factory_get_project_database_oauth_access_token(uuid) to service_role;
