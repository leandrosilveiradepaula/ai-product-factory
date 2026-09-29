create table if not exists public.factory_impact_analyses (
 id uuid primary key default gen_random_uuid(),
 project_id uuid not null references public.factory_projects(id) on delete cascade,
 brain_snapshot_id uuid references public.factory_project_brain_snapshots(id) on delete set null,
 task_id uuid references public.factory_tasks(id) on delete set null,
 run_id uuid references public.factory_runs(id) on delete set null,
 change_set_id uuid references public.factory_change_sets(id) on delete set null,
 confidence text not null check (confidence in ('high','medium','low','unknown')),
 seed_nodes jsonb not null default '[]'::jsonb,
 impacted_nodes jsonb not null default '[]'::jsonb,
 unknowns jsonb not null default '[]'::jsonb,
 summary text not null,
 created_at timestamptz not null default now()
);
create index if not exists idx_factory_impact_project_created
 on public.factory_impact_analyses(project_id,created_at desc);
create index if not exists idx_factory_impact_run
 on public.factory_impact_analyses(run_id);
alter table public.factory_impact_analyses enable row level security;
revoke all on public.factory_impact_analyses from public,anon,authenticated;
grant select,insert on public.factory_impact_analyses to service_role;

create or replace function public.factory_record_impact_analysis(
 p_project_id uuid,p_brain_snapshot_id uuid,p_task_id uuid,p_run_id uuid,p_change_set_id uuid,
 p_confidence text,p_seed_nodes jsonb,p_impacted_nodes jsonb,p_unknowns jsonb,p_summary text
) returns uuid
language plpgsql
security invoker
set search_path=''
as $$
declare v_id uuid;
begin
 if p_confidence not in ('high','medium','low','unknown') then raise exception 'invalid impact confidence'; end if;
 if jsonb_typeof(coalesce(p_seed_nodes,'[]'::jsonb))<>'array' then raise exception 'seed_nodes must be array'; end if;
 if jsonb_typeof(coalesce(p_impacted_nodes,'[]'::jsonb))<>'array' then raise exception 'impacted_nodes must be array'; end if;
 if jsonb_typeof(coalesce(p_unknowns,'[]'::jsonb))<>'array' then raise exception 'unknowns must be array'; end if;
 if nullif(btrim(p_summary),'') is null then raise exception 'impact summary required'; end if;
 if not exists(select 1 from public.factory_projects where id=p_project_id) then raise exception 'project not found'; end if;
 if p_brain_snapshot_id is not null and not exists(
   select 1 from public.factory_project_brain_snapshots where id=p_brain_snapshot_id and project_id=p_project_id
 ) then raise exception 'brain snapshot does not belong to project'; end if;
 insert into public.factory_impact_analyses(
   project_id,brain_snapshot_id,task_id,run_id,change_set_id,confidence,seed_nodes,impacted_nodes,unknowns,summary
 ) values(
   p_project_id,p_brain_snapshot_id,p_task_id,p_run_id,p_change_set_id,p_confidence,
   coalesce(p_seed_nodes,'[]'::jsonb),coalesce(p_impacted_nodes,'[]'::jsonb),coalesce(p_unknowns,'[]'::jsonb),p_summary
 ) returning id into v_id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(p_project_id,p_task_id,p_run_id,'system','impact-engine','impact.analysis.recorded',
   jsonb_build_object('impact_analysis_id',v_id,'confidence',p_confidence,
     'impacted_count',jsonb_array_length(coalesce(p_impacted_nodes,'[]'::jsonb)),
     'unknown_count',jsonb_array_length(coalesce(p_unknowns,'[]'::jsonb))));
 return v_id;
end;
$$;
revoke all on function public.factory_record_impact_analysis(uuid,uuid,uuid,uuid,uuid,text,jsonb,jsonb,jsonb,text)
 from public,anon,authenticated;
grant execute on function public.factory_record_impact_analysis(uuid,uuid,uuid,uuid,uuid,text,jsonb,jsonb,jsonb,text)
 to service_role;
