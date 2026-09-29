create table if not exists public.factory_policy_decisions (
 id uuid primary key default gen_random_uuid(),
 project_id uuid not null references public.factory_projects(id) on delete cascade,
 run_id uuid not null references public.factory_runs(id) on delete cascade,
 policy_key text not null,
 policy_version integer not null check (policy_version >= 1),
 outcome text not null check (outcome in ('blocked','ready_for_human_release','allowed_nonproduction')),
 reasons jsonb not null default '[]'::jsonb,
 context jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(),
 constraint factory_policy_context_no_secrets check (
   not (context ?| array['token','secret','password','api_key','authorization','credential'])
 )
);
create index if not exists idx_factory_policy_decisions_run_created
 on public.factory_policy_decisions(run_id,created_at desc);
alter table public.factory_policy_decisions enable row level security;
revoke all on public.factory_policy_decisions from public,anon,authenticated;
grant select,insert on public.factory_policy_decisions to service_role;

create table if not exists public.factory_release_reports (
 id uuid primary key default gen_random_uuid(),
 project_id uuid not null references public.factory_projects(id) on delete cascade,
 run_id uuid not null references public.factory_runs(id) on delete cascade,
 policy_decision_id uuid references public.factory_policy_decisions(id) on delete set null,
 candidate_commit text not null,
 status text not null check (status in ('blocked','ready_for_human_release','released')),
 report jsonb not null,
 rollback jsonb not null,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 unique(run_id)
);
create index if not exists idx_factory_release_reports_project_status
 on public.factory_release_reports(project_id,status,created_at desc);
alter table public.factory_release_reports enable row level security;
revoke all on public.factory_release_reports from public,anon,authenticated;
grant select,insert,update on public.factory_release_reports to service_role;

create or replace function public.factory_get_release_facts(p_run_id uuid)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
 v_project_id uuid;
 v_candidate text;
 v_dod jsonb;
 v_req_total integer;
 v_req_verified integer;
 v_evals jsonb;
 v_preview jsonb;
 v_previous_production jsonb;
begin
 select t.project_id,r.candidate_commit into v_project_id,v_candidate
 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
 where r.id=p_run_id;
 if v_project_id is null then raise exception 'run not found'; end if;

 v_dod:=public.factory_get_definition_of_done_readiness(v_project_id);
 select count(*) into v_req_total
 from public.factory_requirements where project_id=v_project_id and status='active';
 select count(*) into v_req_verified
 from public.factory_requirements req
 where req.project_id=v_project_id and req.status='active'
   and exists(
     select 1 from public.factory_requirement_evidence e
     where e.requirement_id=req.id and e.status='passed'
   );

 select coalesce(jsonb_agg(jsonb_build_object(
   'eval_type',x.eval_type,'status',x.status,'baseline_ref',x.baseline_ref
 ) order by x.created_at),'[]'::jsonb) into v_evals
 from (
  select eval_type,status,baseline_ref,created_at
  from public.factory_evaluations
  where run_id=p_run_id
  order by created_at desc
  limit 50
 ) x;

 select jsonb_build_object(
  'environment',d.environment,'status',d.status,'deployment_ref',d.deployment_ref,
  'rollback_ref',d.rollback_ref,'deployed_at',d.deployed_at
 ) into v_preview
 from public.factory_deployments d
 where d.run_id=p_run_id and d.environment='preview'
 order by d.created_at desc limit 1;

 select jsonb_build_object(
  'deployment_ref',d.deployment_ref,'rollback_ref',d.rollback_ref,'deployed_at',d.deployed_at,
  'run_id',d.run_id
 ) into v_previous_production
 from public.factory_deployments d
 join public.factory_runs r on r.id=d.run_id
 join public.factory_tasks t on t.id=r.task_id
 where t.project_id=v_project_id and d.environment='production' and d.status in ('ready','success','deployed')
   and d.run_id<>p_run_id
 order by d.created_at desc limit 1;

 return jsonb_build_object(
  'project_id',v_project_id,
  'candidate_commit',v_candidate,
  'definition_of_done',v_dod,
  'requirements',jsonb_build_object('total',v_req_total,'with_passing_evidence',v_req_verified),
  'evaluations',coalesce(v_evals,'[]'::jsonb),
  'preview',v_preview,
  'previous_production',v_previous_production
 );
end;
$$;
revoke all on function public.factory_get_release_facts(uuid) from public,anon,authenticated;
grant execute on function public.factory_get_release_facts(uuid) to service_role;

