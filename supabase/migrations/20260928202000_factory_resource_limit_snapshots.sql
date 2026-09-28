create table if not exists public.factory_resource_limit_snapshots (
 id uuid primary key default gen_random_uuid(),
 provider text not null,
 resource_key text not null,
 metric_key text not null,
 used_value numeric,
 limit_value numeric,
 unit text not null default 'count',
 window_key text,
 window_started_at timestamptz,
 resets_at timestamptz,
 quality text not null check (quality in ('exact','derived','provider_blocked','unknown')),
 source text not null,
 status text not null check (status in ('normal','attention','critical','blocked','unknown')),
 metadata jsonb not null default '{}'::jsonb,
 observed_at timestamptz not null default now(),
 constraint factory_resource_limit_no_secret_metadata check (
  not (metadata ?| array['token','secret','password','api_key','authorization','credential'])
 )
);
create index if not exists factory_resource_limit_snapshots_lookup_idx
 on public.factory_resource_limit_snapshots(provider,resource_key,metric_key,observed_at desc);
alter table public.factory_resource_limit_snapshots enable row level security;
revoke all on public.factory_resource_limit_snapshots from public,anon,authenticated;

create or replace function public.factory_record_resource_limit(
 p_provider text,p_resource_key text,p_metric_key text,p_used_value numeric,p_limit_value numeric,
 p_unit text,p_window_key text,p_window_started_at timestamptz,p_resets_at timestamptz,
 p_quality text,p_source text,p_metadata jsonb default '{}'::jsonb
) returns uuid language plpgsql security definer set search_path='' as $$
declare v_status text; v_id uuid; v_ratio numeric;
begin
 if p_used_value is not null and p_used_value < 0 then raise exception 'used value must be non-negative'; end if;
 if p_limit_value is not null and p_limit_value <= 0 then raise exception 'limit value must be positive'; end if;
 if p_metadata ?| array['token','secret','password','api_key','authorization','credential'] then raise exception 'secret-like metadata is forbidden'; end if;
 if p_quality='provider_blocked' then v_status:='blocked';
 elsif p_used_value is null or p_limit_value is null then v_status:='unknown';
 else
  v_ratio:=p_used_value/p_limit_value;
  v_status:=case when v_ratio>=1 then 'blocked' when v_ratio>=0.9 then 'critical' when v_ratio>=0.7 then 'attention' else 'normal' end;
 end if;
 insert into public.factory_resource_limit_snapshots(provider,resource_key,metric_key,used_value,limit_value,unit,window_key,window_started_at,resets_at,quality,source,status,metadata)
 values(p_provider,p_resource_key,p_metric_key,p_used_value,p_limit_value,coalesce(nullif(p_unit,''),'count'),p_window_key,p_window_started_at,p_resets_at,p_quality,p_source,v_status,coalesce(p_metadata,'{}'::jsonb))
 returning id into v_id;
 return v_id;
end;$$;
revoke all on function public.factory_record_resource_limit(text,text,text,numeric,numeric,text,text,timestamptz,timestamptz,text,text,jsonb) from public,anon,authenticated;
grant execute on function public.factory_record_resource_limit(text,text,text,numeric,numeric,text,text,timestamptz,timestamptz,text,text,jsonb) to service_role;
