-- Independent full-product certification producer.  The global observer stays
-- read-only; this service-role-only path creates an isolated assessment run.
begin;

create table if not exists public.factory_product_readiness_certifications (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.factory_projects(id) on delete cascade,
  run_id uuid not null unique references public.factory_runs(id) on delete cascade,
  repository text not null,
  assessed_commit text not null check (assessed_commit ~ '^[0-9a-f]{40}$'),
  evidence_digest text not null check (evidence_digest ~ '^[0-9a-f]{64}$'),
  state text not null default 'collecting' check (state in ('collecting','persisted')),
  evaluation_id uuid references public.factory_evaluations(id) on delete restrict,
  created_at timestamptz not null default now(),
  persisted_at timestamptz,
  unique(project_id, assessed_commit, evidence_digest)
);
alter table public.factory_product_readiness_certifications enable row level security;
revoke all on table public.factory_product_readiness_certifications from public, anon, authenticated;
grant select,insert,update,delete on table public.factory_product_readiness_certifications to service_role;
create index if not exists idx_factory_readiness_certifications_project_sha
  on public.factory_product_readiness_certifications(project_id, assessed_commit, created_at desc);
-- Historical evaluations can legitimately predate this producer and are not
-- rewritten here. New duplicate prevention is enforced by the certification
-- identity row locked by the RPCs below, avoiding a risky global unique index.

create or replace function public.factory_begin_product_readiness_certification_v1(
  p_project_key text, p_repository text, p_assessed_commit text, p_evidence_digest text
) returns jsonb language plpgsql security invoker set search_path='' as $f$
declare v_project public.factory_projects%rowtype; v_task_id uuid; v_run_id uuid;
declare v_cert public.factory_product_readiness_certifications%rowtype;
begin
 if nullif(btrim(p_project_key),'') is null
    or p_repository !~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'
    or p_assessed_commit !~ '^[0-9a-f]{40}$'
    or p_evidence_digest !~ '^[0-9a-f]{64}$' then
  raise exception 'invalid product readiness certification identity' using errcode='PT400';
 end if;
 select * into v_project from public.factory_projects
 where project_key=p_project_key for update;
 if not found or not v_project.is_active or v_project.repository is distinct from p_repository then
  raise exception 'project is not an active exact repository match' using errcode='PT403';
 end if;
 select * into v_cert from public.factory_product_readiness_certifications
 where project_id=v_project.id and assessed_commit=p_assessed_commit and evidence_digest=p_evidence_digest
 for update;
 if found then
  return jsonb_build_object('certification_id',v_cert.id,'run_id',v_cert.run_id,
   'assessed_commit',v_cert.assessed_commit,'state',v_cert.state,'idempotent',true);
 end if;
 insert into public.factory_tasks(project_id,external_key,title,description,status,complexity,risk,acceptance_criteria,depends_on)
 values(v_project.id,'product-readiness:'||p_evidence_digest,
   'Independent product readiness certification','Isolated deterministic evidence assessment.',
   'running','low','{}'::jsonb,'[]'::jsonb,'[]'::jsonb) returning id into v_task_id;
 insert into public.factory_runs(task_id,status,execution_route,source_commit,candidate_commit,metadata,started_at)
 values(v_task_id,'running','direct',p_assessed_commit,p_assessed_commit,
   jsonb_build_object('source','independent-product-certifier','purpose','product_readiness_assessment',
     'repository',p_repository,'assessed_commit',p_assessed_commit,'evidence_digest',p_evidence_digest),now())
 returning id into v_run_id;
 insert into public.factory_product_readiness_certifications(project_id,run_id,repository,assessed_commit,evidence_digest)
 values(v_project.id,v_run_id,p_repository,p_assessed_commit,p_evidence_digest) returning * into v_cert;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,v_task_id,v_run_id,'system','product-readiness-certifier','product_readiness.certification_started',
  jsonb_build_object('assessed_commit',p_assessed_commit,'evidence_digest',p_evidence_digest));
 return jsonb_build_object('certification_id',v_cert.id,'run_id',v_run_id,
  'assessed_commit',p_assessed_commit,'state',v_cert.state,'idempotent',false);
end;
$f$;
revoke all on function public.factory_begin_product_readiness_certification_v1(text,text,text,text)
 from public,anon,authenticated;
grant execute on function public.factory_begin_product_readiness_certification_v1(text,text,text,text) to service_role;

