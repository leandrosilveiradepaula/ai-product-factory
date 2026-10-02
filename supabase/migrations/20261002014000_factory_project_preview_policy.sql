create or replace function public.factory_record_project_preview_policy(
  p_project_id uuid,
  p_policy jsonb,
  p_evidence jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_project public.factory_projects%rowtype;
  v_existing jsonb;
  v_policy jsonb;
begin
  select * into v_project
  from public.factory_projects
  where id=p_project_id and is_active=true
  for update;

  if v_project.id is null then raise exception 'active project not found'; end if;
  if jsonb_typeof(coalesce(p_policy,'null'::jsonb))<>'object' then raise exception 'preview policy must be an object'; end if;
  if p_policy->>'provider'<>'vercel' then raise exception 'automatic preview onboarding only supports verified Vercel integration'; end if;
  if p_policy->>'mode'<>'github' then raise exception 'automatic preview onboarding only supports github mode'; end if;
  if coalesce((p_policy->>'required')::boolean,false) is not true then
    raise exception 'automatic preview onboarding cannot disable preview';
  end if;
  if p_evidence->>'source'<>'github_vercel_integration' then
    raise exception 'verified GitHub Vercel evidence is required';
  end if;
  if btrim(coalesce(p_evidence->>'commit_sha',''))='' then raise exception 'evidence commit sha is required'; end if;

  v_existing:=v_project.manifest->'preview';
  if jsonb_typeof(v_existing)='object'
     and (v_existing ? 'required' or v_existing ? 'provider' or v_existing ? 'mode' or v_existing ? 'required_paths') then
    return jsonb_build_object(
      'project_id',p_project_id,
      'updated',false,
      'reason','existing_policy_preserved',
      'preview',v_existing
    );
  end if;

  v_policy:=p_policy||jsonb_build_object('evidence',coalesce(p_evidence,'{}'::jsonb));

  update public.factory_projects
  set manifest=jsonb_set(coalesce(manifest,'{}'::jsonb),'{preview}',v_policy,true),
      updated_at=now()
  where id=p_project_id;

  insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
  values(
    p_project_id,'system','github-capability-preflight','project.preview_policy.verified',
    jsonb_build_object(
      'preview',v_policy,
      'source','github_vercel_integration'
    )
  );

  return jsonb_build_object(
    'project_id',p_project_id,
    'updated',true,
    'reason','vercel_github_integration_verified',
    'preview',v_policy
  );
end;
$$;

revoke all on function public.factory_record_project_preview_policy(uuid,jsonb,jsonb)
  from public,anon,authenticated;
grant execute on function public.factory_record_project_preview_policy(uuid,jsonb,jsonb)
  to service_role;
