create extension if not exists pgcrypto;

create table if not exists public.factory_projects (
  id uuid primary key default gen_random_uuid(),
  project_key text not null unique,
  name text not null,
  repository text,
  project_kind text not null,
  lifecycle_stage text not null default 'discovery',
  manifest jsonb not null default '{}'::jsonb,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.factory_product_specs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.factory_projects(id) on delete cascade,
  version integer not null,
  status text not null default 'draft',
  spec jsonb not null,
  created_at timestamptz not null default now(),
  unique(project_id, version)
);

create table if not exists public.factory_tasks (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.factory_projects(id) on delete cascade,
  parent_task_id uuid references public.factory_tasks(id),
  external_key text,
  title text not null,
  description text,
  status text not null default 'queued',
  complexity text not null default 'low',
  risk jsonb not null default '{}'::jsonb,
  acceptance_criteria jsonb not null default '[]'::jsonb,
  depends_on jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.factory_runs (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references public.factory_tasks(id) on delete cascade,
  status text not null default 'created',
  execution_route text,
  source_commit text,
  candidate_commit text,
  branch_name text,
  started_at timestamptz,
  finished_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.factory_decisions (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.factory_projects(id) on delete cascade,
  task_id uuid references public.factory_tasks(id) on delete cascade,
  decision_type text not null,
  question text,
  decision jsonb not null,
  decided_by text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.factory_human_gates (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.factory_runs(id) on delete cascade,
  gate_type text not null,
  status text not null default 'pending',
  reasons jsonb not null default '[]'::jsonb,
  requested_at timestamptz not null default now(),
  resolved_at timestamptz,
  resolved_by text,
  resolution jsonb not null default '{}'::jsonb
);

create table if not exists public.factory_tool_usage (
  id bigserial primary key,
  run_id uuid references public.factory_runs(id) on delete cascade,
  tool_family text not null,
  operation text,
  usage_units numeric,
  estimated_cost numeric,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.factory_codex_usage (
  id bigserial primary key,
  run_id uuid not null references public.factory_runs(id) on delete cascade,
  policy_level integer not null check (policy_level between 0 and 4),
  reason jsonb not null default '[]'::jsonb,
  invocation_count integer not null default 0,
  reported_usage jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.factory_evaluations (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.factory_runs(id) on delete cascade,
  eval_type text not null,
  status text not null,
  score numeric,
  baseline_ref text,
  result jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.factory_deployments (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.factory_runs(id) on delete cascade,
  environment text not null,
  status text not null,
  deployment_ref text,
  rollback_ref text,
  deployed_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.factory_audit_events (
  id bigserial primary key,
  project_id uuid references public.factory_projects(id) on delete cascade,
  run_id uuid references public.factory_runs(id) on delete cascade,
  actor_type text not null,
  actor_ref text,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_factory_tasks_project_status
  on public.factory_tasks(project_id, status);
create index if not exists idx_factory_runs_task_status
  on public.factory_runs(task_id, status);
create index if not exists idx_factory_gates_run_status
  on public.factory_human_gates(run_id, status);
create index if not exists idx_factory_evals_run
  on public.factory_evaluations(run_id);
create index if not exists idx_factory_codex_run
  on public.factory_codex_usage(run_id);
create index if not exists idx_factory_audit_project_created
  on public.factory_audit_events(project_id, created_at);
