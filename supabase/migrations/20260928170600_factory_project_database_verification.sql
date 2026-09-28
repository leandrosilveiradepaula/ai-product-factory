alter table public.factory_project_databases
  drop constraint if exists factory_project_databases_status_check;
alter table public.factory_project_databases
  add constraint factory_project_databases_status_check
  check (status in ('pending_access','verifying','ready_read','ready_write','pending_provision_approval','provisioning','active','blocked'));

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
declare v_status text; v_row public.factory_project_databases%rowtype;
begin
  if p_access_mode not in ('unconfigured','management_api','oauth') then raise exception 'unsupported access_mode'; end if;
  if p_permission_mode not in ('none','read','read_write') then raise exception 'unsupported permission_mode'; end if;
  if p_credential_ref is not null and (
    p_credential_ref like 'sbp_%' or p_credential_ref like 'sb_secret_%'
    or p_credential_ref like 'eyJ%' or length(p_credential_ref)>160
  ) then raise exception 'credential_ref must be an opaque secret reference, never a credential value'; end if;

  v_status:=case
    when not p_is_existing then 'pending_provision_approval'
    else 'pending_access'
  end;

  insert into public.factory_project_databases(
    project_id,environment,project_ref,organization_ref,region,access_mode,credential_ref,
    permission_mode,status,is_existing,metadata,last_verified_at,updated_at
  ) values(
    p_project_id,coalesce(nullif(btrim(p_environment),''),'prod'),nullif(btrim(p_project_ref),''),
    nullif(btrim(p_organization_ref),''),nullif(btrim(p_region),''),p_access_mode,
    nullif(btrim(p_credential_ref),''),p_permission_mode,v_status,p_is_existing,
    coalesce(p_metadata,'{}'::jsonb),null,now()
  )
  on conflict(project_id,provider,environment) do update set
    project_ref=excluded.project_ref,organization_ref=excluded.organization_ref,region=excluded.region,
    access_mode=excluded.access_mode,credential_ref=excluded.credential_ref,
    permission_mode=excluded.permission_mode,status=excluded.status,is_existing=excluded.is_existing,
    metadata=excluded.metadata,last_verified_at=null,updated_at=now()
  returning * into v_row;

  insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
  values(p_project_id,'system','database-registry','project.database.registered',
    jsonb_build_object('database_id',v_row.id,'provider',v_row.provider,'environment',v_row.environment,
      'project_ref',v_row.project_ref,'permission_mode',v_row.permission_mode,'status',v_row.status,
      'is_existing',v_row.is_existing));
  return to_jsonb(v_row);
end; $$;

create or replace function public.factory_record_project_database_verification(
  p_database_id uuid,
  p_verified_project_ref text,
  p_read_verified boolean,
  p_write_verified boolean default false,
  p_evidence jsonb default '{}'::jsonb
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_row public.factory_project_databases%rowtype; v_status text;
begin
  select * into v_row from public.factory_project_databases where id=p_database_id for update;
  if not found then raise exception 'database binding not found'; end if;
  if v_row.project_ref is null or p_verified_project_ref is distinct from v_row.project_ref then
    update public.factory_project_databases set status='blocked',last_verified_at=now(),updated_at=now()
      where id=p_database_id returning * into v_row;
  else
    v_status:=case
      when p_write_verified and v_row.permission_mode='read_write' then 'ready_write'
      when p_read_verified then 'ready_read'
      else 'blocked' end;
    update public.factory_project_databases set status=v_status,last_verified_at=now(),updated_at=now(),
      metadata=metadata || jsonb_build_object('last_verification',coalesce(p_evidence,'{}'::jsonb))
      where id=p_database_id returning * into v_row;
  end if;
  insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
  values(v_row.project_id,'system','database-preflight','project.database.verified',
    jsonb_build_object('database_id',v_row.id,'project_ref_match',p_verified_project_ref=v_row.project_ref,
      'read_verified',p_read_verified,'write_verified',p_write_verified,'status',v_row.status));
  return to_jsonb(v_row);
end; $$;

revoke all on function public.factory_record_project_database_verification(uuid,text,boolean,boolean,jsonb)
  from public,anon,authenticated;
grant execute on function public.factory_record_project_database_verification(uuid,text,boolean,boolean,jsonb)
  to service_role;
