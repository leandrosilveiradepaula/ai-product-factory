create table if not exists public.factory_visual_evidence_runs (
  id uuid primary key default gen_random_uuid(),
  workflow_run_id bigint not null unique,
  source_commit text not null,
  artifact_name text not null,
  encryption_key text not null,
  status text not null default 'prepared'
    check (status in ('prepared','captured','consumed','expired')),
  expires_at timestamptz not null default (now() + interval '2 hours'),
  created_at timestamptz not null default now(),
  consumed_at timestamptz
);

alter table public.factory_visual_evidence_runs enable row level security;
revoke all on table public.factory_visual_evidence_runs from anon, authenticated;
grant select, insert, update, delete on table public.factory_visual_evidence_runs to service_role;

comment on table public.factory_visual_evidence_runs is
  'Ephemeral encryption-key registry for authenticated visual evidence. Fail-closed: no anon/authenticated policies.';
