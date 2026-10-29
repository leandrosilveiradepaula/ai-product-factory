-- Candidate only: MUST NOT be applied until separately authorized in production.
-- Signed GitHub App webhooks are a delivery hint, never authorization to
-- start projects, invoke paid models, merge a PR, or publish production.
begin;

create table public.factory_external_webhook_wakes (
 delivery_id uuid primary key,
 project_id uuid not null references public.factory_projects(id) on delete restrict,
 run_id uuid not null references public.factory_runs(id) on delete restrict,
 repository_id bigint not null check(repository_id>0),
 installation_id bigint not null check(installation_id>0),
 repository text not null,
 event_type text not null check(event_type in ('check_run','workflow_run','deployment_status','pull_request')),
 candidate_commit text not null check(candidate_commit ~ '^[0-9a-f]{40}$'),
 pr_number integer,
 execution_generation bigint not null check(execution_generation>0),
 status text not null default 'pending' check(status in ('pending','claimed','requested','retryable','suppressed','exhausted')),
 attempts integer not null default 0 check(attempts between 0 and 3),
 lease_until timestamptz,
 next_attempt_at timestamptz not null default now(),
 last_result text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 check((status='claimed' and lease_until is not null) or (status<>'claimed' and lease_until is null))
);
create index factory_external_webhook_wakes_due on public.factory_external_webhook_wakes(next_attempt_at)
 where status in ('pending','retryable','claimed');
alter table public.factory_external_webhook_wakes enable row level security;
revoke all on public.factory_external_webhook_wakes from public,anon,authenticated;
grant select,insert,update on public.factory_external_webhook_wakes to service_role;

create function public.factory_claim_external_webhook_wake_v1(
 p_delivery_id uuid,p_event_type text,p_action text,p_repository_id bigint,
 p_repository text,p_installation_id bigint,p_candidate_commit text,
 p_pr_number integer default null
) returns jsonb language plpgsql security invoker set search_path='' as $body$
declare
 v_ids uuid[];
 v_run public.factory_runs%rowtype;
 v_project uuid;
 v_generation bigint;
 v_receipt public.factory_external_webhook_wakes%rowtype;
 v_expected_status text;
begin
 if p_delivery_id is null or p_repository_id is null or p_repository_id<1
    or p_installation_id is null or p_installation_id<1
    or p_repository is null or length(p_repository)>180
    or p_repository !~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'
    or p_candidate_commit is null or p_candidate_commit !~ '^[0-9a-f]{40}$'
    or (p_pr_number is not null and p_pr_number<1)
 then raise exception 'invalid GitHub event identity';end if;
 if not ((p_event_type in ('workflow_run','check_run') and p_action='completed')
      or (p_event_type='deployment_status' and p_action='created')
      or (p_event_type='pull_request' and p_action='closed' and p_pr_number is not null))
 then raise exception 'invalid GitHub event type';end if;
 v_expected_status:=case when p_event_type in ('workflow_run','check_run') then 'ci_pending'
   when p_event_type='deployment_status' then 'preview_ready'
   else 'awaiting_release' end;

 -- Fail closed on ambiguous candidates. Repository and installation identities
 -- must match server-owned Control Plane facts; never trust payload-only IDs.
 select array_agg(found.id) into v_ids from (
  select r.id from public.factory_runs r
  join public.factory_tasks t on t.id=r.task_id
  join public.factory_projects p on p.id=t.project_id
  join public.factory_project_github_access a on a.project_id=p.id
  join public.factory_project_execution_controls c on c.project_id=p.id
  where p.is_active=true and c.state='running'
    and p.repository=p_repository and a.repository=p_repository
    and a.repository_id=p_repository_id and a.installation_id=p_installation_id
    and a.auth_mode='github_app' and a.status='ready'
    and r.candidate_commit=p_candidate_commit and r.status=v_expected_status
    and (r.execution_route is null or lower(r.execution_route) not in ('direct','codex')
      or (jsonb_typeof(r.metadata->'execution_generation')='number'
       and (r.metadata->>'execution_generation') ~ '^[0-9]{1,12}$'
       and (r.metadata->>'execution_generation')::bigint=c.generation))
    and (p_pr_number is null or
         exists(select 1 from public.factory_tool_usage u
          where u.run_id=r.id and u.operation='create_pr'
            and u.metadata->>'pr'=p_pr_number::text)
         or (r.metadata->>'pr_number'=p_pr_number::text))
  order by r.created_at,r.id limit 2
 ) found;
 if coalesce(array_length(v_ids,1),0)<>1 then
  return jsonb_build_object('status','ignored');
 end if;
 select r.* into v_run from public.factory_runs r where r.id=v_ids[1];
 select t.project_id,c.generation into v_project,v_generation
 from public.factory_tasks t
 join public.factory_project_execution_controls c on c.project_id=t.project_id
 where t.id=v_run.task_id;

 insert into public.factory_external_webhook_wakes(
  delivery_id,project_id,run_id,repository_id,installation_id,repository,
  event_type,candidate_commit,pr_number,execution_generation
 )values(
  p_delivery_id,v_project,v_run.id,p_repository_id,p_installation_id,
  p_repository,p_event_type,p_candidate_commit,p_pr_number,v_generation
 ) on conflict(delivery_id) do nothing;
 select * into v_receipt from public.factory_external_webhook_wakes
 where delivery_id=p_delivery_id for update;
 if not found or v_receipt.run_id<>v_run.id or v_receipt.repository_id<>p_repository_id
   or v_receipt.repository<>p_repository or v_receipt.event_type<>p_event_type
   or v_receipt.candidate_commit<>p_candidate_commit
   or v_receipt.installation_id<>p_installation_id
   or v_receipt.pr_number is distinct from p_pr_number
 then raise exception 'webhook delivery identity drift';end if;
 if v_receipt.execution_generation<>v_generation then
  update public.factory_external_webhook_wakes set status='suppressed',
   lease_until=null,last_result='epoch_revoked',updated_at=now()
   where delivery_id=p_delivery_id;
  return jsonb_build_object('status','ignored');
 end if;
 if v_receipt.status in ('requested','suppressed','exhausted')
    or (v_receipt.status='claimed' and v_receipt.lease_until>now())
 then return jsonb_build_object('status','duplicate');end if;
 if v_receipt.next_attempt_at>now() then
  return jsonb_build_object('status','deferred');end if;
 if v_receipt.attempts>=3 then
  update public.factory_external_webhook_wakes set status='exhausted',
   lease_until=null,last_result='attempt_limit',updated_at=now()
   where delivery_id=p_delivery_id;
  return jsonb_build_object('status','exhausted');
 end if;
 update public.factory_external_webhook_wakes set status='claimed',
   attempts=v_receipt.attempts+1,lease_until=now()+interval '90 seconds',updated_at=now()
 where delivery_id=p_delivery_id;
 return jsonb_build_object('status','claimed','run_id',v_run.id,'attempt',v_receipt.attempts+1);
