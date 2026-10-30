-- Journey Delivery Binding v2. Candidate only: this migration is intentionally
-- additive and is NOT applied by this repository.  It never backfills history.
begin;

create table if not exists public.factory_journeys (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.factory_projects(id) on delete restrict,
  request_id uuid not null,
  request_source text not null check (request_source in ('github-owner','factory-console')),
  auth_actor_ref text not null,
  auth_event_id text not null,
  request_digest text not null check (request_digest ~ '^[0-9a-f]{64}$'),
  request_snapshot jsonb not null default '{}'::jsonb,
  issue_repository text,
  issue_number integer check (issue_number is null or issue_number > 0),
  state text not null check (state in ('intake_accepted','awaiting_source','source_bound','executing','preview_verified','awaiting_release','released_observed','closed')),
  execution_generation bigint,
  project_policy_version integer,
  policy_digest text,
  binding jsonb not null default '{}'::jsonb,
  binding_version integer not null default 2 check (binding_version=2),
  source_commit text,
  work_unit_output_commit text,
  candidate_commit text,
  preview_merge_sha text,
  production_release_sha text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(project_id,request_id),
  check (request_snapshot ? 'text' and request_snapshot->>'digest'=request_digest),
  check ((state in ('intake_accepted','awaiting_source')) or (
    execution_generation is not null and project_policy_version is not null
    and policy_digest ~ '^[0-9a-f]{64}$' and source_commit ~ '^[0-9a-f]{40}$'
    and binding->>'journey_id'=id::text and binding->>'source_commit'=source_commit
  ))
);
alter table public.factory_journeys enable row level security;
revoke all on table public.factory_journeys from public,anon,authenticated;
grant all on table public.factory_journeys to service_role;

alter table public.factory_tasks add column if not exists journey_id uuid references public.factory_journeys(id) on delete restrict;
alter table public.factory_runs add column if not exists journey_id uuid references public.factory_journeys(id) on delete restrict;
alter table public.factory_change_sets add column if not exists journey_id uuid references public.factory_journeys(id) on delete restrict;
create index if not exists idx_factory_journeys_project_state on public.factory_journeys(project_id,state,created_at);
create index if not exists idx_factory_runs_journey on public.factory_runs(journey_id) where journey_id is not null;
create index if not exists idx_factory_change_sets_journey on public.factory_change_sets(journey_id) where journey_id is not null;
-- Evidence is written by the authenticated resolver after its exact GitHub
-- GET and consumed under lock by bind. A client supplied binding digest alone
-- is intentionally not an authorization proof.
create table if not exists public.factory_journey_source_evidence_v2 (
  journey_id uuid primary key references public.factory_journeys(id) on delete restrict,
  repository text not null, source_ref text not null, source_commit text not null check (source_commit ~ '^[0-9a-f]{40}$'),
  policy_digest text not null check (policy_digest ~ '^[0-9a-f]{64}$'), proof_digest text not null check (proof_digest ~ '^[0-9a-f]{64}$'),
  observed_generation bigint not null, observed_at timestamptz not null default now()
);
alter table public.factory_journey_source_evidence_v2 enable row level security;
revoke all on table public.factory_journey_source_evidence_v2 from public,anon,authenticated;
grant all on table public.factory_journey_source_evidence_v2 to service_role;

-- Propagation is structural, not an optional convention in downstream
-- workers. Legacy rows remain NULL; a V2 descendant cannot silently lose or
-- exchange its capability while materializing tasks, runs or Change Sets.
create or replace function public.factory_propagate_journey_binding_v2()
returns trigger language plpgsql security invoker set search_path='' as $fn$
declare inherited_journey uuid;
begin
 if tg_table_name='factory_tasks' and nullif(to_jsonb(new)->>'parent_task_id','') is not null then
   select journey_id into inherited_journey from public.factory_tasks where id=(to_jsonb(new)->>'parent_task_id')::uuid;
 elsif tg_table_name='factory_runs' then
   select journey_id into inherited_journey from public.factory_tasks where id=(to_jsonb(new)->>'task_id')::uuid;
 elsif tg_table_name='factory_change_sets' then
   select journey_id into inherited_journey from public.factory_tasks where id=(to_jsonb(new)->>'root_task_id')::uuid;
 end if;
 if inherited_journey is not null then
   if new.journey_id is null then new.journey_id:=inherited_journey;
   elsif new.journey_id is distinct from inherited_journey then raise exception 'journey binding cannot cross descendants' using errcode='PT409'; end if;
 end if;
 if new.journey_id is not null and not exists(
   select 1 from public.factory_journeys j where j.id=new.journey_id
    and j.state in ('source_bound','executing','preview_verified','awaiting_release')
 ) then raise exception 'journey binding is not executable' using errcode='PT409'; end if;
 return new;
