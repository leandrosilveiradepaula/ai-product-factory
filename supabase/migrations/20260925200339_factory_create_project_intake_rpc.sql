create or replace function public.factory_create_project_intake(
  p_project_key text,
  p_name text,
  p_repository text,
  p_project_kind text,
  p_manifest jsonb,
  p_spec jsonb
) returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare v_project_id uuid;
begin
  if nullif(btrim(p_project_key), '') is null then raise exception 'project_key is required'; end if;
  if nullif(btrim(p_name), '') is null then raise exception 'name is required'; end if;
  insert into public.factory_projects(project_key,name,repository,project_kind,lifecycle_stage,manifest,is_active)
  values (btrim(p_project_key),btrim(p_name),nullif(btrim(p_repository),''),p_project_kind,'discovery',coalesce(p_manifest,'{}'::jsonb),true)
  returning id into v_project_id;
  insert into public.factory_product_specs(project_id,version,status,spec) values (v_project_id,1,'draft',coalesce(p_spec,'{}'::jsonb));
  insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
  values (v_project_id,'human','factory-console','project.intake.created',jsonb_build_object('project_key',p_project_key,'project_kind',p_project_kind));
  return v_project_id;
end;
$$;
revoke all on function public.factory_create_project_intake(text,text,text,text,jsonb,jsonb) from public, anon, authenticated;
grant execute on function public.factory_create_project_intake(text,text,text,text,jsonb,jsonb) to service_role;
