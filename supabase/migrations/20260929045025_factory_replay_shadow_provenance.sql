create table if not exists public.factory_run_provenance (
 run_id uuid primary key references public.factory_runs(id) on delete cascade,
 project_id uuid not null references public.factory_projects(id) on delete cascade,
 snapshot_hash text not null check (snapshot_hash ~ '^[0-9a-f]{64}$'),
 snapshot jsonb not null,
 created_at timestamptz not null default now()
);
alter table public.factory_run_provenance enable row level security;
revoke all on public.factory_run_provenance from public,anon,authenticated;
grant select,insert,update on public.factory_run_provenance to service_role;

create table if not exists public.factory_replay_requests (
 id uuid primary key default gen_random_uuid(),
 source_run_id uuid not null references public.factory_runs(id) on delete cascade,
 mode text not null check (mode in ('offline','shadow')),
 status text not null default 'ready' check (status in ('ready','evaluated','blocked')),
 provenance_hash text not null,
 snapshot jsonb not null,
 effect text not null default 'none' check (effect='none'),
 model_calls_allowed boolean not null default false check (model_calls_allowed=false),
 created_at timestamptz not null default now(),
 evaluated_at timestamptz
);
alter table public.factory_replay_requests enable row level security;
revoke all on public.factory_replay_requests from public,anon,authenticated;
grant select,insert,update on public.factory_replay_requests to service_role;

create table if not exists public.factory_shadow_decisions (
 id uuid primary key default gen_random_uuid(),
 source_run_id uuid not null references public.factory_runs(id) on delete cascade,
 replay_id uuid references public.factory_replay_requests(id) on delete cascade,
 component text not null,
 component_version text not null,
 input_hash text not null check (input_hash ~ '^[0-9a-f]{64}$'),
 decision jsonb not null,
 observed_outcome jsonb not null default '{}'::jsonb,
 effect text not null default 'none' check (effect='none'),
 created_at timestamptz not null default now()
);
alter table public.factory_shadow_decisions enable row level security;
revoke all on public.factory_shadow_decisions from public,anon,authenticated;
grant select,insert,update on public.factory_shadow_decisions to service_role;
create index if not exists idx_factory_shadow_decisions_run on public.factory_shadow_decisions(source_run_id,created_at);

