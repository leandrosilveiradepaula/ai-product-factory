create table if not exists public.factory_project_attachments (
  id uuid primary key default gen_random_uuid(),
  draft_id uuid not null,
  operator_user_id uuid not null,
  project_id uuid references public.factory_projects(id) on delete cascade,
  storage_bucket text not null,
  storage_path text not null unique,
  original_name text not null,
  mime_type text not null,
  size_bytes bigint not null check (size_bytes > 0 and size_bytes <= 10485760),
  sha256 text not null,
  created_at timestamptz not null default now(),
  finalized_at timestamptz
);

create index if not exists idx_factory_project_attachments_draft
  on public.factory_project_attachments(draft_id, operator_user_id);
create index if not exists idx_factory_project_attachments_project
  on public.factory_project_attachments(project_id, created_at);

alter table public.factory_project_attachments enable row level security;
revoke all on table public.factory_project_attachments from anon, authenticated;
grant all on table public.factory_project_attachments to service_role;

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values (
  'factory-project-files',
  'factory-project-files',
  false,
  10485760,
  array[
    'application/pdf',
    'text/plain',
    'text/markdown',
    'text/csv',
    'application/json',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'image/png',
    'image/jpeg',
    'image/webp'
  ]::text[]
)
on conflict (id) do update set
  public=false,
  file_size_limit=excluded.file_size_limit,
  allowed_mime_types=excluded.allowed_mime_types;

create or replace function public.factory_finalize_project_attachments(
  p_draft_id uuid,
  p_operator_user_id uuid,
  p_project_id uuid
) returns integer
language plpgsql
security invoker
set search_path = ''
as $$
declare v_count integer;
begin
  if not exists(select 1 from public.factory_projects where id=p_project_id) then
    raise exception 'project not found';
  end if;
  update public.factory_project_attachments
     set project_id=p_project_id, finalized_at=now()
   where draft_id=p_draft_id
     and operator_user_id=p_operator_user_id
     and project_id is null;
  get diagnostics v_count = row_count;
  insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
  values (
    p_project_id,
    'human',
    'factory-console',
    'project.attachments.finalized',
    jsonb_build_object('draft_id',p_draft_id,'count',v_count)
  );
  return v_count;
end;
$$;

revoke all on function public.factory_finalize_project_attachments(uuid,uuid,uuid) from public, anon, authenticated;
grant execute on function public.factory_finalize_project_attachments(uuid,uuid,uuid) to service_role;
