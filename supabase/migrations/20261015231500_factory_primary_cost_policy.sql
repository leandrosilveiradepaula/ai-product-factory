-- Admin-configurable primary-model cost policy. HUMAN PROD MIGRATION GATE.
-- Apply this before merging the runtime that removes workflow budgets.
create table if not exists public.factory_primary_cost_policy (
 policy_key text primary key default 'primary'
  constraint factory_primary_cost_policy_single_key check (policy_key='primary'),
 budget_usd numeric(12,4) not null
  constraint factory_primary_cost_policy_budget check (budget_usd between 0.01 and 100000.00),
 reserve_usd numeric(12,4) not null
  constraint factory_primary_cost_policy_reserve check (reserve_usd between 0.0001 and budget_usd),
 version integer not null default 1 check (version>0),
 updated_by uuid references auth.users(id) on delete set null,
 updated_at timestamptz not null default now()
);
alter table public.factory_primary_cost_policy enable row level security;
revoke all on table public.factory_primary_cost_policy from public,anon,authenticated;
grant select,update on table public.factory_primary_cost_policy to service_role;
-- Intentionally no policies for anon/authenticated, even for reads.
insert into public.factory_primary_cost_policy(policy_key,budget_usd,reserve_usd,version)
values('primary',10.00,0.50,1) on conflict(policy_key) do nothing;

create or replace function public.factory_update_primary_cost_policy(
 p_actor_user_id uuid,p_expected_version integer,p_budget_usd numeric,
 p_reserve_usd numeric,p_reason text,p_confirm_paid_limit boolean
) returns jsonb language plpgsql security invoker set search_path to ''
as $function$
declare
  previous public.factory_primary_cost_policy%rowtype;
  changed public.factory_primary_cost_policy%rowtype;
begin
 if p_actor_user_id is null or not exists(
  select 1 from public.factory_console_operators
  where user_id=p_actor_user_id and role='admin' and is_active=true
 ) then raise exception 'admin authorization required' using errcode='PT403'; end if;
 if p_confirm_paid_limit is distinct from true then
  raise exception 'explicit paid limit confirmation required' using errcode='PT400';
 end if;
 if p_expected_version is null or p_expected_version<1
    or p_budget_usd is null or p_reserve_usd is null
    or p_budget_usd not between 0.01 and 100000.00
    or p_reserve_usd not between 0.0001 and p_budget_usd
    or p_budget_usd <> round(p_budget_usd,4)
    or p_reserve_usd <> round(p_reserve_usd,4)
    or char_length(btrim(coalesce(p_reason,''))) not between 12 and 300
 then raise exception 'invalid cost policy update' using errcode='PT400'; end if;
 select * into previous from public.factory_primary_cost_policy
  where policy_key='primary' for update;
 if not found or previous.version is distinct from p_expected_version then
  raise exception 'stale cost policy version' using errcode='PT409'; end if;
 if previous.budget_usd=p_budget_usd and previous.reserve_usd=p_reserve_usd then
  raise exception 'no financial settings changed' using errcode='PT400'; end if;
 update public.factory_primary_cost_policy set
   budget_usd=p_budget_usd,reserve_usd=p_reserve_usd,
   version=previous.version+1,
   updated_by=p_actor_user_id,updated_at=now()
  where policy_key='primary' and version=p_expected_version
  returning * into changed;
 if not found then raise exception 'stale cost policy version' using errcode='PT409'; end if;
 insert into public.factory_audit_events(actor_type,actor_ref,event_type,payload)
 values('human',p_actor_user_id::text,'factory.cost_policy.updated',jsonb_build_object(
  'previous_version',previous.version,'new_version',changed.version,
  'previous_budget_usd',previous.budget_usd,'new_budget_usd',changed.budget_usd,
  'previous_reserve_usd',previous.reserve_usd,'new_reserve_usd',changed.reserve_usd,
  'reason',btrim(p_reason),'source','factory-console'
 ));
 return jsonb_build_object(
  'policy_key',changed.policy_key,'budget_usd',changed.budget_usd,
  'reserve_usd',changed.reserve_usd,'version',changed.version,
  'updated_at',changed.updated_at
 );
end;
$function$;
revoke all on function public.factory_update_primary_cost_policy(uuid,integer,numeric,numeric,text,boolean)
 from public,anon,authenticated;
grant execute on function public.factory_update_primary_cost_policy(uuid,integer,numeric,numeric,text,boolean)
 to service_role;
