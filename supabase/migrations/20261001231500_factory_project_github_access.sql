create table if not exists public.factory_project_github_access (
  project_id uuid primary key references public.factory_projects(id) on delete cascade,
  repository text not null,
  auth_mode text not null default 'fine_grained_pat'
    check (auth_mode in ('native_github_token','fine_grained_pat','github_app')),
  required_capabilities jsonb not null default '{}'::jsonb,
  observed_capabilities jsonb not null default '{}'::jsonb,
  status text not null default 'unverified'
    check (status in ('unverified','ready','partial','blocked','stale')),
  installation_id bigint,
  repository_id bigint,
  last_verified_at timestamptz,
  last_error text,
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_factory_project_github_access_status
  on public.factory_project_github_access(status, updated_at);

alter table public.factory_project_github_access enable row level security;
revoke all on table public.factory_project_github_access from anon, authenticated;
grant all on table public.factory_project_github_access to service_role;

insert into public.factory_project_github_access(project_id,repository,auth_mode,status)
select id,repository,
       case when repository='leandrosilveiradepaula/ai-product-factory'
            then 'native_github_token' else 'fine_grained_pat' end,
       'unverified'
from public.factory_projects
where repository is not null and btrim(repository)<>''
on conflict (project_id) do nothing;

create or replace function public.factory_seed_project_github_access()
returns trigger
language plpgsql
security invoker
set search_path=''
as $$
begin
  if new.repository is not null and btrim(new.repository)<>'' then
    insert into public.factory_project_github_access(project_id,repository,auth_mode,status)
    values(
      new.id,
      btrim(new.repository),
      case when btrim(new.repository)='leandrosilveiradepaula/ai-product-factory'
           then 'native_github_token' else 'fine_grained_pat' end,
      'unverified'
    )
    on conflict(project_id) do update set
      repository=excluded.repository,
      auth_mode=case
        when public.factory_project_github_access.auth_mode='github_app' then 'github_app'
        else excluded.auth_mode
      end,
      status=case
        when public.factory_project_github_access.repository is distinct from excluded.repository then 'stale'
        else public.factory_project_github_access.status
      end,
      updated_at=now();
  end if;
  return new;
end;
$$;

drop trigger if exists trg_factory_seed_project_github_access on public.factory_projects;
create trigger trg_factory_seed_project_github_access
after insert or update of repository on public.factory_projects
for each row execute function public.factory_seed_project_github_access();

revoke all on function public.factory_seed_project_github_access() from public,anon,authenticated;
grant execute on function public.factory_seed_project_github_access() to service_role;

create or replace function public.factory_record_project_github_access(
  p_project_id uuid,
  p_repository text,
  p_auth_mode text,
  p_required_capabilities jsonb,
  p_observed_capabilities jsonb,
  p_status text,
  p_last_error text default null,
  p_evidence jsonb default '{}'::jsonb,
  p_installation_id bigint default null,
  p_repository_id bigint default null
) returns public.factory_project_github_access
language plpgsql
security invoker
set search_path=''
as $$
declare v_row public.factory_project_github_access;
begin
  if btrim(coalesce(p_repository,''))='' then raise exception 'repository is required'; end if;
  if p_auth_mode not in ('native_github_token','fine_grained_pat','github_app') then raise exception 'invalid github auth mode'; end if;
  if p_status not in ('unverified','ready','partial','blocked','stale') then raise exception 'invalid github access status'; end if;

  insert into public.factory_project_github_access(
    project_id,repository,auth_mode,required_capabilities,observed_capabilities,status,
    installation_id,repository_id,last_verified_at,last_error,evidence,updated_at
  ) values (
    p_project_id,btrim(p_repository),p_auth_mode,coalesce(p_required_capabilities,'{}'::jsonb),
    coalesce(p_observed_capabilities,'{}'::jsonb),p_status,p_installation_id,p_repository_id,
    now(),nullif(btrim(coalesce(p_last_error,'')),''),coalesce(p_evidence,'{}'::jsonb),now()
  )
  on conflict(project_id) do update set
    repository=excluded.repository,
    auth_mode=excluded.auth_mode,
    required_capabilities=excluded.required_capabilities,
    observed_capabilities=excluded.observed_capabilities,
    status=excluded.status,
    installation_id=coalesce(excluded.installation_id,public.factory_project_github_access.installation_id),
    repository_id=coalesce(excluded.repository_id,public.factory_project_github_access.repository_id),
    last_verified_at=excluded.last_verified_at,
    last_error=excluded.last_error,
    evidence=excluded.evidence,
    updated_at=now()
  returning * into v_row;

  insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
  values(
    p_project_id,'system','github-capability-preflight','project.github_access.verified',
    jsonb_build_object(
      'repository',p_repository,
      'auth_mode',p_auth_mode,
      'status',p_status,
      'observed_capabilities',coalesce(p_observed_capabilities,'{}'::jsonb)
    )
  );
  return v_row;
end;
$$;

revoke all on function public.factory_record_project_github_access(uuid,text,text,jsonb,jsonb,text,text,jsonb,bigint,bigint)
  from public,anon,authenticated;
grant execute on function public.factory_record_project_github_access(uuid,text,text,jsonb,jsonb,text,text,jsonb,bigint,bigint)
  to service_role;
