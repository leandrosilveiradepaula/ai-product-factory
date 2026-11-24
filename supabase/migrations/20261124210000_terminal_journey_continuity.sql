-- Continuity after a genuinely finished V2 delivery. No data mutation on install.
-- Explicit per-project admin opt-in; the worker never promotes or merges main.
begin;

create table if not exists public.factory_journey_refresh_permissions_v2(
 project_id uuid primary key references public.factory_projects(id) on delete restrict,
 repository text not null, enabled boolean not null,
 authorized_by uuid not null, updated_at timestamptz not null default now()
);
alter table public.factory_journey_refresh_permissions_v2 enable row level security;
revoke all on table public.factory_journey_refresh_permissions_v2 from public,anon,authenticated;
grant select,insert,update on table public.factory_journey_refresh_permissions_v2 to service_role;

create table if not exists public.factory_journey_refresh_receipts_v2(
 journey_id uuid primary key references public.factory_journeys(id) on delete restrict,
 project_id uuid not null references public.factory_projects(id) on delete restrict,
 prior_journey_id uuid not null references public.factory_journeys(id) on delete restrict,
 evidence jsonb not null, receipt jsonb not null,
 created_at timestamptz not null default now()
);
alter table public.factory_journey_refresh_receipts_v2 enable row level security;
revoke all on table public.factory_journey_refresh_receipts_v2 from public,anon,authenticated;
grant select,insert on table public.factory_journey_refresh_receipts_v2 to service_role;