end $fn$;
drop trigger if exists factory_propagate_journey_task_v2 on public.factory_tasks;
create trigger factory_propagate_journey_task_v2 before insert or update of parent_task_id,journey_id on public.factory_tasks for each row execute function public.factory_propagate_journey_binding_v2();
drop trigger if exists factory_propagate_journey_run_v2 on public.factory_runs;
create trigger factory_propagate_journey_run_v2 before insert or update of task_id,journey_id on public.factory_runs for each row execute function public.factory_propagate_journey_binding_v2();
drop trigger if exists factory_propagate_journey_change_set_v2 on public.factory_change_sets;
create trigger factory_propagate_journey_change_set_v2 before insert or update of root_task_id,journey_id on public.factory_change_sets for each row execute function public.factory_propagate_journey_binding_v2();

create or replace function public.factory_enqueue_journey_intake_v2(
 p_project_key text,p_request text,p_request_id uuid,p_request_source text,
 p_auth_actor_ref text,p_auth_event_id text,p_request_digest text,
 p_issue_repository text default null,p_issue_number integer default null
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare p public.factory_projects%rowtype; c public.factory_project_execution_controls%rowtype;
 j public.factory_journeys%rowtype; request_text text:=btrim(p_request);
begin
 if p_request_id is null or request_text is null or length(request_text) not between 1 and 6000
    or p_request_source not in ('github-owner','factory-console') or nullif(btrim(p_auth_actor_ref),'') is null
    or nullif(btrim(p_auth_event_id),'') is null or p_request_digest !~ '^[0-9a-f]{64}$'
 then raise exception 'invalid journey intake' using errcode='PT400'; end if;
 if p_request_digest is distinct from encode(extensions.digest(convert_to(request_text,'UTF8'),'sha256'),'hex')
 then raise exception 'journey request digest mismatch' using errcode='PT400'; end if;
 if p_request_source='github-owner' and (p_issue_repository is distinct from 'leandrosilveiradepaula/ai-product-factory'
    or p_issue_number is distinct from 1055 or p_auth_actor_ref is distinct from 'github-owner'
    or p_auth_event_id !~ '^[1-9][0-9]*$')
 then raise exception 'invalid github owner provenance' using errcode='PT403'; end if;
 select * into p from public.factory_projects where project_key=btrim(p_project_key) and is_active=true for update;
 if p.id is null then raise exception 'active project not found' using errcode='PT404'; end if;
 select * into c from public.factory_project_execution_controls where project_id=p.id for share;
 if c.state is distinct from 'running' or c.generation is null or c.generation<1 then raise exception 'project is not running' using errcode='PT409'; end if;
 if coalesce((p.manifest->'journey_delivery_binding_v2'->>'enabled')::boolean,false) is not true then
   raise exception 'journey delivery binding v2 is not enabled' using errcode='PT409'; end if;
 select * into j from public.factory_journeys where project_id=p.id and request_id=p_request_id for update;
 if j.id is not null then
   if j.request_digest is distinct from p_request_digest or j.request_source is distinct from p_request_source
      or j.auth_actor_ref is distinct from p_auth_actor_ref or j.auth_event_id is distinct from p_auth_event_id
      or j.issue_repository is distinct from p_issue_repository or j.issue_number is distinct from p_issue_number
   then raise exception 'journey request replay mismatch' using errcode='PT409'; end if;
   return jsonb_build_object('project_id',p.id,'journey_id',j.id,'request_id',p_request_id,'created',false,'state',j.state,'source',p_request_source);
 end if;
 insert into public.factory_journeys(project_id,request_id,request_source,auth_actor_ref,auth_event_id,request_digest,request_snapshot,issue_repository,issue_number,state)
 values(p.id,p_request_id,p_request_source,p_auth_actor_ref,p_auth_event_id,p_request_digest,
   jsonb_build_object('text',request_text,'digest',p_request_digest,'source',p_request_source,
     'control_issue_repository',p_issue_repository,'control_issue_number',p_issue_number,
     'authorization_event_id',p_auth_event_id),p_issue_repository,p_issue_number,'awaiting_source') returning * into j;
 insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
 values(p.id,'human',p_auth_actor_ref,'journey.intake_accepted',jsonb_build_object('journey_id',j.id,'request_id',p_request_id,'source',p_request_source,'state',j.state));
 return jsonb_build_object('project_id',p.id,'journey_id',j.id,'request_id',p_request_id,'created',true,'state',j.state,'source',p_request_source);
end $fn$;

create or replace function public.factory_bind_journey_source_v2(
 p_project_key text,p_request_id uuid,p_expected_generation bigint,p_expected_policy_version integer,p_binding jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare p public.factory_projects%rowtype; c public.factory_project_execution_controls%rowtype; j public.factory_journeys%rowtype; evidence public.factory_journey_source_evidence_v2%rowtype;
 task_id uuid; run_id uuid; policy jsonb; v_policy_digest text; binding_digest text; stages jsonb;
begin
 select * into p from public.factory_projects where project_key=btrim(p_project_key) and is_active=true for update;
 if p.id is null then raise exception 'active project not found' using errcode='PT404'; end if;
 select * into c from public.factory_project_execution_controls where project_id=p.id for update;
 select * into j from public.factory_journeys where project_id=p.id and request_id=p_request_id for update;
 if j.id is null or j.state not in ('intake_accepted','awaiting_source') then raise exception 'journey is not source-bindable' using errcode='PT409'; end if;
 policy:=p.manifest->'journey_delivery_binding_v2';
 if c.state is distinct from 'running' or c.generation is distinct from p_expected_generation or p_expected_generation<1
    or coalesce((policy->>'enabled')::boolean,false) is not true or (policy->>'version')::integer is distinct from p_expected_policy_version
 then raise exception 'journey source binding epoch or policy changed' using errcode='PT409'; end if;
 v_policy_digest:=policy->>'digest'; binding_digest:=encode(extensions.digest(p_binding::text,'sha256'),'hex');
 if v_policy_digest !~ '^[0-9a-f]{64}$' or p_binding is null or p_binding->>'journey_id' is null
    or p_binding->>'execution_generation' is null or p_binding->>'execution_generation' !~ '^[1-9][0-9]*$'
    or (p_binding->>'execution_generation')::bigint is distinct from c.generation
    or p_binding->>'policy_version' is null or p_binding->>'policy_version' !~ '^[1-9][0-9]*$'
    or (p_binding->>'policy_version')::integer is distinct from p_expected_policy_version
    or p_binding->>'source_ref' is null
    or p_binding->>'integration_branch' is null or p_binding->>'preview_branch_prefix' is null
    or p_binding->>'preview_base_ref' is null or p_binding->>'release_base_ref' is null
    or p_binding->>'journey_id' is distinct from j.id::text
    or p_binding->>'project_id' is distinct from p.id::text or p_binding->>'request_id' is distinct from p_request_id::text
    or p_binding->>'repository' is distinct from p.repository or p_binding->>'source_repository' is distinct from p.repository
    or p_binding->>'source_commit' !~ '^[0-9a-f]{40}$' or p_binding->>'source_proof_digest' !~ '^[0-9a-f]{64}$'
    or p_binding->>'source_mode' not in ('main_snapshot','authorized_preview','greenfield_bootstrap')
    or p_binding->>'source_mode' is distinct from policy->>'source_mode'
    or (p_binding->>'source_mode'='main_snapshot' and p_binding->>'source_ref' is distinct from 'main')
    or p_binding->>'integration_branch' !~ ('^factory/journey-'||j.id::text||'([/-].*)?$')
    or p_binding->>'preview_branch_prefix' !~ '^preview/journey-[a-z0-9_-]+$'
    or p_binding->>'preview_base_ref' is distinct from policy->>'preview_base_ref'
    or p_binding->>'release_base_ref' is distinct from policy->>'release_base_ref'
    or p_binding->>'policy_digest' is distinct from v_policy_digest or p_binding->>'binding_version' is distinct from '2'
 then raise exception 'invalid journey source binding' using errcode='PT400'; end if;
 select * into evidence from public.factory_journey_source_evidence_v2 where journey_id=j.id for update;
 if evidence.journey_id is null or evidence.repository is distinct from p.repository
    or evidence.source_ref is distinct from p_binding->>'source_ref'
    or evidence.source_commit is distinct from p_binding->>'source_commit'
    or evidence.policy_digest is distinct from v_policy_digest
    or evidence.proof_digest is distinct from p_binding->>'source_proof_digest'
    or evidence.observed_generation is distinct from c.generation
 then raise exception 'journey source evidence unavailable or inconsistent' using errcode='PT409'; end if;
 if exists(select 1 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
   where t.project_id=p.id and r.status in ('created','queued','running') and r.journey_id is distinct from j.id)
 then raise exception 'project already has an active incompatible run' using errcode='PT409'; end if;
 if exists(select 1 from public.factory_tasks t where t.project_id=p.id and t.journey_id=j.id) then raise exception 'journey already has work' using errcode='PT409'; end if;
 stages:=case when p.project_kind='greenfield' then jsonb_build_array('discovery','specification','planning') else jsonb_build_array('reconciliation','gap_analysis','planning') end;
 update public.factory_journeys set state='source_bound',execution_generation=c.generation,project_policy_version=p_expected_policy_version,policy_digest=v_policy_digest,binding=p_binding,source_commit=p_binding->>'source_commit',updated_at=now() where id=j.id;
 insert into public.factory_tasks(project_id,journey_id,external_key,title,description,status,complexity,risk,acceptance_criteria,depends_on)
 values(p.id,j.id,'journey-v2-'||j.id::text,'Execute authorized journey request',
   'Immutable authorized request: '||(j.request_snapshot->>'text'),'queued','medium','{}',
   jsonb_build_array('bound source','bound destinations','request_id='||p_request_id::text,'request_digest='||j.request_digest),'[]') returning id into task_id;
 insert into public.factory_runs(task_id,journey_id,status,execution_route,source_commit,branch_name,metadata)
 values(task_id,j.id,'created','direct',p_binding->>'source_commit',p_binding->>'integration_branch',jsonb_build_object('stages',stages,'journey_binding_v2',p_binding,'journey_request',j.request_snapshot,'execution_generation',c.generation,'continuation_request_id',p_request_id::text)) returning id into run_id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(p.id,task_id,run_id,'system','journey-binder','journey.source_bound',jsonb_build_object('journey_id',j.id,'request_id',p_request_id,'binding_digest',binding_digest,'source_commit',p_binding->>'source_commit','preview_base_ref',p_binding->>'preview_base_ref'));
 return jsonb_build_object('journey_id',j.id,'task_id',task_id,'run_id',run_id,'state','source_bound','created',true);
end $fn$;

create or replace function public.factory_record_journey_source_evidence_v2(
 p_journey_id uuid,p_repository text,p_source_ref text,p_source_commit text,p_policy_digest text,p_proof_digest text,p_generation bigint
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare j public.factory_journeys%rowtype; p public.factory_projects%rowtype; c public.factory_project_execution_controls%rowtype;
begin
 select * into j from public.factory_journeys where id=p_journey_id for update;
 if j.id is null or j.state not in ('intake_accepted','awaiting_source') then raise exception 'journey is not awaiting source' using errcode='PT409'; end if;
 select * into p from public.factory_projects where id=j.project_id and is_active=true;
 select * into c from public.factory_project_execution_controls where project_id=j.project_id for share;
 if p.id is null or c.state is distinct from 'running' or c.generation is distinct from p_generation
    or p.repository is distinct from p_repository or p_source_ref <> 'main' or p_source_commit !~ '^[0-9a-f]{40}$'
    or p_policy_digest !~ '^[0-9a-f]{64}$' or p_proof_digest !~ '^[0-9a-f]{64}$'
 then raise exception 'invalid journey source evidence' using errcode='PT400'; end if;
 insert into public.factory_journey_source_evidence_v2(journey_id,repository,source_ref,source_commit,policy_digest,proof_digest,observed_generation)
 values(p_journey_id,p_repository,p_source_ref,p_source_commit,p_policy_digest,p_proof_digest,p_generation)
 on conflict (journey_id) do update set repository=excluded.repository,source_ref=excluded.source_ref,source_commit=excluded.source_commit,policy_digest=excluded.policy_digest,proof_digest=excluded.proof_digest,observed_generation=excluded.observed_generation,observed_at=now();
 return jsonb_build_object('journey_id',j.id,'recorded',true);
end $fn$;


-- Event-driven, idempotent settlement: only durable, same-journey facts can
-- advance a V2 journey. The observer never merges GitHub branches.
create or replace function public.factory_reconcile_journey_v2(p_run_id uuid)
returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare
  v_run public.factory_runs%rowtype;
  v_task public.factory_tasks%rowtype;
  j public.factory_journeys%rowtype;
  c public.factory_change_sets%rowtype;
  rr public.factory_runs%rowtype;
  v_control_state text;
  v_control_generation bigint;
  v_candidate text;
  v_pr text;
  v_preview_url text;
  v_preview_merge text;
  v_not_required boolean := false;
  v_verified boolean := false;
  v_release_ready boolean := false;
  v_merge text;
  v_release_candidate text;
  v_release_status text;
begin
  select * into v_run from public.factory_runs where id=p_run_id;
  if v_run.id is null or v_run.journey_id is null then
    return jsonb_build_object('status','legacy_not_applicable');
  end if;
  select * into j from public.factory_journeys where id=v_run.journey_id for update;
  select * into v_task from public.factory_tasks where id=v_run.task_id;
  if j.id is null or v_task.id is null or v_task.project_id is distinct from j.project_id
     or v_task.journey_id is distinct from j.id
     or v_run.metadata->>'execution_generation' is distinct from j.execution_generation::text
     or j.binding->>'journey_id' is distinct from j.id::text
     or j.binding->>'request_id' is distinct from j.request_id::text
     or j.binding->>'project_id' is distinct from j.project_id::text
     or j.binding->>'source_commit' is distinct from j.source_commit
     or j.binding->>'policy_digest' is distinct from j.policy_digest
  then raise exception 'journey reconciliation identity mismatch' using errcode='PT409'; end if;
  if j.state='closed' then
    return jsonb_build_object('journey_id',j.id,'state',j.state,
      'preview_merge_sha',j.preview_merge_sha,'production_release_sha',j.production_release_sha);
  end if;
  if j.state in ('intake_accepted','awaiting_source') then
    raise exception 'journey reconciliation state is not executable' using errcode='PT409';
  end if;
  select state,generation into v_control_state,v_control_generation
    from public.factory_project_execution_controls where project_id=j.project_id;
  -- Pause/stop/epoch rotation freezes advancement, but an independently
  -- observed human merge can still be recorded after it actually occurred.
  if v_control_state='running' and v_control_generation=j.execution_generation then
    if j.state='source_bound' and exists(
      select 1 from public.factory_runs r
      where r.journey_id=j.id
        and r.metadata->>'execution_generation'=j.execution_generation::text
        and r.status in ('running','completed','preview_ready','awaiting_release','integrated','merged')
    ) then
      update public.factory_journeys set state='executing',updated_at=now() where id=j.id;
      insert into public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
      values(j.project_id,p_run_id,'system','journey-v2-reconciler','journey.executing',
        jsonb_build_object('journey_id',j.id,'request_id',j.request_id,'generation',j.execution_generation));
      j.state:='executing';
    end if;

    select cs.* into c from public.factory_change_sets cs
    join public.factory_runs release_run on release_run.id=cs.release_run_id
    where cs.journey_id=j.id and cs.project_id=j.project_id
      and release_run.journey_id=j.id and release_run.task_id=cs.root_task_id
      and release_run.metadata->>'execution_generation'=j.execution_generation::text
      and cs.source_commit=j.source_commit
      and cs.integration_branch=j.binding->>'integration_branch'
      and release_run.branch_name=cs.integration_branch
      and cs.candidate_commit=release_run.candidate_commit
      and cs.candidate_commit ~ '^[0-9a-f]{40}$'
      and cs.metadata->'integration_release_request'->>'candidate_commit'=cs.candidate_commit
      and cs.metadata->'integration_release_request'->>'branch'=cs.integration_branch
    order by cs.updated_at desc,cs.id desc limit 1;
    if c.id is not null then
      select * into rr from public.factory_runs where id=c.release_run_id;
      v_candidate:=c.candidate_commit;
      v_pr:=c.metadata->'integration_release_request'->>'pr_number';
      if v_pr ~ '^[1-9][0-9]*$'
         and exists(select 1 from public.factory_evaluations e
           where e.run_id=rr.id and e.eval_type='github_ci'
             and e.status='success' and e.baseline_ref=v_candidate)
         and exists(select 1 from public.factory_evaluations e
           where e.run_id=rr.id and e.eval_type='quality_gate'
             and e.status='success' and e.baseline_ref=v_candidate
             and e.result->>'passed'='true')
      then
        -- A V2 Preview must have used the journey-specific promotion branch,
        -- plus the exact candidate deployment and browser-e2e receipts.
        select d.metadata->>'preview_url' into v_preview_url
        from public.factory_deployments d
        where d.run_id=rr.id and d.environment='preview' and d.status='success'
          and d.metadata->>'candidate_commit'=v_candidate
          and nullif(d.metadata->>'preview_url','') is not null
          and exists(select 1 from public.factory_evaluations e
            where e.run_id=rr.id and e.eval_type='browser_e2e'
              and e.status='success' and e.baseline_ref=d.metadata->>'preview_url')
          and exists(select 1 from public.factory_audit_events a
            where a.run_id=rr.id and a.event_type='preview.promotion_completed'
              and a.payload->>'candidate_commit'=v_candidate
              and a.payload->>'branch'=(j.binding->>'preview_branch_prefix'||'-'||c.id::text)
              and a.payload->>'pr_number'=v_pr)
        order by d.created_at desc limit 1;
        v_not_required:=exists(
          select 1 from public.factory_tool_usage u
          where u.run_id=rr.id and u.operation='preview_not_required_awaiting_human_merge'
            and u.metadata->>'head_sha'=v_candidate and u.metadata->>'pr'=v_pr
        ) and exists(
          select 1 from public.factory_audit_events a
          where a.run_id=rr.id and a.event_type='release.preview_not_required'
            and a.payload->>'head_sha'=v_candidate and a.payload->>'pr'=v_pr
        );
        v_verified:=v_preview_url is not null or v_not_required;
        if v_verified and j.state in ('executing','preview_verified','awaiting_release') then
          if j.candidate_commit is not null and j.candidate_commit is distinct from v_candidate then
            raise exception 'journey candidate changed after verified Preview' using errcode='PT409';
          end if;
          if j.state='executing' then
            update public.factory_journeys set state='preview_verified',
              candidate_commit=v_candidate,updated_at=now() where id=j.id;
            insert into public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
            values(j.project_id,rr.id,'system','journey-v2-reconciler','journey.preview_verified',
              jsonb_build_object('journey_id',j.id,'candidate_commit',v_candidate,
                'preview_disposition',case when v_not_required then 'not_applicable' else 'browser_verified' end,
                'preview_url',v_preview_url,'pr_number',v_pr::bigint));
            j.state:='preview_verified';
            j.candidate_commit:=v_candidate;
          end if;
          v_release_ready:=rr.status='awaiting_release'
            and j.binding->>'release_base_ref'='main'
            and (
              (j.binding->>'preview_base_ref'='main' and exists(
                select 1 from public.factory_release_reports report
                where report.run_id=rr.id and report.project_id=j.project_id
                  and report.status='ready_for_human_release'
                  and report.candidate_commit=v_candidate
                  and report.report->'blockers'='[]'::jsonb
              ))
              or
              -- A Preview-only candidate has a production-blocked report.
              -- This *exact* production-specific blocker permits only the
              -- human nonproduction merge gate; it never releases main.
              (j.binding->>'preview_base_ref' like 'preview/%' and exists(
                select 1 from public.factory_release_reports report
                where report.run_id=rr.id and report.project_id=j.project_id
                  and report.status='blocked'
                  and report.candidate_commit=v_candidate
                  and report.report->'blockers'=jsonb_build_array(
                    'production requires a separate verified main-target release candidate')
              ))
            )
            and (v_not_required or exists(
              select 1 from public.factory_tool_usage u
              where u.run_id=rr.id and u.operation='verified_preview_awaiting_human_merge'
                and u.metadata->>'head_sha'=v_candidate and u.metadata->>'pr'=v_pr
                and u.metadata->>'preview_url'=v_preview_url))
            and exists(select 1 from public.factory_audit_events a
              where a.run_id=rr.id and a.event_type in ('release.awaiting_human_merge','release.preview_not_required')
                and a.payload->>'head_sha'=v_candidate and a.payload->>'pr'=v_pr);
          if v_release_ready and j.state='preview_verified' then
            update public.factory_journeys set state='awaiting_release',updated_at=now() where id=j.id;
            insert into public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
            values(j.project_id,rr.id,'system','journey-v2-reconciler','journey.awaiting_release',
              jsonb_build_object('journey_id',j.id,'candidate_commit',v_candidate,
                'pr_number',v_pr::bigint,'automatic_merge',false,
                'gate_kind',case when j.binding->>'preview_base_ref'='main'
                  then 'production_main' else 'nonproduction_preview' end,
                'target_ref',j.binding->>'preview_base_ref',
                'production_release_eligible',(j.binding->>'preview_base_ref'='main')));
            j.state:='awaiting_release';
          end if;
        end if;
      end if;

    end if;
  end if;


  -- The separate nonproduction observer verifies a HUMAN Preview merge.
  -- This can settle while the project is paused; it never authorizes main.
  if j.state='awaiting_release'
     and j.binding->>'preview_base_ref' like 'preview/%' then
    select a.payload->>'merge_sha' into v_preview_merge
    from public.factory_audit_events a
    join public.factory_change_sets cs on cs.release_run_id=a.run_id
    where a.run_id is not null and cs.journey_id=j.id
      and cs.project_id=j.project_id and cs.candidate_commit=j.candidate_commit
      and cs.source_commit=j.source_commit
      and cs.integration_branch=j.binding->>'integration_branch'
      and a.event_type='change_set.nonproduction_merge.observed'
      and a.payload->>'candidate_commit'=cs.candidate_commit
      and a.payload->>'base_ref'=j.binding->>'preview_base_ref'
      and a.payload->>'head_ref'=j.binding->>'integration_branch'
      and a.payload->>'repository'=j.binding->>'repository'
      and a.payload->>'pr_number'=cs.metadata->'integration_release_request'->>'pr_number'
      and a.payload->>'merge_sha' ~ '^[0-9a-f]{40}$'
      and a.payload->>'environment'='preview'
      and a.payload->>'merged'='true'
      and a.payload->>'merge_is_ancestor'='true'
      and a.payload->>'vercel_state'='success'
      and a.payload->>'production_released'='false'
      and a.payload->>'evidence_source'='github_exact_pr_and_merge_commit_status'
    order by a.id desc limit 1;
    if v_preview_merge is not null then
      if j.preview_merge_sha is not null and j.preview_merge_sha is distinct from v_preview_merge then
        raise exception 'journey Preview merge receipt conflict' using errcode='PT409';
      end if;
      update public.factory_journeys set state='closed',
        preview_merge_sha=v_preview_merge,updated_at=now() where id=j.id;
      insert into public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
      values(j.project_id,p_run_id,'system','journey-v2-reconciler','journey.closed',
        jsonb_build_object('journey_id',j.id,'candidate_commit',j.candidate_commit,
          'preview_merge_sha',v_preview_merge,'closure_reason','observed_nonproduction_merge',
          'production_released',false,'automatic_merge',false));
      j.state:='closed'; j.preview_merge_sha:=v_preview_merge;
    end if;
  end if;

  -- Production remains a distinct main-target candidate and human gate.
  -- A Preview-only candidate never becomes released_observed.
  if j.state='awaiting_release' and j.binding->>'preview_base_ref'='main' then
    select report.status,report.candidate_commit,report.report->>'merge_sha'
      into v_release_status,v_release_candidate,v_merge
    from public.factory_release_reports report
    join public.factory_runs release_run on release_run.id=report.run_id
    where release_run.journey_id=j.id and report.project_id=j.project_id
      and report.status='released' and report.candidate_commit=j.candidate_commit
      and release_run.status='merged'
      and release_run.candidate_commit=report.report->>'merge_sha'
      and release_run.metadata->>'execution_generation'=j.execution_generation::text
    order by report.updated_at desc limit 1;
    if v_release_status='released' and v_merge ~ '^[0-9a-f]{40}$'
       and exists(select 1 from public.factory_audit_events a
         join public.factory_runs release_run on release_run.id=a.run_id
         where release_run.journey_id=j.id
           and a.event_type='release.human_merge_observed'
           and a.payload->>'merge_sha'=v_merge
           and coalesce(a.payload->>'candidate_commit',a.payload->>'head_sha')
               =j.candidate_commit)
    then
      if j.production_release_sha is not null and j.production_release_sha is distinct from v_merge then
        raise exception 'journey production release receipt conflict' using errcode='PT409';
      end if;
      update public.factory_journeys set state='released_observed',
        production_release_sha=v_merge,updated_at=now() where id=j.id;
      insert into public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
      values(j.project_id,p_run_id,'system','journey-v2-reconciler','journey.released_observed',
        jsonb_build_object('journey_id',j.id,'candidate_commit',j.candidate_commit,
          'merge_sha',v_merge,'automatic_merge',false));
      j.state:='released_observed';
    end if;
  end if;
  return jsonb_build_object('journey_id',j.id,'state',j.state,
    'candidate_commit',j.candidate_commit,'preview_merge_sha',j.preview_merge_sha,
    'production_release_sha',case when j.state='released_observed' then v_merge else j.production_release_sha end);
end $fn$;

create or replace function public.factory_reconcile_journey_trigger_v2()
returns trigger language plpgsql security invoker set search_path='' as $fn$
declare v_run_id uuid;
begin
  if tg_table_name='factory_runs' then v_run_id:=new.id;
  elsif tg_table_name='factory_change_sets' then v_run_id:=new.release_run_id;
  elsif tg_table_name='factory_audit_events' then
    if new.event_type not in ('preview.promotion_completed','preview.browser_evidence_recorded',
      'release.awaiting_human_merge','release.preview_not_required',
      'release.human_merge_observed','change_set.nonproduction_merge.observed') then
      return new;
    end if;
    v_run_id:=new.run_id;
  else v_run_id:=new.run_id;
  end if;
  if v_run_id is not null then perform public.factory_reconcile_journey_v2(v_run_id); end if;
  return new;
end $fn$;

create trigger factory_journey_run_settlement_v2 after update of status,candidate_commit
on public.factory_runs for each row execute function public.factory_reconcile_journey_trigger_v2();
create trigger factory_journey_change_set_settlement_v2 after insert or update of candidate_commit,release_run_id,metadata,status
on public.factory_change_sets for each row execute function public.factory_reconcile_journey_trigger_v2();
create trigger factory_journey_evaluation_settlement_v2 after insert
on public.factory_evaluations for each row execute function public.factory_reconcile_journey_trigger_v2();
create trigger factory_journey_deployment_settlement_v2 after insert or update of status
on public.factory_deployments for each row execute function public.factory_reconcile_journey_trigger_v2();
create trigger factory_journey_tool_usage_settlement_v2 after insert
on public.factory_tool_usage for each row execute function public.factory_reconcile_journey_trigger_v2();
create trigger factory_journey_release_report_settlement_v2 after insert or update of status,report
on public.factory_release_reports for each row execute function public.factory_reconcile_journey_trigger_v2();
create trigger factory_journey_audit_settlement_v2 after insert
on public.factory_audit_events for each row execute function public.factory_reconcile_journey_trigger_v2();


-- A persisted V2 run cannot be reinterpreted as V1 by removing policy.
-- Rollback disables new admission with enabled=false, retaining the object.
create or replace function public.factory_preserve_journey_policy_v2()
returns trigger language plpgsql security invoker set search_path='' as $fn$
begin
  if exists(select 1 from public.factory_journeys j where j.project_id=new.id)
     and jsonb_typeof(new.manifest->'journey_delivery_binding_v2') is distinct from 'object'
  then raise exception 'cannot remove V2 policy with persisted journeys' using errcode='PT409';
  end if;
  return new;
end $fn$;
create trigger factory_preserve_journey_policy_v2 before update of manifest
on public.factory_projects for each row execute function public.factory_preserve_journey_policy_v2();
revoke all on function public.factory_preserve_journey_policy_v2() from public,anon,authenticated;
grant execute on function public.factory_preserve_journey_policy_v2() to service_role;

revoke all on function public.factory_reconcile_journey_v2(uuid) from public,anon,authenticated;
grant execute on function public.factory_reconcile_journey_v2(uuid) to service_role;
revoke all on function public.factory_reconcile_journey_trigger_v2() from public,anon,authenticated;
grant execute on function public.factory_reconcile_journey_trigger_v2() to service_role;

revoke all on function public.factory_enqueue_journey_intake_v2(text,text,uuid,text,text,text,text,text,integer) from public,anon,authenticated;
grant execute on function public.factory_enqueue_journey_intake_v2(text,text,uuid,text,text,text,text,text,integer) to service_role;
revoke all on function public.factory_bind_journey_source_v2(text,uuid,bigint,integer,jsonb) from public,anon,authenticated;
grant execute on function public.factory_bind_journey_source_v2(text,uuid,bigint,integer,jsonb) to service_role;
revoke all on function public.factory_record_journey_source_evidence_v2(uuid,text,text,text,text,text,bigint) from public,anon,authenticated;
grant execute on function public.factory_record_journey_source_evidence_v2(uuid,text,text,text,text,text,bigint) to service_role;
commit;
