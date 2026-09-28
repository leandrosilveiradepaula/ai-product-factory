create table if not exists public.factory_project_databases (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.factory_projects(id) on delete cascade,
  provider text not null default 'supabase' check (provider in ('supabase')),
  environment text not null default 'prod',
  project_ref text,
  organization_ref text,
  region text,
  access_mode text not null default 'unconfigured'
    check (access_mode in ('unconfigured','management_api','oauth')),
  credential_ref text,
  permission_mode text not null default 'none'
    check (permission_mode in ('none','read','read_write')),
  status text not null default 'pending_access'
    check (status in ('pending_access','ready_read','ready_write','pending_provision_approval','provisioning','active','blocked')),
  is_existing boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  last_verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(project_id,provider,environment)
);

alter table public.factory_project_databases enable row level security;
revoke all on table public.factory_project_databases from public,anon,authenticated;
grant select,insert,update on table public.factory_project_databases to service_role;

create index if not exists idx_factory_project_databases_project
  on public.factory_project_databases(project_id,status);

create or replace function public.factory_register_project_database(
  p_project_id uuid,
  p_environment text,
  p_project_ref text,
  p_organization_ref text,
  p_region text,
  p_access_mode text,
  p_credential_ref text,
  p_permission_mode text,
  p_is_existing boolean,
  p_metadata jsonb default '{}'::jsonb
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_status text;
  v_row public.factory_project_databases%rowtype;
begin
  if p_access_mode not in ('unconfigured','management_api','oauth') then
    raise exception 'unsupported access_mode';
  end if;
  if p_permission_mode not in ('none','read','read_write') then
    raise exception 'unsupported permission_mode';
  end if;
  if p_credential_ref is not null and (
    p_credential_ref like 'sbp_%'
    or p_credential_ref like 'sb_secret_%'
    or p_credential_ref like 'eyJ%'
    or length(p_credential_ref) > 160
  ) then
    raise exception 'credential_ref must be an opaque secret reference, never a credential value';
  end if;

  v_status:=case
    when not p_is_existing then 'pending_provision_approval'
    when nullif(btrim(coalesce(p_project_ref,'')),'') is null then 'pending_access'
    when p_permission_mode='read_write' and nullif(btrim(coalesce(p_credential_ref,'')),'') is not null then 'ready_write'
    when p_permission_mode='read' and nullif(btrim(coalesce(p_credential_ref,'')),'') is not null then 'ready_read'
    else 'pending_access'
  end;

  insert into public.factory_project_databases(
    project_id,environment,project_ref,organization_ref,region,access_mode,credential_ref,
    permission_mode,status,is_existing,metadata,updated_at
  ) values(
    p_project_id,coalesce(nullif(btrim(p_environment),''),'prod'),nullif(btrim(p_project_ref),''),
    nullif(btrim(p_organization_ref),''),nullif(btrim(p_region),''),p_access_mode,
    nullif(btrim(p_credential_ref),''),p_permission_mode,v_status,p_is_existing,
    coalesce(p_metadata,'{}'::jsonb),now()
  )
  on conflict(project_id,provider,environment) do update set
    project_ref=excluded.project_ref,
    organization_ref=excluded.organization_ref,
    region=excluded.region,
    access_mode=excluded.access_mode,
    credential_ref=excluded.credential_ref,
    permission_mode=excluded.permission_mode,
    status=excluded.status,
    is_existing=excluded.is_existing,
    metadata=excluded.metadata,
    updated_at=now()
  returning * into v_row;

  insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
  values(
    p_project_id,'system','database-registry','project.database.registered',
    jsonb_build_object(
      'database_id',v_row.id,'provider',v_row.provider,'environment',v_row.environment,
      'project_ref',v_row.project_ref,'permission_mode',v_row.permission_mode,
      'status',v_row.status,'is_existing',v_row.is_existing
    )
  );

  return to_jsonb(v_row);
end;
$$;

revoke all on function public.factory_register_project_database(uuid,text,text,text,text,text,text,text,boolean,jsonb)
  from public,anon,authenticated;
grant execute on function public.factory_register_project_database(uuid,text,text,text,text,text,text,text,boolean,jsonb)
  to service_role;
