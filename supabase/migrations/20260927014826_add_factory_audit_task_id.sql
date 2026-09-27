alter table public.factory_audit_events
  add column if not exists task_id uuid
  references public.factory_tasks(id) on delete cascade;

create index if not exists idx_factory_audit_task
  on public.factory_audit_events(task_id);