create or replace function public.factory_record_policy_decision(
 p_run_id uuid,p_policy_key text,p_policy_version integer,p_outcome text,p_reasons jsonb,p_context jsonb
) returns uuid
language plpgsql
security invoker
set search_path=''
as $$
declare v_project_id uuid;v_id uuid;
begin
 if p_outcome not in ('blocked','ready_for_human_release','allowed_nonproduction') then raise exception 'invalid policy outcome'; end if;
 if p_policy_version<1 then raise exception 'invalid policy version'; end if;
 if jsonb_typeof(coalesce(p_reasons,'[]'::jsonb))<>'array' then raise exception 'reasons must be array'; end if;
 if jsonb_typeof(coalesce(p_context,'{}'::jsonb))<>'object' then raise exception 'context must be object'; end if;
 if coalesce(p_context,'{}'::jsonb) ?| array['token','secret','password','api_key','authorization','credential'] then
  raise exception 'secret-like policy context is forbidden';
 end if;
 select t.project_id into v_project_id from public.factory_runs r join public.factory_tasks t on t.id=r.task_id where r.id=p_run_id;
 if v_project_id is null then raise exception 'run not found'; end if;
 insert into public.factory_policy_decisions(project_id,run_id,policy_key,policy_version,outcome,reasons,context)
 values(v_project_id,p_run_id,p_policy_key,p_policy_version,p_outcome,coalesce(p_reasons,'[]'::jsonb),coalesce(p_context,'{}'::jsonb))
 returning id into v_id;
 if p_outcome='blocked' then
  update public.factory_runs set status='release_policy_blocked' where id=p_run_id;
 end if;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 select v_project_id,r.task_id,p_run_id,'system','release-policy','release.policy.decided',
  jsonb_build_object('decision_id',v_id,'policy_key',p_policy_key,'policy_version',p_policy_version,'outcome',p_outcome,'reasons',coalesce(p_reasons,'[]'::jsonb))
 from public.factory_runs r where r.id=p_run_id;
 return v_id;
end;
$$;
revoke all on function public.factory_record_policy_decision(uuid,text,integer,text,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.factory_record_policy_decision(uuid,text,integer,text,jsonb,jsonb) to service_role;

create or replace function public.factory_record_release_report(
 p_run_id uuid,p_policy_decision_id uuid,p_candidate_commit text,p_status text,p_report jsonb,p_rollback jsonb
) returns uuid
language plpgsql
security invoker
set search_path=''
as $$
declare v_project_id uuid;v_id uuid;
begin
 if p_status not in ('blocked','ready_for_human_release','released') then raise exception 'invalid release report status'; end if;
 if nullif(btrim(p_candidate_commit),'') is null then raise exception 'candidate commit required'; end if;
 if jsonb_typeof(coalesce(p_report,'{}'::jsonb))<>'object' or jsonb_typeof(coalesce(p_rollback,'{}'::jsonb))<>'object' then
  raise exception 'release report and rollback must be objects';
 end if;
 select t.project_id into v_project_id from public.factory_runs r join public.factory_tasks t on t.id=r.task_id where r.id=p_run_id;
 if v_project_id is null then raise exception 'run not found'; end if;
 if p_policy_decision_id is not null and not exists(
  select 1 from public.factory_policy_decisions where id=p_policy_decision_id and run_id=p_run_id
 ) then raise exception 'policy decision does not belong to run'; end if;

 insert into public.factory_release_reports(project_id,run_id,policy_decision_id,candidate_commit,status,report,rollback)
 values(v_project_id,p_run_id,p_policy_decision_id,p_candidate_commit,p_status,p_report,p_rollback)
 on conflict(run_id) do update set
  policy_decision_id=excluded.policy_decision_id,candidate_commit=excluded.candidate_commit,status=excluded.status,
  report=excluded.report,rollback=excluded.rollback,updated_at=now()
 returning id into v_id;
 return v_id;
end;
$$;
revoke all on function public.factory_record_release_report(uuid,uuid,text,text,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.factory_record_release_report(uuid,uuid,text,text,jsonb,jsonb) to service_role;

create or replace function public.factory_mark_release_report_released(p_run_id uuid,p_merge_sha text)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare v_id uuid;
begin
 if nullif(btrim(p_merge_sha),'') is null then raise exception 'merge sha required'; end if;
 update public.factory_release_reports
 set status='released',report=report||jsonb_build_object('merge_sha',p_merge_sha,'released_by','observed_manual_merge'),updated_at=now()
 where run_id=p_run_id
 returning id into v_id;
 if v_id is null then raise exception 'release report not found'; end if;
 return jsonb_build_object('id',v_id,'status','released','merge_sha',p_merge_sha);
end;
$$;
revoke all on function public.factory_mark_release_report_released(uuid,text) from public,anon,authenticated;
grant execute on function public.factory_mark_release_report_released(uuid,text) to service_role;
