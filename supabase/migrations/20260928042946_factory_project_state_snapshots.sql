create table if not exists public.factory_project_state_snapshots (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.factory_projects(id) on delete cascade,
  run_id uuid references public.factory_runs(id) on delete set null,
  observed_stage text,
  summary text not null,
  evidence jsonb not null default '[]'::jsonb,
  gaps jsonb not null default '[]'::jsonb,
  constraints jsonb not null default '[]'::jsonb,
  source_status jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_factory_project_state_snapshots_project
  on public.factory_project_state_snapshots(project_id, created_at desc);
alter table public.factory_project_state_snapshots enable row level security;
revoke all on table public.factory_project_state_snapshots from anon, authenticated;
grant all on table public.factory_project_state_snapshots to service_role;

create or replace function public.factory_record_project_state_snapshot(
  p_project_id uuid,
  p_run_id uuid,
  p_observed_stage text,
  p_summary text,
  p_evidence jsonb default '[]'::jsonb,
  p_gaps jsonb default '[]'::jsonb,
  p_constraints jsonb default '[]'::jsonb,
  p_source_status jsonb default '{}'::jsonb
) returns uuid
language plpgsql
security invoker
set search_path=''
as $$
declare v_id uuid;
begin
  if btrim(coalesce(p_summary,''))='' then raise exception 'snapshot summary is required'; end if;
  insert into public.factory_project_state_snapshots(project_id,run_id,observed_stage,summary,evidence,gaps,constraints,source_status)
  values(p_project_id,p_run_id,nullif(btrim(p_observed_stage),''),btrim(p_summary),coalesce(p_evidence,'[]'::jsonb),coalesce(p_gaps,'[]'::jsonb),coalesce(p_constraints,'[]'::jsonb),coalesce(p_source_status,'{}'::jsonb))
  returning id into v_id;
  insert into public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
  values(p_project_id,p_run_id,'system','factory-runtime','project.state_snapshot.recorded',jsonb_build_object('snapshot_id',v_id,'observed_stage',p_observed_stage));
  return v_id;
end;
$$;
revoke all on function public.factory_record_project_state_snapshot(uuid,uuid,text,text,jsonb,jsonb,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.factory_record_project_state_snapshot(uuid,uuid,text,text,jsonb,jsonb,jsonb,jsonb) to service_role;