-- This is an authenticated administrative configuration action, not a Start.
-- It explicitly authorizes one nonproduction base ref for each legitimate
-- future request. No branch or model is created by this function.
create or replace function public.factory_authorize_journey_refresh_v2(
 p_project_key text,p_actor_id uuid,p_expected_generation bigint,
 p_expected_version bigint,p_expected_policy_digest text,p_enabled boolean
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare p public.factory_projects%rowtype; c public.factory_project_execution_controls%rowtype;
 old public.factory_journey_refresh_permissions_v2%rowtype; policy jsonb;
begin
 if p_enabled is null or p_expected_policy_digest is null or p_expected_policy_digest !~ '^[0-9a-f]{64}$'
    or not exists(select 1 from public.factory_console_operators op
       where op.user_id=p_actor_id and op.is_active and op.role='admin')
 then raise exception 'unauthorized journey refresh policy' using errcode='PT403'; end if;
 select * into p from public.factory_projects where project_key=p_project_key
    and is_active and project_kind='existing' for update;
 if not found then raise exception 'existing project not found' using errcode='PT404'; end if;
 select * into c from public.factory_project_execution_controls where project_id=p.id for update;
 policy:=p.manifest->'journey_delivery_binding_v2';
 if c.generation is distinct from p_expected_generation or c.version is distinct from p_expected_version
    or policy->>'digest' is distinct from p_expected_policy_digest
    or policy->>'enabled' is distinct from 'true'
    or policy->>'source_mode' is distinct from 'main_snapshot'
    or policy->>'release_base_ref' is distinct from 'main'
    or policy->>'preview_base_ref' not like 'preview/%'
    or policy->>'source_commit_pin' is null
    or policy->>'source_commit_pin' !~ '^[0-9a-f]{40}$'
    or policy->>'preview_base_source_sha' is distinct from policy->>'source_commit_pin'
    or (p_enabled and (c.state is distinct from 'running' or not public.factory_control_quiescent(p.id)
       or exists(select 1 from public.factory_journeys j where j.project_id=p.id
                  and j.state not in ('closed','released_observed','superseded'))))
 then raise exception 'journey refresh authorization stale or unsafe' using errcode='PT409'; end if;
 select * into old from public.factory_journey_refresh_permissions_v2 where project_id=p.id;
 if found and old.repository=p.repository and old.enabled=p_enabled and old.authorized_by=p_actor_id
 then return jsonb_build_object('project_id',p.id,'enabled',p_enabled,'changed',false); end if;
 insert into public.factory_journey_refresh_permissions_v2(project_id,repository,enabled,authorized_by)
 values(p.id,p.repository,p_enabled,p_actor_id)
 on conflict(project_id) do update set repository=excluded.repository,enabled=excluded.enabled,
    authorized_by=excluded.authorized_by,updated_at=now();
 insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
 values(p.id,'human',p_actor_id::text,'journey.refresh.authorization_changed',
    jsonb_build_object('enabled',p_enabled,'repository',p.repository,
      'policy_digest',p_expected_policy_digest,'generation',c.generation,
      'production_release_authorized',false));
 return jsonb_build_object('project_id',p.id,'enabled',p_enabled,'changed',true);
end $fn$;

-- Serialized preflight for one authentic, as-yet unbound request. Prior
-- Preview-only delivery is NOT assumed to be in main; the broker verifies
-- both old source and prior delivered SHA against current main independently.
create or replace function public.factory_plan_terminal_journey_refresh_v2(
 p_project_key text,p_journey_id uuid,p_expected_generation bigint,
 p_expected_version bigint,p_expected_policy_digest text
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare p public.factory_projects%rowtype; c public.factory_project_execution_controls%rowtype;
 j public.factory_journeys%rowtype; prior public.factory_journeys%rowtype;
 policy jsonb; prior_delivery text; new_ref text;
begin
 select * into p from public.factory_projects where project_key=p_project_key
     and is_active and project_kind='existing' for update;
 if not found then raise exception 'existing project not found' using errcode='PT404'; end if;
 select * into c from public.factory_project_execution_controls where project_id=p.id for update;
 select * into j from public.factory_journeys where id=p_journey_id and project_id=p.id for update;
 policy:=p.manifest->'journey_delivery_binding_v2';
 if c.state is distinct from 'running' or c.generation is distinct from p_expected_generation
    or c.version is distinct from p_expected_version
    or j.id is null or j.state not in ('awaiting_source','intake_accepted')
    or j.source_commit is not null or j.execution_generation is not null
    or policy->>'enabled' is distinct from 'true' or policy->>'source_mode' is distinct from 'main_snapshot'
    or policy->>'release_base_ref' is distinct from 'main'
    or policy->>'digest' is distinct from p_expected_policy_digest
    or policy->>'version' is null or policy->>'version' !~ '^[1-9][0-9]*$'
    or policy->>'source_commit_pin' is null or policy->>'source_commit_pin' !~ '^[a-f0-9]{40}$'
    or policy->>'preview_base_source_sha' is distinct from policy->>'source_commit_pin'
    or policy->>'preview_base_ref' is null or policy->>'preview_base_ref' not like 'preview/%'
    or not exists(select 1 from public.factory_journey_refresh_permissions_v2 a
         join public.factory_console_operators op on op.user_id=a.authorized_by
         where a.project_id=p.id and a.repository=p.repository and a.enabled
           and op.is_active and op.role='admin')
 then raise exception 'journey refresh not authorized or stale' using errcode='PT409'; end if;
 select * into prior from public.factory_journeys
 where project_id=p.id and id<>j.id order by created_at desc,id desc limit 1 for share;
 if prior.id is null or prior.state not in ('closed','released_observed')
    or prior.policy_digest is distinct from policy->>'digest'
    or prior.project_policy_version is distinct from (policy->>'version')::integer
    or prior.execution_generation is distinct from c.generation
    or prior.source_commit is distinct from policy->>'source_commit_pin'
    or prior.binding->>'repository' is distinct from p.repository
    or prior.binding->>'preview_base_ref' is distinct from policy->>'preview_base_ref'
 then raise exception 'previous journey not provably terminal under this policy' using errcode='PT409'; end if;
 prior_delivery:=case when prior.state='released_observed' then prior.production_release_sha else prior.preview_merge_sha end;
 if prior_delivery is null or prior_delivery !~ '^[a-f0-9]{40}$'
    or not public.factory_control_quiescent(p.id)
    or exists(select 1 from public.factory_journeys k where k.project_id=p.id and k.id<>j.id
              and k.state not in ('closed','released_observed','superseded'))
    or exists(select 1 from public.factory_tasks t where t.journey_id=j.id)
    or exists(select 1 from public.factory_journey_source_evidence_v2 e where e.journey_id=j.id)
    or exists(select 1 from public.factory_human_gates g join public.factory_runs r on r.id=g.run_id
             join public.factory_tasks t on t.id=r.task_id where t.project_id=p.id and g.status='pending')
    or exists(select 1 from public.factory_change_sets cs where cs.project_id=p.id and
       (cs.lease_owner is not null or cs.lease_expires_at is not null or cs.status not in ('completed','superseded','blocked')))
    or exists(select 1 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
       where t.project_id=p.id and (r.lease_owner is not null or r.lease_expires_at is not null or
       (r.status not in ('completed','failed','blocked','cancelled','integrated','merged','superseded')
        and not (r.status='preview_ready' and t.status='completed')
        and not (r.status='repair_pending' and t.status in ('completed','integrated') and exists(
          select 1 from public.factory_change_sets cs where cs.project_id=p.id
            and cs.id::text=r.metadata->>'change_set_id' and cs.root_task_id=t.id
            and cs.status='completed' and cs.lease_owner is null and cs.lease_expires_at is null)))))
 then raise exception 'terminal continuity has unfinished work or missing delivery receipt' using errcode='PT409'; end if;
 new_ref:='preview/journey-base-'||j.id::text;
 if exists(select 1 from public.factory_journeys k where k.project_id=p.id and
           k.binding->>'preview_base_ref'=new_ref)
 then raise exception 'next Preview base already belongs to another journey' using errcode='PT409'; end if;
 return jsonb_build_object('project_id',p.id,'repository',p.repository,'journey_id',j.id,
   'request_id',j.request_id,'prior_journey_id',prior.id,'prior_source_sha',prior.source_commit,
   'prior_delivery_sha',prior_delivery,'prior_policy_digest',policy->>'digest',
   'generation',c.generation,'version',c.version,'preview_ref',new_ref);
end $fn$;

create or replace function public.factory_commit_terminal_journey_refresh_v2(
 p_project_key text,p_journey_id uuid,p_expected_generation bigint,
 p_expected_version bigint,p_expected_policy_digest text,p_evidence jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare plan jsonb; p public.factory_projects%rowtype; policy jsonb; result jsonb;
 sha text; digest text; previous public.factory_journey_refresh_receipts_v2%rowtype;
begin
 select * into p from public.factory_projects where project_key=p_project_key for update;
 select * into previous from public.factory_journey_refresh_receipts_v2 where journey_id=p_journey_id;
 if found then
   if previous.project_id is distinct from p.id or previous.evidence is distinct from p_evidence
      or previous.receipt->>'prior_policy_digest' is distinct from p_expected_policy_digest
      or previous.receipt->>'previous_generation' is distinct from p_expected_generation::text
      or previous.receipt->>'previous_version' is distinct from p_expected_version::text
   then raise exception 'terminal refresh replay differs' using errcode='PT409'; end if;
   return previous.receipt;
 end if;
 plan:=public.factory_plan_terminal_journey_refresh_v2(p_project_key,p_journey_id,
      p_expected_generation,p_expected_version,p_expected_policy_digest);
 sha:=p_evidence->>'main_sha';
 if jsonb_typeof(p_evidence) is distinct from 'object' or sha is null or sha !~ '^[a-f0-9]{40}$'
    or p_evidence->>'preview_sha' is distinct from sha
    or p_evidence->>'repository' is distinct from plan->>'repository'
    or p_evidence->>'preview_ref' is distinct from plan->>'preview_ref'
    or p_evidence->>'prior_source_sha' is distinct from plan->>'prior_source_sha'
    or p_evidence->>'prior_delivery_sha' is distinct from plan->>'prior_delivery_sha'
    or p_evidence->>'source_ancestor_verified' is distinct from 'true'
    or p_evidence->>'delivery_ancestor_verified' is distinct from 'true'
    or p_evidence->>'verification_source' is distinct from 'github_exact_refs'
    or p_evidence->>'production_release_authorized' is distinct from 'false'
 then raise exception 'invalid exact GitHub terminal refresh evidence' using errcode='PT409'; end if;
 policy:=p.manifest->'journey_delivery_binding_v2';
 policy:=(policy-'digest')||jsonb_build_object('version',(policy->>'version')::integer+1,
   'source_commit_pin',sha,'preview_base_source_sha',sha,'preview_base_ref',plan->>'preview_ref');
 digest:=encode(extensions.digest(convert_to(policy::text,'UTF8'),'sha256'),'hex');
 policy:=policy||jsonb_build_object('digest',digest);
 update public.factory_projects set manifest=jsonb_set(manifest,'{journey_delivery_binding_v2}',policy,false),
    updated_at=now() where id=p.id and manifest->'journey_delivery_binding_v2'->>'digest'=p_expected_policy_digest;
 if not found then raise exception 'policy CAS lost' using errcode='PT409'; end if;
 update public.factory_project_execution_controls set generation=generation+1,version=version+1,updated_at=now()
 where project_id=p.id and state='running' and generation=p_expected_generation and version=p_expected_version;
 if not found then raise exception 'control CAS lost' using errcode='PT409'; end if;
 result:=plan||jsonb_build_object('status','rotated','previous_generation',p_expected_generation,
    'previous_version',p_expected_version,'generation',p_expected_generation+1,'version',p_expected_version+1,
    'policy_version',(policy->>'version')::integer,'policy_digest',digest,'source_commit',sha,
    'production_release_authorized',false);
 insert into public.factory_journey_refresh_receipts_v2(journey_id,project_id,prior_journey_id,evidence,receipt)
 values(p_journey_id,p.id,(plan->>'prior_journey_id')::uuid,p_evidence,result);
 insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
 values(p.id,'system','terminal-journey-refresh','journey.source_policy.rotated',result);
 return result;
end $fn$;

revoke all on function public.factory_authorize_journey_refresh_v2(text,uuid,bigint,bigint,text,boolean) from public,anon,authenticated;
grant execute on function public.factory_authorize_journey_refresh_v2(text,uuid,bigint,bigint,text,boolean) to service_role;
revoke all on function public.factory_plan_terminal_journey_refresh_v2(text,uuid,bigint,bigint,text) from public,anon,authenticated;
grant execute on function public.factory_plan_terminal_journey_refresh_v2(text,uuid,bigint,bigint,text) to service_role;
revoke all on function public.factory_commit_terminal_journey_refresh_v2(text,uuid,bigint,bigint,text,jsonb) from public,anon,authenticated;
grant execute on function public.factory_commit_terminal_journey_refresh_v2(text,uuid,bigint,bigint,text,jsonb) to service_role;

-- Settle ONLY an old SQL grant repair that was superseded by an independently
-- reviewed, human-merged candidate. Old failed attempts, repair jobs, Work
-- Units, costs and recovery requests are immutable historical evidence.
create or replace function public.factory_settle_terminal_security_repair_v1(
 p_repair_id uuid,p_apply boolean default false
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare j public.factory_repair_jobs%rowtype; p public.factory_projects%rowtype;
 c public.factory_change_sets%rowtype; root public.factory_runs%rowtype;
 t public.factory_tasks%rowtype; u public.factory_change_set_work_units%rowtype;
 s public.factory_specialist_lane_jobs%rowtype; old_run public.factory_runs%rowtype;
 v_ctl public.factory_project_execution_controls%rowtype;
 child record; old_status text; v_children uuid[]:='{}'; v_tasks uuid[];
 v_receipt jsonb; previous jsonb;
begin
 if p_repair_id is null or p_apply is null then raise exception 'invalid settlement' using errcode='PT400'; end if;
 select * into j from public.factory_repair_jobs where id=p_repair_id;
 if not found then return jsonb_build_object('status','not_eligible','reason','repair_not_found'); end if;
 -- Lock the same project/control rows as the recovery admission RPC, then
 -- reread all identities; no concurrent restart may cross this transaction.
 select * into p from public.factory_projects where id=j.project_id and is_active for update;
 if not found then return jsonb_build_object('status','not_eligible','reason','project_not_active'); end if;
 select * into v_ctl from public.factory_project_execution_controls where project_id=p.id for update;
 select * into j from public.factory_repair_jobs where id=p_repair_id and project_id=p.id for update;
 select payload into previous from public.factory_audit_events a where a.project_id=p.id
    and a.task_id=j.task_id and a.event_type='task.terminal_repair_superseded'
    and a.payload->>'repair_id'=j.id::text order by a.id desc limit 1;
 if found then return jsonb_build_object('status','already_settled','receipt',previous); end if;
 select * into c from public.factory_change_sets where id=j.change_set_id and project_id=p.id for update;
 select * into root from public.factory_runs where id=j.source_run_id for update;
 select * into t from public.factory_tasks where id=j.task_id and project_id=p.id for update;
 select * into u from public.factory_change_set_work_units where id=j.work_unit_id for update;
 select * into old_run from public.factory_runs where id=u.run_id for update;
 if v_ctl.state is distinct from 'running' or not public.factory_control_quiescent(p.id)
    or j.status is distinct from 'blocked' or j.source_role is distinct from 'security'
    or j.finding->>'kind' is distinct from 'database_security'
    or j.finding->>'code' is distinct from 'permissive_public_grant'
    or j.finding->>'path' is null or j.finding->>'path' !~ '^supabase/migrations/[A-Za-z0-9_-]+\.sql
    or c.status is distinct from 'completed' or c.release_run_id is distinct from root.id
    or c.lease_owner is not null or c.lease_expires_at is not null
    or c.candidate_commit is null or c.candidate_commit !~ '^[a-f0-9]{40}
    or j.candidate_commit is null or j.candidate_commit !~ '^[a-f0-9]{40}
    or c.candidate_commit=j.candidate_commit
    or root.task_id is distinct from c.root_task_id or root.status is distinct from 'merged'
    or root.lease_owner is not null or root.lease_expires_at is not null
    or root.metadata->>'execution_generation' is distinct from v_ctl.generation::text
    or root.candidate_commit is null or root.candidate_commit !~ '^[a-f0-9]{40}
    or not exists(select 1 from public.factory_tasks rt where rt.id=c.root_task_id
                 and rt.project_id=p.id and rt.status in ('completed','integrated'))
    or t.id is null or t.status is distinct from 'blocked' or t.parent_task_id is distinct from c.root_task_id
    or u.id is null or u.change_set_id is distinct from c.id or u.task_id is distinct from t.id
    or u.status is distinct from 'blocked' or u.output_commit is not null
    or old_run.task_id is distinct from t.id or old_run.status is distinct from 'blocked'
    or old_run.metadata->>'change_set_id' is distinct from c.id::text
    or old_run.lease_owner is not null or old_run.lease_expires_at is not null
    or not exists(select 1 from public.factory_audit_events a
      where a.project_id=p.id and a.run_id=root.id and a.event_type='release.human_merge_observed'
       and a.payload->>'head_sha'=c.candidate_commit and a.payload->>'merge_sha'=root.candidate_commit
       and a.payload->>'pr' ~ '^[1-9][0-9]*)
 then return jsonb_build_object('status','not_eligible','reason','terminal_delivery_lineage_not_verified'); end if;
 select * into s from public.factory_specialist_lane_jobs
 where project_id=p.id and run_id=root.id and role='security'
   and candidate_commit=c.candidate_commit and status='passed' for share;
 if not found or s.evidence->>'candidate_commit' is distinct from c.candidate_commit
    or s.evidence->>'_factory_epoch' is distinct from v_ctl.generation::text
    or s.evidence->>'blocking_findings' is distinct from '0'
    or s.evidence#>>'{coverage,sql_rls_rpc_invariants}' is distinct from 'true'
    or s.evidence->'unreviewable_paths' is distinct from '[]'::jsonb
    or jsonb_typeof(s.evidence->'database_lineage') is distinct from 'array'
    or not (s.evidence->'database_lineage' @> jsonb_build_array(jsonb_build_object('path',j.finding->>'path')))
 then return jsonb_build_object('status','not_eligible','reason','exact_security_recheck_not_verified'); end if;
 -- Retire only failed attempts explicitly related to this exact repair by
 -- the durable operator recovery record. An unrelated child blocks settlement.
 for child in select ct.id,ct.status,cr.id run_id,cr.status run_status,q.id request_id,q.status request_status,
                      cr.lease_owner,cr.lease_expires_at
   from public.factory_tasks ct
   left join public.factory_blocked_work_recovery_requests q
     on q.project_id=p.id and q.repair_job_id=j.id and q.source_task_id=t.id
     and q.source_run_id=old_run.id and q.continuation_task_id=ct.id
   left join public.factory_runs cr on cr.id=q.continuation_run_id and cr.task_id=ct.id
   where ct.parent_task_id=t.id for update of ct
 loop
   if child.status not in ('failed','blocked','cancelled') or child.request_id is null
      or child.request_status is distinct from 'blocked'
      or child.run_status not in ('failed','blocked','cancelled') or child.run_id is null
      or child.lease_owner is not null or child.lease_expires_at is not null
      or exists(select 1 from public.factory_tasks d where d.parent_task_id=child.id)
   then return jsonb_build_object('status','not_eligible','reason','recovery_descendant_not_terminal'); end if;
   if child.status<>'cancelled' then v_children:=array_append(v_children,child.id); end if;
 end loop;
 v_tasks:=array_prepend(t.id,v_children);
 if exists(select 1 from public.factory_blocked_work_recovery_requests q where q.project_id=p.id
       and q.repair_job_id=j.id and q.status<>'blocked')
    or exists(select 1 from public.factory_runs r where r.task_id=any(v_tasks)
       and (r.status not in ('failed','blocked','cancelled') or r.lease_owner is not null or r.lease_expires_at is not null))
    or exists(select 1 from public.factory_human_gates g join public.factory_runs r on r.id=g.run_id
       where r.task_id=any(v_tasks) and g.status='pending')
    or exists(select 1 from public.factory_change_sets k where k.root_task_id=any(v_tasks)
       and k.status not in ('completed','superseded'))
 then return jsonb_build_object('status','not_eligible','reason','unfinished_recovery_work'); end if;
 v_receipt:=jsonb_build_object('status',case when p_apply then 'settled' else 'eligible' end,
   'project_id',p.id,'repair_id',j.id,'old_candidate',j.candidate_commit,
   'verified_candidate',c.candidate_commit,'observed_merge_sha',root.candidate_commit,
   'specialist_job_id',s.id,'source_run_id',root.id,'blocked_run_id',old_run.id,
   'task_ids',to_jsonb(v_tasks),'reason','superseded_by_verified_human_merged_security_repair',
   'historical_runs_preserved',true,'production_release_authorized',false);
 if not p_apply then return v_receipt; end if;
 for child in select id,status from public.factory_tasks where id=any(v_tasks) order by id for update loop
   old_status:=child.status;
   update public.factory_tasks set status='cancelled',updated_at=now()
     where id=child.id and project_id=p.id and status=old_status and status in ('failed','blocked');
   if not found then raise exception 'terminal repair task CAS lost' using errcode='PT409'; end if;
   insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
   values(p.id,child.id,root.id,'system','terminal-security-repair-reconciliation',
     'task.terminal_repair_superseded',v_receipt||jsonb_build_object('previous_status',old_status,'task_status','cancelled'));
 end loop;
 return v_receipt;
end $fn$;

create or replace function public.factory_settle_terminal_security_repairs_v1(
 p_limit integer default 8,p_apply boolean default false
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare item record; receipts jsonb:='[]'; receipt jsonb; settled integer:=0; eligible integer:=0;
begin
 if p_limit is null or p_limit not between 1 and 20 or p_apply is null
 then raise exception 'invalid bounded settlement' using errcode='PT400'; end if;
 for item in select j.id from public.factory_repair_jobs j
   join public.factory_tasks t on t.id=j.task_id and t.project_id=j.project_id
   join public.factory_change_sets c on c.id=j.change_set_id and c.project_id=j.project_id
   where j.status='blocked' and j.source_role='security' and t.status='blocked'
     and j.finding->>'code'='permissive_public_grant' and c.status='completed'
     and c.candidate_commit<>j.candidate_commit
   order by j.updated_at,j.id limit p_limit
 loop
   receipt:=public.factory_settle_terminal_security_repair_v1(item.id,p_apply);
   if receipt->>'status'='settled' then settled:=settled+1; end if;
   if receipt->>'status'='eligible' then eligible:=eligible+1; end if;
   receipts:=receipts||jsonb_build_array(receipt);
 end loop;
 return jsonb_build_object('status','ok','applied',p_apply,'eligible',eligible,'settled',settled,'receipts',receipts);
end $fn$;

-- Recovery eligibility is observed, not inferred from registration or an
-- arbitrary failed run. Repeated attempts with unchanged evidence are refused.
create or replace function public.factory_blocked_recovery_eligibility_v2(p_project_id uuid)
returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare j public.factory_repair_jobs%rowtype; t public.factory_tasks%rowtype;
 c public.factory_project_execution_controls%rowtype;
begin
 select * into c from public.factory_project_execution_controls where project_id=p_project_id;
 if c.state is distinct from 'running' or not exists(select 1 from public.factory_projects p
       where p.id=p_project_id and p.is_active)
 then return jsonb_build_object('status','not_eligible','reason','project_not_running'); end if;
 if not public.factory_control_quiescent(p_project_id) or exists(
    select 1 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
      where t.project_id=p_project_id and r.status in ('created','queued','running','implementing'))
 then return jsonb_build_object('status','not_eligible','reason','work_in_progress'); end if;
 select * into j from public.factory_repair_jobs where project_id=p_project_id and status='blocked'
     and cycle<max_cycles order by updated_at desc,id desc limit 1;
 if not found then return jsonb_build_object('status','not_eligible','reason','no_resumable_repair'); end if;
 select * into t from public.factory_tasks where id=j.task_id and project_id=p_project_id;
 if t.status is distinct from 'blocked' then return jsonb_build_object('status','not_eligible','reason','historical_repair'); end if;
 if exists(select 1 from public.factory_blocked_work_recovery_requests q where q.repair_job_id=j.id
      and q.project_id=p_project_id and q.status in ('accepted','queued','claimed','recovering'))
 then return jsonb_build_object('status','not_eligible','reason','recovery_in_progress'); end if;
 if exists(select 1 from public.factory_blocked_work_recovery_requests q where q.repair_job_id=j.id
      and q.project_id=p_project_id and q.status in ('blocked','completed') and q.updated_at>=j.updated_at)
 then return jsonb_build_object('status','not_eligible','reason','previous_recovery_requires_new_evidence'); end if;
 if not exists(select 1 from public.factory_change_sets cs join public.factory_runs sr on sr.id=j.source_run_id
      join public.factory_tasks st on st.id=sr.task_id
      join public.factory_runs br on br.task_id=t.id
      where cs.id=j.change_set_id and cs.project_id=p_project_id and cs.status='completed'
      and cs.root_task_id=st.id and st.project_id=p_project_id
      and sr.status in ('merged','integrated','completed')
      and cs.lease_owner is null and cs.lease_expires_at is null
      and br.status='blocked' and br.lease_owner is null and br.lease_expires_at is null
      and br.metadata->>'change_set_id'=cs.id::text)
 then return jsonb_build_object('status','not_eligible','reason','repair_lineage_unverified'); end if;
 if public.factory_settle_terminal_security_repair_v1(j.id,false)->>'status' in ('eligible','already_settled')
 then return jsonb_build_object('status','not_eligible','reason','repair_superseded_by_verified_delivery'); end if;
 return jsonb_build_object('status','eligible','repair_id',j.id,'cycle',j.cycle,'max_cycles',j.max_cycles);
end $fn$;

-- Serialize independent commands on the existing project row. A replay uses
-- the original V1 idempotency receipt; a new command rechecks eligibility.
create or replace function public.factory_restart_blocked_work_v2(
 p_project_key text,p_command_id uuid,p_expected_version bigint,p_actor_id uuid
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare p public.factory_projects%rowtype; c public.factory_project_execution_controls%rowtype;
 eligibility jsonb;
begin
 if p_command_id is null or p_actor_id is null or p_expected_version is null
    or not exists(select 1 from public.factory_console_operators op where op.user_id=p_actor_id
                  and op.is_active and op.role in ('admin','operator'))
 then raise exception 'unauthorized recovery actor' using errcode='PT403'; end if;
 select * into p from public.factory_projects where project_key=p_project_key and is_active for update;
 if not found then raise exception 'project not found' using errcode='PT404'; end if;
 if exists(select 1 from public.factory_blocked_work_recovery_requests q
     where q.project_id=p.id and q.command_id=p_command_id)
 then return public.factory_restart_blocked_work_v1(p_project_key,p_command_id,p_expected_version,p_actor_id); end if;
 select * into c from public.factory_project_execution_controls where project_id=p.id for update;
 if c.state is distinct from 'running' or c.version is distinct from p_expected_version
 then raise exception 'project control changed' using errcode='PT409'; end if;
 eligibility:=public.factory_blocked_recovery_eligibility_v2(p.id);
 if eligibility->>'status' is distinct from 'eligible'
 then raise exception 'recovery not eligible: %',eligibility->>'reason' using errcode='PT409'; end if;
 return public.factory_restart_blocked_work_v1(p_project_key,p_command_id,p_expected_version,p_actor_id);
end $fn$;
revoke all on function public.factory_settle_terminal_security_repair_v1(uuid,boolean) from public,anon,authenticated;
grant execute on function public.factory_settle_terminal_security_repair_v1(uuid,boolean) to service_role;
revoke all on function public.factory_settle_terminal_security_repairs_v1(integer,boolean) from public,anon,authenticated;
grant execute on function public.factory_settle_terminal_security_repairs_v1(integer,boolean) to service_role;
revoke all on function public.factory_blocked_recovery_eligibility_v2(uuid) from public,anon,authenticated;
grant execute on function public.factory_blocked_recovery_eligibility_v2(uuid) to service_role;
revoke all on function public.factory_restart_blocked_work_v2(text,uuid,bigint,uuid) from public,anon,authenticated;
grant execute on function public.factory_restart_blocked_work_v2(text,uuid,bigint,uuid) to service_role;
commit;
