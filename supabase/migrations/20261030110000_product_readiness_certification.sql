-- Independent full-product certification producer.  The global observer stays
-- read-only; this service-role-only path creates an isolated assessment run.
begin;

create table if not exists public.factory_product_readiness_certifications (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.factory_projects(id) on delete cascade,
  -- Reserve a run identity without creating a runnable task/run. A failed
  -- assessment must NEVER prevent an unrelated authorized project Start.
  reservation_run_id uuid not null unique default gen_random_uuid(),
  run_id uuid unique references public.factory_runs(id) on delete restrict,
  repository text not null,
  assessed_commit text not null check (assessed_commit ~ '^[0-9a-f]{40}$'),
  evidence_digest text not null check (evidence_digest ~ '^[0-9a-f]{64}$'),
  state text not null default 'collecting' check (state in ('collecting','persisted')),
  evaluation_id uuid references public.factory_evaluations(id) on delete restrict,
  -- Superseded assessments remain immutable history; exactly one is current.
  is_current boolean not null default false,
  report jsonb,
  created_at timestamptz not null default now(),
  persisted_at timestamptz,
  unique(project_id, assessed_commit, evidence_digest),
  constraint certification_state_consistency check (
    (state='collecting' and run_id is null and evaluation_id is null
      and persisted_at is null and is_current=false and report is null)
    or (state='persisted' and run_id=reservation_run_id and run_id is not null
      and evaluation_id is not null and persisted_at is not null and report is not null)
  )
);
alter table public.factory_product_readiness_certifications enable row level security;
revoke all on table public.factory_product_readiness_certifications from public, anon, authenticated;
grant select,insert,update,delete on table public.factory_product_readiness_certifications to service_role;
create index if not exists idx_factory_readiness_certifications_project_sha
  on public.factory_product_readiness_certifications(project_id, assessed_commit, created_at desc);
create unique index if not exists idx_factory_readiness_one_current_per_sha
  on public.factory_product_readiness_certifications(project_id, assessed_commit)
  where is_current;
-- Historical evaluations can legitimately predate this producer and are not
-- rewritten here. New duplicate prevention is enforced by the certification
-- identity row locked by the RPCs below, avoiding a risky global unique index.

create or replace function public.factory_begin_product_readiness_certification_v1(
  p_project_key text, p_repository text, p_assessed_commit text, p_evidence_digest text
) returns jsonb language plpgsql security invoker set search_path='' as $f$
declare
 v_project public.factory_projects%rowtype;
 v_cert public.factory_product_readiness_certifications%rowtype;
begin
 if nullif(btrim(p_project_key),'') is null
    or coalesce(p_repository,'') !~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'
    or coalesce(p_assessed_commit,'') !~ '^[0-9a-f]{40}$'
    or coalesce(p_evidence_digest,'') !~ '^[0-9a-f]{64}$' then
  raise exception 'invalid product readiness certification identity' using errcode='PT400';
 end if;
 -- Same serialization order as persist: project first, certification second.
 select * into v_project from public.factory_projects
 where project_key=p_project_key for update;
 if not found or not v_project.is_active or v_project.repository is distinct from p_repository then
  raise exception 'project is not an active exact repository match' using errcode='PT403';
 end if;
 select * into v_cert from public.factory_product_readiness_certifications
 where project_id=v_project.id and assessed_commit=p_assessed_commit and evidence_digest=p_evidence_digest
 for update;
 if found then
  return jsonb_build_object('certification_id',v_cert.id,
   'run_id',v_cert.reservation_run_id,'assessed_commit',v_cert.assessed_commit,
   'state',v_cert.state,'idempotent',true);
 end if;
 -- RESERVATION ONLY. Do not create an unfinished root task or running run:
 -- the owner Start admission checks unfinished roots and would block production.
 insert into public.factory_product_readiness_certifications(
  project_id,repository,assessed_commit,evidence_digest)
 values(v_project.id,p_repository,p_assessed_commit,p_evidence_digest)
 returning * into v_cert;
 insert into public.factory_audit_events(project_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,'system','product-readiness-certifier','product_readiness.certification_reserved',
  jsonb_build_object('assessed_commit',p_assessed_commit,'evidence_digest',p_evidence_digest,
    'certification_id',v_cert.id));
 return jsonb_build_object('certification_id',v_cert.id,
  'run_id',v_cert.reservation_run_id,'assessed_commit',p_assessed_commit,
  'state',v_cert.state,'idempotent',false);
