create index if not exists idx_factory_audit_run
  on public.factory_audit_events(run_id);
create index if not exists idx_factory_decisions_project
  on public.factory_decisions(project_id);
create index if not exists idx_factory_decisions_task
  on public.factory_decisions(task_id);
create index if not exists idx_factory_deployments_run
  on public.factory_deployments(run_id);
create index if not exists idx_factory_tasks_parent
  on public.factory_tasks(parent_task_id);
create index if not exists idx_factory_tool_usage_run
  on public.factory_tool_usage(run_id);