create table if not exists public.factory_improvement_proposals (
 id uuid primary key default gen_random_uuid(),
 source_run_id uuid references public.factory_runs(id) on delete set null,
 proposal_key text not null,
 evidence jsonb not null default '{}'::jsonb,
 proposed_change jsonb not null,
 status text not null default 'proposed' check (status in ('proposed','accepted','rejected','implemented')),
 requires_source_control boolean not null default true check (requires_source_control=true),
 auto_apply boolean not null default false check (auto_apply=false),
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
alter table public.factory_improvement_proposals enable row level security;
revoke all on public.factory_improvement_proposals from public,anon,authenticated;
grant select,insert,update on public.factory_improvement_proposals to service_role;

create or replace function public.factory_record_run_provenance(
 p_run_id uuid,p_snapshot_hash text,p_snapshot jsonb
) returns jsonb
language plpgsql security invoker set search_path=''
as $$
declare v_project_id uuid;
begin
 if p_snapshot_hash !~ '^[0-9a-f]{64}$' then raise exception 'invalid provenance hash'; end if;
 if jsonb_typeof(coalesce(p_snapshot,'{}'::jsonb))<>'object' then raise exception 'provenance snapshot must be object'; end if;
 if p_snapshot::text ~* '(sb_secret_|sk-(proj-)?[a-z0-9_-]{12,}|gh[pousr]_[a-z0-9]{12,}|BEGIN [A-Z ]*PRIVATE KEY|Bearer[[:space:]]+[A-Za-z0-9._~-]{16,})' then
  raise exception 'secret-like value rejected from provenance';
 end if;
 select t.project_id into v_project_id
 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
 where r.id=p_run_id;
 if v_project_id is null then raise exception 'run not found'; end if;
 insert into public.factory_run_provenance(run_id,project_id,snapshot_hash,snapshot)
 values(p_run_id,v_project_id,p_snapshot_hash,p_snapshot)
 on conflict(run_id) do update set snapshot_hash=excluded.snapshot_hash,snapshot=excluded.snapshot;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 select v_project_id,r.task_id,p_run_id,'system','provenance-recorder','run.provenance.recorded',
   jsonb_build_object('snapshot_hash',p_snapshot_hash) from public.factory_runs r where r.id=p_run_id;
 return jsonb_build_object('run_id',p_run_id,'snapshot_hash',p_snapshot_hash);
end;
$$;
revoke all on function public.factory_record_run_provenance(uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.factory_record_run_provenance(uuid,text,jsonb) to service_role;

create or replace function public.factory_create_replay_request(p_source_run_id uuid,p_mode text default 'offline')
returns jsonb
language plpgsql security invoker set search_path=''
as $$
declare v_prov public.factory_run_provenance%rowtype;v_id uuid;
begin
 if p_mode not in ('offline','shadow') then raise exception 'invalid replay mode'; end if;
 select * into v_prov from public.factory_run_provenance where run_id=p_source_run_id;
 if not found then raise exception 'source run has no provenance snapshot'; end if;
 insert into public.factory_replay_requests(source_run_id,mode,provenance_hash,snapshot,effect,model_calls_allowed)
 values(p_source_run_id,p_mode,v_prov.snapshot_hash,v_prov.snapshot,'none',false)
 returning id into v_id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 select v_prov.project_id,r.task_id,p_source_run_id,'system','replay-controller','replay.requested',
   jsonb_build_object('replay_id',v_id,'mode',p_mode,'effect','none','model_calls_allowed',false)
 from public.factory_runs r where r.id=p_source_run_id;
 return jsonb_build_object('replay_id',v_id,'source_run_id',p_source_run_id,'mode',p_mode,'status','ready',
   'effect','none','model_calls_allowed',false,'snapshot_hash',v_prov.snapshot_hash);
end;
$$;
revoke all on function public.factory_create_replay_request(uuid,text) from public,anon,authenticated;
grant execute on function public.factory_create_replay_request(uuid,text) to service_role;

create or replace function public.factory_record_shadow_decision(
 p_source_run_id uuid,p_replay_id uuid,p_component text,p_component_version text,
 p_input_hash text,p_decision jsonb,p_observed_outcome jsonb default '{}'::jsonb
) returns jsonb
language plpgsql security invoker set search_path=''
as $$
declare v_id uuid;
begin
 if nullif(btrim(p_component),'') is null or nullif(btrim(p_component_version),'') is null then raise exception 'shadow component/version required'; end if;
 if p_input_hash !~ '^[0-9a-f]{64}$' then raise exception 'invalid shadow input hash'; end if;
 if jsonb_typeof(coalesce(p_decision,'{}'::jsonb))<>'object' then raise exception 'shadow decision must be object'; end if;
 insert into public.factory_shadow_decisions(source_run_id,replay_id,component,component_version,input_hash,decision,observed_outcome,effect)
 values(p_source_run_id,p_replay_id,p_component,p_component_version,p_input_hash,p_decision,coalesce(p_observed_outcome,'{}'::jsonb),'none')
 returning id into v_id;
 update public.factory_replay_requests set status='evaluated',evaluated_at=now() where id=p_replay_id;
 return jsonb_build_object('shadow_decision_id',v_id,'effect','none','status','evaluated');
end;
$$;
revoke all on function public.factory_record_shadow_decision(uuid,uuid,text,text,text,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.factory_record_shadow_decision(uuid,uuid,text,text,text,jsonb,jsonb) to service_role;

create or replace function public.factory_propose_improvement(
 p_source_run_id uuid,p_proposal_key text,p_evidence jsonb,p_proposed_change jsonb
) returns jsonb
language plpgsql security invoker set search_path=''
as $$
declare v_id uuid;
begin
 if nullif(btrim(p_proposal_key),'') is null then raise exception 'proposal key required'; end if;
 if jsonb_typeof(coalesce(p_evidence,'{}'::jsonb))<>'object' or jsonb_typeof(coalesce(p_proposed_change,'{}'::jsonb))<>'object' then
  raise exception 'proposal evidence/change must be objects';
 end if;
 insert into public.factory_improvement_proposals(source_run_id,proposal_key,evidence,proposed_change,status,requires_source_control,auto_apply)
 values(p_source_run_id,btrim(p_proposal_key),coalesce(p_evidence,'{}'::jsonb),coalesce(p_proposed_change,'{}'::jsonb),
   'proposed',true,false) returning id into v_id;
 return jsonb_build_object('proposal_id',v_id,'status','proposed','requires_source_control',true,'auto_apply',false);
end;
$$;
revoke all on function public.factory_propose_improvement(uuid,text,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.factory_propose_improvement(uuid,text,jsonb,jsonb) to service_role;

