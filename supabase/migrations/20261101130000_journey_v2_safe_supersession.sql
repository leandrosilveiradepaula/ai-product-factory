-- Supersede one exhausted, unshipped Journey V2 and rotate the authorized
-- main_snapshot/Preview pair in ONE CAS transaction. Never rewrite its history.
-- This migration must be merged, PostgreSQL-QA verified, then explicitly
-- approved for installation. This script never invokes the transition itself.
begin;

alter table public.factory_journeys
  drop constraint if exists factory_journeys_state_check;
alter table public.factory_journeys
  add constraint factory_journeys_state_check check (
    state in ('intake_accepted','awaiting_source','source_bound','executing',
      'preview_verified','awaiting_release','released_observed','closed','superseded')
  );

create table if not exists public.factory_journey_supersessions_v2 (
  command_id uuid primary key,
  project_id uuid not null references public.factory_projects(id) on delete restrict,
  journey_id uuid not null unique references public.factory_journeys(id) on delete restrict,
  actor_user_id uuid not null,
  expected_generation bigint not null,
  expected_version bigint not null,
  prior_source_commit text not null,
  new_preview_ref text not null,
  verified_main_sha text not null,
  verified_preview_sha text not null,
  result jsonb not null,
  created_at timestamptz not null default now()
);
alter table public.factory_journey_supersessions_v2 enable row level security;
revoke all on table public.factory_journey_supersessions_v2 from public,anon,authenticated;
grant all on table public.factory_journey_supersessions_v2 to service_role;

-- Preserve the legacy request schema and replay semantics. The only new
-- admission path is guarded under the same locked project row.
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
 -- The project row is locked above. A second independent Start is not an
 -- idempotent replay and cannot be admitted until the first journey terminates.
 if exists(select 1 from public.factory_journeys other
   where other.project_id=p.id
     and other.state not in ('closed','released_observed','superseded'))
 then raise exception 'project has an unfinished V2 journey' using errcode='PT409'; end if;
 insert into public.factory_journeys(project_id,request_id,request_source,auth_actor_ref,auth_event_id,request_digest,request_snapshot,issue_repository,issue_number,state)
 values(p.id,p_request_id,p_request_source,p_auth_actor_ref,p_auth_event_id,p_request_digest,
   jsonb_build_object('text',request_text,'digest',p_request_digest,'source',p_request_source,
     'control_issue_repository',p_issue_repository,'control_issue_number',p_issue_number,
     'authorization_event_id',p_auth_event_id),p_issue_repository,p_issue_number,'awaiting_source') returning * into j;
 insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
 values(p.id,'human',p_auth_actor_ref,'journey.intake_accepted',jsonb_build_object('journey_id',j.id,'request_id',p_request_id,'source',p_request_source,'state',j.state));
 return jsonb_build_object('project_id',p.id,'journey_id',j.id,'request_id',p_request_id,'created',true,'state',j.state,'source',p_request_source);
end $fn$;

-- Even a stale pending V2 request cannot bind while another active journey
-- exists. The production resolver still requires immutable source evidence.
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
 if exists(select 1 from public.factory_journeys other where other.project_id=p.id
   and other.id<>j.id and other.state not in ('closed','released_observed','superseded'))
 then raise exception 'project has an incompatible V2 journey' using errcode='PT409'; end if;
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