create or replace function public.factory_persist_product_readiness_certification_v1(
 p_certification_id uuid, p_run_id uuid, p_assessed_commit text, p_evidence_digest text,
 p_result jsonb, p_report jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $f$
declare v_cert public.factory_product_readiness_certifications%rowtype; v_run public.factory_runs%rowtype;
declare v_task public.factory_tasks%rowtype; v_eval public.factory_evaluations%rowtype;
declare v_status text; v_ready boolean; v_domain text; v_coverage text[];
begin
 if p_assessed_commit !~ '^[0-9a-f]{40}$' or p_evidence_digest !~ '^[0-9a-f]{64}$'
    or jsonb_typeof(p_result) <> 'object' or jsonb_typeof(p_report) <> 'object' then
  raise exception 'invalid certification persistence payload' using errcode='PT400';
 end if;
 select * into v_cert from public.factory_product_readiness_certifications where id=p_certification_id for update;
 if not found or v_cert.run_id<>p_run_id or v_cert.assessed_commit<>p_assessed_commit
    or v_cert.evidence_digest<>p_evidence_digest then
  raise exception 'certification provenance mismatch' using errcode='PT409';
 end if;
 select * into v_run from public.factory_runs where id=p_run_id for update;
 select * into v_task from public.factory_tasks where id=v_run.task_id for update;
 if v_task.project_id<>v_cert.project_id or v_run.candidate_commit<>p_assessed_commit
    or v_run.metadata->>'purpose'<>'product_readiness_assessment'
    or v_run.metadata->>'evidence_digest'<>p_evidence_digest then
  raise exception 'run provenance mismatch' using errcode='PT409';
 end if;
 if p_result->>'assessed_commit'<>p_assessed_commit
    or p_result->>'assessment_ref'<>('product-readiness-certifier:'||p_evidence_digest)
    or jsonb_typeof(p_result->'domains')<>'object' or jsonb_typeof(p_result->'blockers')<>'array'
    or jsonb_typeof(p_report->'criteria')<>'object' then
  raise exception 'assessment result provenance or shape invalid' using errcode='PT400';
 end if;
 foreach v_domain in array array['security','observability_operations','test_strategy','product_experience','documentation','functional_completeness'] loop
  if jsonb_typeof(p_result->'domains'->v_domain)<>'object'
     or p_result->'domains'->v_domain->>'status' not in ('passed','failed','not_applicable')
     or jsonb_typeof(p_report->'criteria'->v_domain)<>'object' then
   raise exception 'incomplete six-domain assessment' using errcode='PT400';
  end if;
 end loop;
 v_ready := (p_result->'ready') = 'true'::jsonb;
 if (p_result->>'status') is distinct from
    (case when v_ready then 'passed' else 'not_ready' end) then
  raise exception 'assessment status contradicts readiness' using errcode='PT400';
 end if;
 if v_cert.state='persisted' then
  select * into v_eval from public.factory_evaluations where id=v_cert.evaluation_id;
  if not found or v_eval.result<>p_result or v_eval.baseline_ref<>p_assessed_commit then
   raise exception 'persisted certification replay contradicts durable result' using errcode='PT409';
  end if;
  return jsonb_build_object('run_id',p_run_id,'assessment_id',v_eval.id,
   'assessed_commit',p_assessed_commit,'evaluation_status',v_eval.status,'idempotent',true);
 end if;
 v_status:=case when v_ready then 'passed' else 'failed' end;
 insert into public.factory_evaluations(run_id,eval_type,status,baseline_ref,result)
 values(p_run_id,'product_readiness',v_status,p_assessed_commit,p_result) returning * into v_eval;
 update public.factory_product_readiness_certifications set state='persisted',evaluation_id=v_eval.id,persisted_at=now()
 where id=v_cert.id;
 update public.factory_runs set status='completed',finished_at=now() where id=p_run_id;
 update public.factory_tasks set status='completed',updated_at=now() where id=v_task.id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_cert.project_id,v_task.id,p_run_id,'system','product-readiness-certifier','product_readiness.assessed',
  jsonb_build_object('assessed_commit',p_assessed_commit,'ready',v_ready,'evaluation_id',v_eval.id,
   'evaluation_status',v_status,'blockers',p_result->'blockers'));
 return jsonb_build_object('run_id',p_run_id,'assessment_id',v_eval.id,'assessed_commit',p_assessed_commit,
  'evaluation_status',v_status,'idempotent',false);
end;
$f$;
revoke all on function public.factory_persist_product_readiness_certification_v1(uuid,uuid,text,text,jsonb,jsonb)
 from public,anon,authenticated;
grant execute on function public.factory_persist_product_readiness_certification_v1(uuid,uuid,text,text,jsonb,jsonb) to service_role;
commit;