end;
$f$;
revoke all on function public.factory_begin_product_readiness_certification_v1(text,text,text,text)
 from public,anon,authenticated;
grant execute on function public.factory_begin_product_readiness_certification_v1(text,text,text,text) to service_role;

create or replace function public.factory_persist_product_readiness_certification_v1(
 p_certification_id uuid, p_run_id uuid, p_assessed_commit text, p_evidence_digest text,
 p_result jsonb, p_report jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $f$
declare
 v_cert public.factory_product_readiness_certifications%rowtype;
 v_project public.factory_projects%rowtype;
 v_project_id uuid;
 v_task_id uuid;
 v_eval public.factory_evaluations%rowtype;
 v_run public.factory_runs%rowtype;
 v_task public.factory_tasks%rowtype;
 v_status text;
 v_ready boolean;
 v_domain text;
 v_domain_status text;
begin
 if coalesce(p_assessed_commit,'') !~ '^[0-9a-f]{40}$'
    or coalesce(p_evidence_digest,'') !~ '^[0-9a-f]{64}$'
    or jsonb_typeof(p_result) is distinct from 'object'
    or jsonb_typeof(p_report) is distinct from 'object' then
  raise exception 'invalid certification persistence payload' using errcode='PT400';
 end if;
 -- Follow project's lock order, avoiding deadlocks with begin/Start.
 select project_id into v_project_id from public.factory_product_readiness_certifications
 where id=p_certification_id;
 if not found then
  raise exception 'certification identity missing' using errcode='PT409';
 end if;
 select * into v_project from public.factory_projects where id=v_project_id for update;
 select * into v_cert from public.factory_product_readiness_certifications
 where id=p_certification_id for update;
 if v_cert.project_id is distinct from v_project.id
    or v_cert.reservation_run_id is distinct from p_run_id
    or v_cert.assessed_commit is distinct from p_assessed_commit
    or v_cert.evidence_digest is distinct from p_evidence_digest
    or v_cert.repository is distinct from v_project.repository then
  raise exception 'certification provenance mismatch' using errcode='PT409';
 end if;
 if p_result->>'assessed_commit' is distinct from p_assessed_commit
    or p_result->>'assessment_ref' is distinct from ('product-readiness-certifier:'||p_evidence_digest)
    or jsonb_typeof(p_result->'domains') is distinct from 'object'
    or jsonb_typeof(p_result->'blockers') is distinct from 'array'
    or jsonb_typeof(p_result->'ready') is distinct from 'boolean'
    or jsonb_typeof(p_report->'criteria') is distinct from 'object'
    or p_report->'assessment' is distinct from p_result then
  raise exception 'assessment result provenance or shape invalid' using errcode='PT400';
 end if;
 foreach v_domain in array array['security','observability_operations','test_strategy',
              'product_experience','documentation','functional_completeness'] loop
  v_domain_status:=p_result->'domains'->v_domain->>'status';
  if jsonb_typeof(p_result->'domains'->v_domain) is distinct from 'object'
     or coalesce(v_domain_status,'') not in ('passed','failed','not_applicable')
     or jsonb_typeof(p_report->'criteria'->v_domain) is distinct from 'object' then
   raise exception 'incomplete six-domain assessment' using errcode='PT400';
  end if;
 end loop;
 v_ready:=p_result->'ready'='true'::jsonb;
 if (p_result->>'status') is distinct from
    (case when v_ready then 'passed' else 'not_ready' end) then
  raise exception 'assessment status contradicts readiness' using errcode='PT400';
 end if;
 if v_ready and (p_result->'blockers'<>'[]'::jsonb or exists (
    select 1 from jsonb_each(p_result->'domains') as d
    where d.value->>'status' not in ('passed','not_applicable')
 )) then
  raise exception 'passing assessment contains blockers or failed domains' using errcode='PT400';
 end if;
 if not v_ready and jsonb_array_length(p_result->'blockers')=0 then
  raise exception 'not-ready assessment requires explicit blockers' using errcode='PT400';
 end if;
 if v_cert.state='persisted' then
  select * into v_eval from public.factory_evaluations where id=v_cert.evaluation_id;
  select * into v_run from public.factory_runs where id=v_cert.run_id;
  select * into v_task from public.factory_tasks where id=v_run.task_id;
  if v_eval.id is null or v_eval.result is distinct from p_result
     or v_eval.baseline_ref is distinct from p_assessed_commit
     or v_eval.run_id is distinct from p_run_id
     or v_cert.report is distinct from p_report
     or v_task.project_id is distinct from v_cert.project_id
     or v_run.metadata->>'purpose' is distinct from 'product_readiness_assessment' then
   raise exception 'persisted certification replay contradicts durable result' using errcode='PT409';
  end if;
  return jsonb_build_object('run_id',p_run_id,'assessment_id',v_eval.id,
   'assessed_commit',p_assessed_commit,'evaluation_status',v_eval.status,'idempotent',true);
 end if;
 if v_cert.state is distinct from 'collecting'
    or v_cert.run_id is not null or v_cert.evaluation_id is not null then
  raise exception 'certification state does not permit persistence' using errcode='PT409';
 end if;
 -- Atomic finalization: a failure here rolls back the task, run, evaluation
 -- and authoritative pointer. Pending reservations NEVER enter delivery queues.
 insert into public.factory_tasks(project_id,external_key,title,description,status,
                                  complexity,risk,acceptance_criteria,depends_on)
 values(v_cert.project_id,'product-readiness:'||p_evidence_digest,
   'Independent product readiness certification','Isolated deterministic evidence assessment.',
   'completed','low','{}'::jsonb,'[]'::jsonb,'[]'::jsonb)
 returning id into v_task_id;
 insert into public.factory_runs(id,task_id,status,execution_route,source_commit,
                                 candidate_commit,metadata,started_at,finished_at)
 values(v_cert.reservation_run_id,v_task_id,'completed','direct',
    p_assessed_commit,p_assessed_commit,
    jsonb_build_object('source','independent-product-certifier',
      'purpose','product_readiness_assessment','repository',v_cert.repository,
      'assessed_commit',p_assessed_commit,'evidence_digest',p_evidence_digest),now(),now());
 v_status:=case when v_ready then 'passed' else 'failed' end;
 insert into public.factory_evaluations(run_id,eval_type,status,baseline_ref,result)
 values(p_run_id,'product_readiness',v_status,p_assessed_commit,p_result) returning * into v_eval;
 -- Preserve old evaluations as immutable history; maintain one canonical
 -- pointer for the same project/SHA to allow evidence to improve without
 -- trapping the global observer behind duplicate rows.
 update public.factory_product_readiness_certifications
 set is_current=false
 where project_id=v_cert.project_id and assessed_commit=p_assessed_commit and is_current;
 update public.factory_product_readiness_certifications
 set state='persisted',run_id=p_run_id,evaluation_id=v_eval.id,report=p_report,
     persisted_at=now(),is_current=true
 where id=v_cert.id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_cert.project_id,v_task_id,p_run_id,'system','product-readiness-certifier',
  'product_readiness.assessed',
  jsonb_build_object('assessed_commit',p_assessed_commit,'ready',v_ready,
    'evaluation_id',v_eval.id,'evaluation_status',v_status,
    'evidence_digest',p_evidence_digest,'blockers',p_result->'blockers'));
 return jsonb_build_object('run_id',p_run_id,'assessment_id',v_eval.id,
    'assessed_commit',p_assessed_commit,'evaluation_status',v_status,'idempotent',false);
end;
$f$;
revoke all on function public.factory_persist_product_readiness_certification_v1(uuid,uuid,text,text,jsonb,jsonb)
 from public,anon,authenticated;
grant execute on function public.factory_persist_product_readiness_certification_v1(uuid,uuid,text,text,jsonb,jsonb) to service_role;
commit;