create or replace function public.factory_supersede_inactive_journey_v2(
  p_project_key text, p_journey_id uuid, p_command_id uuid, p_actor_user_id uuid,
  p_expected_generation bigint, p_expected_version bigint,
  p_expected_old_source_sha text, p_new_preview_ref text,
  p_verified_main_sha text, p_verified_preview_sha text
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare
  p public.factory_projects%rowtype;
  c public.factory_project_execution_controls%rowtype;
  j public.factory_journeys%rowtype;
  previous public.factory_journey_supersessions_v2%rowtype;
  old_policy jsonb;
  new_policy jsonb;
  new_digest text;
  new_version integer;
  receipt jsonb;
begin
  if p_project_key is null or p_journey_id is null or p_command_id is null or p_actor_user_id is null
     or p_expected_generation is null or p_expected_version is null
     or p_expected_old_source_sha !~ '^[0-9a-f]{40}$'
     or p_verified_main_sha !~ '^[0-9a-f]{40}$'
     or p_verified_preview_sha !~ '^[0-9a-f]{40}$'
     or p_verified_main_sha is distinct from p_verified_preview_sha
     or p_new_preview_ref is null
     or p_new_preview_ref !~ '^preview/[A-Za-z0-9][A-Za-z0-9/_-]{0,100}$'
     or position('..' in p_new_preview_ref)>0 or position('//' in p_new_preview_ref)>0
  then raise exception 'invalid V2 supersession request' using errcode='PT400'; end if;

  -- This is a service-role-only administrative operation with an active
  -- allowlisted operator. The broker must not forward arbitrary web requests.
  if not exists (select 1 from public.factory_console_operators op
    where op.user_id=p_actor_user_id and op.is_active=true and op.role='admin')
  then raise exception 'inactive or unauthorized V2 supersession operator' using errcode='PT403'; end if;

  select * into p from public.factory_projects
    where project_key=btrim(p_project_key) and is_active=true for update;
  if p.id is null or p.project_kind is distinct from 'existing' or p.repository is null
  then raise exception 'active existing project required' using errcode='PT409'; end if;

  -- Serialized replay is checked before the new epoch CAS.
  select * into previous from public.factory_journey_supersessions_v2
    where command_id=p_command_id;
  if previous.command_id is not null then
    if previous.project_id is distinct from p.id
       or previous.journey_id is distinct from p_journey_id
       or previous.actor_user_id is distinct from p_actor_user_id
       or previous.expected_generation is distinct from p_expected_generation
       or previous.expected_version is distinct from p_expected_version
       or previous.prior_source_commit is distinct from p_expected_old_source_sha
       or previous.new_preview_ref is distinct from p_new_preview_ref
       or previous.verified_main_sha is distinct from p_verified_main_sha
       or previous.verified_preview_sha is distinct from p_verified_preview_sha
    then raise exception 'V2 supersession command replay mismatch' using errcode='PT409'; end if;
    return previous.result;
  end if;

  select * into c from public.factory_project_execution_controls
    where project_id=p.id for update;
  select * into j from public.factory_journeys
    where project_id=p.id and id=p_journey_id for update;
  if c.state is distinct from 'running' or c.generation is distinct from p_expected_generation
     or c.version is distinct from p_expected_version
     or j.id is null or j.state is distinct from 'executing'
     or j.execution_generation is distinct from c.generation
     or j.source_commit is distinct from p_expected_old_source_sha
  then raise exception 'V2 supersession stale control or journey' using errcode='PT409'; end if;

  old_policy:=p.manifest->'journey_delivery_binding_v2';
  if jsonb_typeof(old_policy) is distinct from 'object'
     or old_policy->>'source_mode' is distinct from 'main_snapshot'
     or old_policy->>'enabled' is distinct from 'true'
     or old_policy->>'release_base_ref' is distinct from 'main'
     or old_policy->>'digest' is distinct from j.policy_digest
     or j.binding->>'preview_base_ref' is distinct from old_policy->>'preview_base_ref'
     or j.binding->>'integration_branch' is distinct from 'factory/journey-'||j.id::text
     or j.binding->>'repository' is distinct from p.repository
     or old_policy->>'preview_base_ref' is not distinct from p_new_preview_ref
     or old_policy->>'version' !~ '^[1-9][0-9]*$'
     or (old_policy->>'version')::integer is distinct from j.project_policy_version
     or j.candidate_commit is not null or j.work_unit_output_commit is not null
     or j.binding->>'source_commit' is distinct from j.source_commit
     or j.binding->>'execution_generation' is distinct from c.generation::text
     or j.preview_merge_sha is not null or j.production_release_sha is not null
  then raise exception 'V2 supersession provenance or delivery is unsafe' using errcode='PT409'; end if;

  -- Every existing V2 descendant must be terminal and without any lease,
  -- candidate output, release evidence, or unresolved human gate.
  if not public.factory_control_quiescent(p.id)
     or exists(select 1 from public.factory_journeys other where other.project_id=p.id
       and other.id<>j.id and other.state not in ('closed','released_observed','superseded'))
     or exists(select 1 from public.factory_runs r
       join public.factory_tasks t on t.id=r.task_id
       where t.project_id=p.id and r.status in ('created','queued','running'))
     or exists(select 1 from public.factory_tasks t where t.journey_id=j.id
       and t.status not in ('completed','blocked','failed','cancelled','superseded'))
     or exists(select 1 from public.factory_runs r where r.journey_id=j.id
       and (r.status not in ('completed','blocked','failed','cancelled')
            or r.lease_owner is not null or r.candidate_commit is not null))
     or exists(select 1 from public.factory_change_sets cs where cs.journey_id=j.id
       and (cs.status<>'blocked' or cs.lease_owner is not null
            or cs.release_run_id is not null
            or cs.integration_branch is distinct from j.binding->>'integration_branch'))
     or not exists(select 1 from public.factory_change_sets cs
       where cs.journey_id=j.id and cs.status='blocked')
     or not exists(select 1 from public.factory_change_set_work_units wu
       join public.factory_change_sets cs on cs.id=wu.change_set_id
       where cs.journey_id=j.id and wu.status='blocked')
     or exists(select 1 from public.factory_change_set_work_units wu
       join public.factory_change_sets cs on cs.id=wu.change_set_id
       where cs.journey_id=j.id and (
         wu.status not in ('blocked','failed') or wu.output_commit is not null))
     or exists(select 1 from public.factory_human_gates gate
       join public.factory_runs r on r.id=gate.run_id where r.journey_id=j.id)
     or exists(select 1 from public.factory_deployments d
       join public.factory_runs r on r.id=d.run_id where r.journey_id=j.id)
     or exists(select 1 from public.factory_release_reports report
       join public.factory_runs r on r.id=report.run_id where r.journey_id=j.id)
     or exists(select 1 from public.factory_audit_events a
       join public.factory_runs r on r.id=a.run_id where r.journey_id=j.id
         and a.event_type in ('release.awaiting_human_merge','release.human_merge_observed',
                              'change_set.nonproduction_merge.observed'))
  then raise exception 'V2 journey is not provably inactive and unshipped' using errcode='PT409'; end if;

  -- The caller's GitHub preflight attests both exact refs. A new V2
  -- resolver independently verifies those refs again before binding.
  new_version:=(old_policy->>'version')::integer+1;
  new_policy:=jsonb_build_object(
    'enabled',true,'version',new_version,'source_mode','main_snapshot',
    'preview_base_ref',p_new_preview_ref,'release_base_ref','main',
    'source_commit_pin',p_verified_main_sha,
    'preview_base_source_sha',p_verified_preview_sha
  );
  new_digest:=encode(extensions.digest(convert_to(new_policy::text,'UTF8'),'sha256'),'hex');
  new_policy:=new_policy||jsonb_build_object('digest',new_digest);

  update public.factory_journeys set state='superseded',updated_at=now()
    where id=j.id and state='executing';
  if not found then raise exception 'V2 supersession journey CAS lost' using errcode='PT409'; end if;
  update public.factory_projects set
    manifest=jsonb_set(p.manifest,'{journey_delivery_binding_v2}',new_policy,false),
    updated_at=now() where id=p.id;
  update public.factory_project_execution_controls set
    generation=generation+1, version=version+1,updated_at=now()
    where project_id=p.id and generation=c.generation and version=c.version;
  if not found then raise exception 'V2 supersession epoch CAS lost' using errcode='PT409'; end if;
  receipt:=jsonb_build_object(
    'status','superseded','created',true,'project_id',p.id,
    'superseded_journey_id',j.id,'previous_generation',c.generation,
    'generation',c.generation+1,'version',c.version+1,
    'policy_version',new_version,'policy_digest',new_digest,
    'new_preview_ref',p_new_preview_ref,'verified_sha',p_verified_main_sha,
    'production_release_authorized',false
  );
  insert into public.factory_journey_supersessions_v2(
    command_id,project_id,journey_id,actor_user_id,expected_generation,expected_version,
    prior_source_commit,new_preview_ref,verified_main_sha,verified_preview_sha,result
  ) values(p_command_id,p.id,j.id,p_actor_user_id,p_expected_generation,p_expected_version,
    p_expected_old_source_sha,p_new_preview_ref,p_verified_main_sha,p_verified_preview_sha,receipt);
  insert into public.factory_audit_events(
    project_id,actor_type,actor_ref,event_type,payload
  ) values (p.id,'human',p_actor_user_id::text,'journey.superseded',receipt||
    jsonb_build_object('command_id',p_command_id,'reason','inactive_blocked_work_unit',
                       'verification_source','authorized_operator_github_preflight'));
  return receipt;
end $fn$;

revoke all on function public.factory_enqueue_journey_intake_v2(text,text,uuid,text,text,text,text,text,integer) from public,anon,authenticated;
grant execute on function public.factory_enqueue_journey_intake_v2(text,text,uuid,text,text,text,text,text,integer) to service_role;
revoke all on function public.factory_bind_journey_source_v2(text,uuid,bigint,integer,jsonb) from public,anon,authenticated;
grant execute on function public.factory_bind_journey_source_v2(text,uuid,bigint,integer,jsonb) to service_role;
revoke all on function public.factory_supersede_inactive_journey_v2(text,uuid,uuid,uuid,bigint,bigint,text,text,text,text) from public,anon,authenticated;
grant execute on function public.factory_supersede_inactive_journey_v2(text,uuid,uuid,uuid,bigint,bigint,text,text,text,text) to service_role;
commit;