end;
$body$;
revoke all on function public.factory_claim_external_webhook_wake_v1(uuid,text,text,bigint,text,bigint,text,integer)
 from public,anon,authenticated;
grant execute on function public.factory_claim_external_webhook_wake_v1(uuid,text,text,bigint,text,bigint,text,integer)
 to service_role;

create function public.factory_ack_external_webhook_wake_v1(
 p_delivery_id uuid,p_attempt integer,p_outcome text
) returns jsonb language plpgsql security invoker set search_path='' as $body$
declare v_receipt public.factory_external_webhook_wakes%rowtype;
 v_state text;v_generation bigint;v_status text;
begin
 if p_delivery_id is null or p_attempt is null or p_attempt<1 or p_attempt>3
    or p_outcome not in ('requested','failed')
 then raise exception 'invalid webhook acknowledgement';end if;
 select * into v_receipt from public.factory_external_webhook_wakes
 where delivery_id=p_delivery_id for update;
 if not found or v_receipt.status<>'claimed' or v_receipt.attempts<>p_attempt
    or v_receipt.lease_until<=now()
 then raise exception 'lost webhook lease';end if;
 select c.state,c.generation into v_state,v_generation
 from public.factory_project_execution_controls c
 where c.project_id=v_receipt.project_id for share;
 v_status:=case when v_state is distinct from 'running'
      or v_generation is distinct from v_receipt.execution_generation then 'suppressed'
  when p_outcome='requested' then 'requested'
  when p_attempt>=3 then 'exhausted'
  else 'retryable' end;
 update public.factory_external_webhook_wakes set status=v_status,
  lease_until=null,last_result=p_outcome,updated_at=now(),
  next_attempt_at=case when v_status='retryable' then now()+interval '60 seconds'
   else next_attempt_at end
 where delivery_id=p_delivery_id;
 insert into public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_receipt.project_id,v_receipt.run_id,'system','github-app-webhook',
 'github.webhook.wake_acknowledged',
 jsonb_build_object('delivery_id',p_delivery_id,'event_type',v_receipt.event_type,
 'status',v_status,'attempt',p_attempt,'candidate_commit',v_receipt.candidate_commit));
 return jsonb_build_object('status',v_status);
end;
$body$;
revoke all on function public.factory_ack_external_webhook_wake_v1(uuid,integer,text)
 from public,anon,authenticated;
grant execute on function public.factory_ack_external_webhook_wake_v1(uuid,integer,text)
 to service_role;

commit;