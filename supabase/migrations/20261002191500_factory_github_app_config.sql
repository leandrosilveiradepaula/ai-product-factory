create table if not exists public.factory_github_app_config (
  config_key text primary key default 'default' check (config_key='default'),
  app_id bigint not null,
  app_slug text not null,
  client_id text not null,
  vault_private_key_secret_id uuid not null,
  vault_webhook_secret_id uuid,
  vault_client_secret_id uuid,
  status text not null default 'registered' check (status in ('registered','active','revoked')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.factory_github_app_config enable row level security;
revoke all on table public.factory_github_app_config from public,anon,authenticated;
grant select,insert,update,delete on table public.factory_github_app_config to service_role;

create or replace function factory_private.store_factory_github_app(
  p_app_id bigint,
  p_app_slug text,
  p_client_id text,
  p_private_key text,
  p_webhook_secret text,
  p_client_secret text
) returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_old public.factory_github_app_config%rowtype;
  v_private uuid;
  v_webhook uuid;
  v_client uuid;
begin
  if p_app_id is null or p_app_id <= 0 then raise exception 'github app id required'; end if;
  if nullif(btrim(coalesce(p_app_slug,'')),'') is null then raise exception 'github app slug required'; end if;
  if nullif(btrim(coalesce(p_client_id,'')),'') is null then raise exception 'github app client id required'; end if;
  if nullif(btrim(coalesce(p_private_key,'')),'') is null then raise exception 'github app private key required'; end if;

  select * into v_old from public.factory_github_app_config where config_key='default' for update;
  if found then
    delete from vault.secrets where id=v_old.vault_private_key_secret_id;
    if v_old.vault_webhook_secret_id is not null then delete from vault.secrets where id=v_old.vault_webhook_secret_id; end if;
    if v_old.vault_client_secret_id is not null then delete from vault.secrets where id=v_old.vault_client_secret_id; end if;
  end if;

  v_private:=vault.create_secret(p_private_key,null,'Factory GitHub App private key');
  if nullif(btrim(coalesce(p_webhook_secret,'')),'') is not null then
    v_webhook:=vault.create_secret(p_webhook_secret,null,'Factory GitHub App webhook secret');
  end if;
  if nullif(btrim(coalesce(p_client_secret,'')),'') is not null then
    v_client:=vault.create_secret(p_client_secret,null,'Factory GitHub App client secret');
  end if;

  insert into public.factory_github_app_config(
    config_key,app_id,app_slug,client_id,vault_private_key_secret_id,
    vault_webhook_secret_id,vault_client_secret_id,status,updated_at
  ) values (
    'default',p_app_id,btrim(p_app_slug),btrim(p_client_id),v_private,v_webhook,v_client,'registered',now()
  )
  on conflict(config_key) do update set
    app_id=excluded.app_id,
    app_slug=excluded.app_slug,
    client_id=excluded.client_id,
    vault_private_key_secret_id=excluded.vault_private_key_secret_id,
    vault_webhook_secret_id=excluded.vault_webhook_secret_id,
    vault_client_secret_id=excluded.vault_client_secret_id,
    status='registered',
    updated_at=now();

  insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
  values(null,'operator','factory-console','github_app.registered',
    jsonb_build_object('app_id',p_app_id,'app_slug',btrim(p_app_slug),'secrets_stored_in_vault',true));

  return jsonb_build_object('app_id',p_app_id,'app_slug',btrim(p_app_slug),'client_id',btrim(p_client_id),'status','registered');
end;
$$;

create or replace function factory_private.get_factory_github_app_credentials()
returns jsonb
language sql
security definer
set search_path=''
as $$
  select jsonb_build_object(
    'app_id',c.app_id,
    'app_slug',c.app_slug,
    'client_id',c.client_id,
    'status',c.status,
    'private_key',pk.decrypted_secret,
    'webhook_secret',wh.decrypted_secret,
    'client_secret',cs.decrypted_secret
  )
  from public.factory_github_app_config c
  join vault.decrypted_secrets pk on pk.id=c.vault_private_key_secret_id
  left join vault.decrypted_secrets wh on wh.id=c.vault_webhook_secret_id
  left join vault.decrypted_secrets cs on cs.id=c.vault_client_secret_id
  where c.config_key='default' and c.status<>'revoked';
$$;

create or replace function factory_private.revoke_factory_github_app()
returns void
language plpgsql
security definer
set search_path=''
as $$
declare v_old public.factory_github_app_config%rowtype;
begin
  select * into v_old from public.factory_github_app_config where config_key='default' for update;
  if not found then return; end if;
  delete from vault.secrets where id=v_old.vault_private_key_secret_id;
  if v_old.vault_webhook_secret_id is not null then delete from vault.secrets where id=v_old.vault_webhook_secret_id; end if;
  if v_old.vault_client_secret_id is not null then delete from vault.secrets where id=v_old.vault_client_secret_id; end if;
  update public.factory_github_app_config
  set status='revoked',updated_at=now(),
      vault_private_key_secret_id=v_old.vault_private_key_secret_id,
      vault_webhook_secret_id=null,
      vault_client_secret_id=null
  where config_key='default';
  insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
  values(null,'operator','factory-console','github_app.revoked',jsonb_build_object('app_id',v_old.app_id,'app_slug',v_old.app_slug));
end;
$$;

revoke all on function factory_private.store_factory_github_app(bigint,text,text,text,text,text) from public,anon,authenticated;
revoke all on function factory_private.get_factory_github_app_credentials() from public,anon,authenticated;
revoke all on function factory_private.revoke_factory_github_app() from public,anon,authenticated;
grant execute on function factory_private.store_factory_github_app(bigint,text,text,text,text,text) to service_role;
grant execute on function factory_private.get_factory_github_app_credentials() to service_role;
grant execute on function factory_private.revoke_factory_github_app() to service_role;

create or replace function public.factory_store_github_app_config(
  p_app_id bigint,
  p_app_slug text,
  p_client_id text,
  p_private_key text,
  p_webhook_secret text,
  p_client_secret text
) returns jsonb
language sql
security invoker
set search_path=''
as $$
  select factory_private.store_factory_github_app(p_app_id,p_app_slug,p_client_id,p_private_key,p_webhook_secret,p_client_secret);
$$;

create or replace function public.factory_get_github_app_credentials()
returns jsonb
language sql
security invoker
set search_path=''
as $$
  select factory_private.get_factory_github_app_credentials();
$$;

create or replace function public.factory_get_github_app_status()
returns jsonb
language sql
security invoker
set search_path=''
as $$
  select jsonb_build_object(
    'configured',true,
    'app_id',app_id,
    'app_slug',app_slug,
    'client_id',client_id,
    'status',status,
    'updated_at',updated_at
  )
  from public.factory_github_app_config
  where config_key='default';
$$;

create or replace function public.factory_revoke_github_app_config()
returns void
language sql
security invoker
set search_path=''
as $$
  select factory_private.revoke_factory_github_app();
$$;

revoke all on function public.factory_store_github_app_config(bigint,text,text,text,text,text) from public,anon,authenticated;
revoke all on function public.factory_get_github_app_credentials() from public,anon,authenticated;
revoke all on function public.factory_get_github_app_status() from public,anon,authenticated;
revoke all on function public.factory_revoke_github_app_config() from public,anon,authenticated;
grant execute on function public.factory_store_github_app_config(bigint,text,text,text,text,text) to service_role;
grant execute on function public.factory_get_github_app_credentials() to service_role;
grant execute on function public.factory_get_github_app_status() to service_role;
grant execute on function public.factory_revoke_github_app_config() to service_role;
