-- Candidate-only additive recovery. Apply to production only after the
-- separately authorized migration gate and human merge of this PR.
-- A trusted running worker can consume a retryable HMAC-verified wake intent
-- after its own schedule-probe; this does NOT simulate a GitHub HTTP 204,
-- execute any work, or assert a production release.
begin;

create function public.factory_reconcile_external_webhook_wakes_v1(
 p_runner_run_id bigint,
 p_ci_work boolean,
 p_preview_work boolean,
 p_release_work boolean,
 p_max_items integer default 4
) returns jsonb
language plpgsql security invoker set search_path='' as $body$
declare
 v_w public.factory_external_webhook_wakes%rowtype;
 v_r public.factory_runs%rowtype;
 v_context_ok boolean;
 v_generation bigint;
 v_valid boolean;
 v_route_ok boolean;
 v_pr_ok boolean;
 v_expected_status text;
 v_lane_ready boolean;
 v_match_count integer;
 v_seen integer:=0;
 v_observed integer:=0;
 v_suppressed integer:=0;
 v_exhausted integer:=0;
 v_deferred integer:=0;
 v_outcome text;
begin
 if p_runner_run_id is null or p_runner_run_id<=0
    or p_ci_work is null or p_preview_work is null or p_release_work is null
    or p_max_items is null or p_max_items not between 1 and 8
 then raise exception 'invalid external webhook recovery request';end if;

 for v_w in
  select w.* from public.factory_external_webhook_wakes w
  where (w.status in ('pending','retryable') and w.next_attempt_at<=now())
     or (w.status='claimed' and w.lease_until<=now())
  order by w.next_attempt_at,w.created_at,w.delivery_id
  limit p_max_items for update skip locked
 loop
  v_seen:=v_seen+1;
  v_context_ok:=false;
  select (
     p.is_active=true and p.repository=v_w.repository
     and c.state='running' and c.generation=v_w.execution_generation
     and a.repository=v_w.repository and a.repository_id=v_w.repository_id
     and a.installation_id=v_w.installation_id
     and a.auth_mode='github_app' and a.status='ready'
    ),c.generation
    into v_context_ok,v_generation
  from public.factory_projects p
  join public.factory_project_execution_controls c on c.project_id=p.id
  join public.factory_project_github_access a on a.project_id=p.id
  where p.id=v_w.project_id;

  select r.* into v_r from public.factory_runs r
  join public.factory_tasks t on t.id=r.task_id
  where r.id=v_w.run_id and t.project_id=v_w.project_id;

  v_expected_status:=case when v_w.event_type in ('workflow_run','check_run') then 'ci_pending'
    when v_w.event_type='deployment_status' then 'preview_ready'
    when v_w.event_type='pull_request' then 'awaiting_release'
    else null end;
  v_lane_ready:=case when v_w.event_type in ('workflow_run','check_run') then p_ci_work
    when v_w.event_type='deployment_status' then p_preview_work
    when v_w.event_type='pull_request' then p_release_work
    else false end;

  v_route_ok:=v_r.execution_route is null or lower(v_r.execution_route) not in ('direct','codex')
    or case when jsonb_typeof(v_r.metadata->'execution_generation')='number'
       and (v_r.metadata->>'execution_generation') ~ '^[0-9]{1,12}$'
      then (v_r.metadata->>'execution_generation')::bigint=v_w.execution_generation
      else false end;
  v_pr_ok:=v_w.pr_number is null
    or v_r.metadata->>'pr_number'=v_w.pr_number::text
    or exists(select 1 from public.factory_tool_usage u
      where u.run_id=v_w.run_id and u.operation='create_pr'
        and u.metadata->>'pr'=v_w.pr_number::text);

  -- Reject a changed stage, switched repo/install, paused project, epoch
  -- change, missing run/PR proof, or ambiguous current run. Old identities
  -- can never be re-used to initiate a new Start, claim or delivery.
  v_valid:=coalesce(v_context_ok,false)
   and v_expected_status is not null
   and v_r.id is not null
   and v_r.candidate_commit=v_w.candidate_commit
   and v_r.status=v_expected_status
   and coalesce(v_route_ok,false) and coalesce(v_pr_ok,false);

  if v_valid then
   select count(*) into v_match_count from (
    select r.id from public.factory_runs r
    join public.factory_tasks t on t.id=r.task_id
    where t.project_id=v_w.project_id and r.status=v_expected_status
      and r.candidate_commit=v_w.candidate_commit
      and (r.execution_route is null or lower(r.execution_route) not in ('direct','codex')
         or case when jsonb_typeof(r.metadata->'execution_generation')='number'
              and (r.metadata->>'execution_generation') ~ '^[0-9]{1,12}$'
             then (r.metadata->>'execution_generation')::bigint=v_w.execution_generation
             else false end)
    limit 2
   ) matches;
   v_valid:=v_match_count=1;
  end if;

  if not v_valid then
   v_outcome:='suppressed';
   update public.factory_external_webhook_wakes
    set status='suppressed',lease_until=null,
        last_result='recovery_identity_or_epoch_revoked',updated_at=now()
    where delivery_id=v_w.delivery_id;
   v_suppressed:=v_suppressed+1;
  elsif v_w.attempts>=3 then
   v_outcome:='exhausted';
   update public.factory_external_webhook_wakes
    set status='exhausted',lease_until=null,
        last_result='recovery_attempt_limit',updated_at=now()
    where delivery_id=v_w.delivery_id;
   v_exhausted:=v_exhausted+1;
  elsif v_lane_ready then
   v_outcome:='runner_observed';
   -- A running, same-repo Factory worker has already probed the matching
   -- durable lane. No further repository_dispatch is necessary. "requested"
   -- is terminal for dedup, while last_result makes this distinct from 204.
   update public.factory_external_webhook_wakes
    set status='requested',lease_until=null,
        last_result='runner_probe_observed_no_http_dispatch',updated_at=now()
    where delivery_id=v_w.delivery_id;
   v_observed:=v_observed+1;
  else
   v_outcome:='deferred';
   if v_w.status='claimed' then
    update public.factory_external_webhook_wakes
     set status='retryable',lease_until=null,
         next_attempt_at=now()+interval '60 seconds',
         last_result='expired_lease_no_eligible_lane',updated_at=now()
     where delivery_id=v_w.delivery_id;
   end if;
   v_deferred:=v_deferred+1;
  end if;

  if v_outcome<>'deferred' then
   insert into public.factory_audit_events(
     project_id,run_id,actor_type,actor_ref,event_type,payload
   ) values (
     v_w.project_id,v_w.run_id,'system','gha-webhook-recovery',
     'github.webhook.wake_reconciled',
     jsonb_build_object(
       'delivery_id',v_w.delivery_id,'candidate_commit',v_w.candidate_commit,
       'event_type',v_w.event_type,'outcome',v_outcome,
       'workflow_run_id',p_runner_run_id,'http_dispatch_204',false,
       'task_executed',false
     )
   );
  end if;
 end loop;
 return jsonb_build_object(
   'status','ok','inspected',v_seen,'runner_observed',v_observed,
   'suppressed',v_suppressed,'exhausted',v_exhausted,'deferred',v_deferred
 );
end;
$body$;

revoke all on function public.factory_reconcile_external_webhook_wakes_v1(
 bigint,boolean,boolean,boolean,integer) from public,anon,authenticated;
grant execute on function public.factory_reconcile_external_webhook_wakes_v1(
 bigint,boolean,boolean,boolean,integer) to service_role;
commit;
