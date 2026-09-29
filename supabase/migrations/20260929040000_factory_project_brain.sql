create table if not exists public.factory_project_brain_snapshots (
 id uuid primary key default gen_random_uuid(),
 project_id uuid not null references public.factory_projects(id) on delete cascade,
 version integer not null,
 status text not null default 'current' check (status in ('current','superseded')),
 source_ref text not null,
 summary text,
 created_at timestamptz not null default now(),
 unique(project_id,version)
);
create unique index if not exists idx_factory_project_brain_current
 on public.factory_project_brain_snapshots(project_id) where status='current';

create table if not exists public.factory_project_brain_nodes (
 id uuid primary key default gen_random_uuid(),
 snapshot_id uuid not null references public.factory_project_brain_snapshots(id) on delete cascade,
 node_key text not null,
 node_type text not null check (node_type in ('project','task','scope','capability','component','api','table','integration','decision','requirement','risk','release','evidence','source')),
 name text not null,
 attributes jsonb not null default '{}'::jsonb,
 source_refs jsonb not null default '[]'::jsonb,
 unique(snapshot_id,node_key)
);

create table if not exists public.factory_project_brain_edges (
 id uuid primary key default gen_random_uuid(),
 snapshot_id uuid not null references public.factory_project_brain_snapshots(id) on delete cascade,
 edge_key text not null,
 from_node_id uuid not null references public.factory_project_brain_nodes(id) on delete cascade,
 to_node_id uuid not null references public.factory_project_brain_nodes(id) on delete cascade,
 relation text not null,
 attributes jsonb not null default '{}'::jsonb,
 source_refs jsonb not null default '[]'::jsonb,
 unique(snapshot_id,edge_key)
);

create index if not exists idx_factory_project_brain_nodes_lookup
 on public.factory_project_brain_nodes(snapshot_id,node_type,node_key);
create index if not exists idx_factory_project_brain_edges_from
 on public.factory_project_brain_edges(snapshot_id,from_node_id);
create index if not exists idx_factory_project_brain_edges_to
 on public.factory_project_brain_edges(snapshot_id,to_node_id);

alter table public.factory_project_brain_snapshots enable row level security;
alter table public.factory_project_brain_nodes enable row level security;
alter table public.factory_project_brain_edges enable row level security;
revoke all on public.factory_project_brain_snapshots from public,anon,authenticated;
revoke all on public.factory_project_brain_nodes from public,anon,authenticated;
revoke all on public.factory_project_brain_edges from public,anon,authenticated;
grant select,insert,update,delete on public.factory_project_brain_snapshots to service_role;
grant select,insert,update,delete on public.factory_project_brain_nodes to service_role;
grant select,insert,update,delete on public.factory_project_brain_edges to service_role;

create or replace function public.factory_record_project_brain_snapshot(
 p_project_id uuid,p_source_ref text,p_summary text,p_nodes jsonb,p_edges jsonb
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
 v_project_id uuid;
 v_version integer;
 v_snapshot_id uuid;
 v_node jsonb;
 v_edge jsonb;
 v_from uuid;
 v_to uuid;
begin
 if nullif(btrim(p_source_ref),'') is null then raise exception 'source_ref is required'; end if;
 if jsonb_typeof(coalesce(p_nodes,'[]'::jsonb))<>'array' then raise exception 'nodes must be array'; end if;
 if jsonb_typeof(coalesce(p_edges,'[]'::jsonb))<>'array' then raise exception 'edges must be array'; end if;
 select id into v_project_id from public.factory_projects where id=p_project_id for update;
 if v_project_id is null then raise exception 'project not found'; end if;
 select coalesce(max(version),0)+1 into v_version from public.factory_project_brain_snapshots where project_id=p_project_id;
 update public.factory_project_brain_snapshots set status='superseded' where project_id=p_project_id and status='current';
 insert into public.factory_project_brain_snapshots(project_id,version,status,source_ref,summary)
 values(p_project_id,v_version,'current',p_source_ref,p_summary)
 returning id into v_snapshot_id;

 for v_node in select value from jsonb_array_elements(coalesce(p_nodes,'[]'::jsonb))
 loop
   if coalesce(v_node->>'key','')='' or coalesce(v_node->>'type','')='' or coalesce(v_node->>'name','')='' then
     raise exception 'brain node requires key, type and name';
   end if;
   if coalesce(v_node->'attributes','{}'::jsonb) ?| array['token','secret','password','api_key','authorization','credential'] then
     raise exception 'secret-like brain node attributes are forbidden';
   end if;
   insert into public.factory_project_brain_nodes(snapshot_id,node_key,node_type,name,attributes,source_refs)
   values(v_snapshot_id,v_node->>'key',v_node->>'type',v_node->>'name',
     coalesce(v_node->'attributes','{}'::jsonb),coalesce(v_node->'source_refs','[]'::jsonb));
 end loop;

 for v_edge in select value from jsonb_array_elements(coalesce(p_edges,'[]'::jsonb))
 loop
   select id into v_from from public.factory_project_brain_nodes where snapshot_id=v_snapshot_id and node_key=v_edge->>'from';
   select id into v_to from public.factory_project_brain_nodes where snapshot_id=v_snapshot_id and node_key=v_edge->>'to';
   if v_from is null or v_to is null then raise exception 'brain edge references unknown node'; end if;
   insert into public.factory_project_brain_edges(snapshot_id,edge_key,from_node_id,to_node_id,relation,attributes,source_refs)
   values(v_snapshot_id,v_edge->>'key',v_from,v_to,v_edge->>'relation',
     coalesce(v_edge->'attributes','{}'::jsonb),coalesce(v_edge->'source_refs','[]'::jsonb));
 end loop;

 insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
 values(p_project_id,'system','project-brain','project_brain.snapshot.recorded',
   jsonb_build_object('snapshot_id',v_snapshot_id,'version',v_version,'nodes',jsonb_array_length(coalesce(p_nodes,'[]'::jsonb)),'edges',jsonb_array_length(coalesce(p_edges,'[]'::jsonb))));

 return jsonb_build_object('snapshot_id',v_snapshot_id,'version',v_version,'status','current');
end;
$$;
revoke all on function public.factory_record_project_brain_snapshot(uuid,text,text,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.factory_record_project_brain_snapshot(uuid,text,text,jsonb,jsonb) to service_role;
