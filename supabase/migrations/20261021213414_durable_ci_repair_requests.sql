-- Candidate only. Apply through the existing human Control Plane migration gate.
-- CI repair reuses Change Set work units; it never grants an auto-merge path.
begin;

create table public.factory_ci_repair_requests (
 id uuid primary key default gen_random_uuid(),
 project_id uuid not null references public.factory_projects(id) on delete cascade,
 change_set_id uuid not null references public.factory_change_sets(id) on delete cascade,
 source_run_id uuid not null references public.factory_runs(id) on delete cascade,
 release_run_id uuid references public.factory_runs(id) on delete set null,
 task_id uuid references public.factory_tasks(id) on delete set null,
 work_unit_id uuid references public.factory_change_set_work_units(id) on delete set null,
 repository text not null,
 pr_number integer not null check (pr_number > 0),
 branch text not null,
 original_candidate_commit text not null check (original_candidate_commit ~ '^[0-9a-f]{40}$'),
 repaired_commit text check (repaired_commit is null or repaired_commit ~ '^[0-9a-f]{40}$'),
 execution_generation bigint not null check (execution_generation > 0),
 attempt integer not null check (attempt between 1 and 4),
 max_attempts integer not null check (max_attempts between 1 and 3),
 failure_class text not null check (failure_class in ('code','infrastructure','runner','permission','quota','unknown')),
 failures jsonb not null check (jsonb_typeof(failures) = 'array' and jsonb_array_length(failures) between 1 and 20),
 write_scopes jsonb not null default '[]'::jsonb check (jsonb_typeof(write_scopes) = 'array'),
 status text not null check (status in ('queued','running','integrated','awaiting_ci','passed','ci_failed','blocked','exhausted','failed_gate')),
 constraint factory_ci_repair_attempt_bound check (
  (status = 'exhausted' and attempt = max_attempts + 1)
  or (status <> 'exhausted' and attempt <= max_attempts)
 ),
 blocker_reason text,
 lease_owner text,
 lease_expires_at timestamptz,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 unique(source_run_id, original_candidate_commit)
);
alter table public.factory_ci_repair_requests enable row level security;
revoke all on public.factory_ci_repair_requests from public, anon, authenticated;
grant select, insert, update on public.factory_ci_repair_requests to service_role;
create index idx_factory_ci_repair_requests_change_set
 on public.factory_ci_repair_requests(change_set_id, status, created_at);
create index idx_factory_ci_repair_requests_release
 on public.factory_ci_repair_requests(release_run_id, repaired_commit, status);

-- Release runs are created by an existing atomic Change Set RPC. Stamp the
-- current epoch in the same INSERT transaction, so a later CI failure cannot
-- revive a pre-pause candidate lacking a generation capability.
create or replace function public.factory_stamp_ci_release_epoch() returns trigger
language plpgsql security invoker set search_path='' as $f$
declare v_generation bigint; v_state text; v_project_id uuid;
begin
 if new.status='ci_pending' and new.metadata->>'source'='change-set'
    and nullif(new.metadata->>'change_set_id','') is not null
    and nullif(new.metadata->>'execution_generation','') is null then
  select t.project_id into v_project_id from public.factory_tasks t where t.id=new.task_id;
  select state,generation into v_state,v_generation
   from public.factory_project_execution_controls where project_id=v_project_id for share;
  if not found or v_state is distinct from 'running' or v_generation is null or v_generation<1 then
   raise exception 'CI release insert has no running project execution epoch' using errcode='PT409';
  end if;
  new.metadata:=coalesce(new.metadata,'{}'::jsonb)||jsonb_build_object('execution_generation',v_generation);
 end if;
 return new;
end;
$f$;
drop trigger if exists factory_stamp_ci_release_epoch on public.factory_runs;
create trigger factory_stamp_ci_release_epoch before insert on public.factory_runs
 for each row execute function public.factory_stamp_ci_release_epoch();

-- Extend the existing context packet source rather than introducing a second
-- executor prompt format.  The Direct/Codex worker receives only sanitized
-- check metadata and the durable write scopes.
create or replace function public.factory_work_unit_context_source(p_run_id uuid)
returns jsonb language plpgsql security invoker set search_path='' as $f$
declare
 v_run public.factory_runs%rowtype; v_task public.factory_tasks%rowtype; v_project public.factory_projects%rowtype;
 v_unit public.factory_change_set_work_units%rowtype; v_set public.factory_change_sets%rowtype;
 v_team public.factory_execution_team_plans%rowtype; v_assignment jsonb; v_repair jsonb;
begin
 select * into v_run from public.factory_runs where id=p_run_id;
 if not found then raise exception 'run not found'; end if;
 select * into v_task from public.factory_tasks where id=v_run.task_id;
 select * into v_project from public.factory_projects where id=v_task.project_id;
 select * into v_unit from public.factory_change_set_work_units where run_id=p_run_id;
 if not found then raise exception 'change-set work unit not found'; end if;
 select * into v_set from public.factory_change_sets where id=v_unit.change_set_id;
 select * into v_team from public.factory_execution_team_plans where id=v_set.team_plan_id;
 select value into v_assignment from jsonb_array_elements(coalesce(v_team.plan->'task_assignments','[]'::jsonb))
  where value->>'task_key'=v_unit.plan_task_key limit 1;
 select jsonb_build_object('repair_kind','ci','repair_request_id',r.id,'attempt',r.attempt,'max_attempts',r.max_attempts,
  'failure_class',r.failure_class,'failures',r.failures,'write_scopes',r.write_scopes,
  'candidate_commit',r.original_candidate_commit,'pr_number',r.pr_number,'branch',r.branch)
 into v_repair from public.factory_ci_repair_requests r where r.work_unit_id=v_unit.id order by r.created_at desc limit 1;
 if v_repair is null then
  select jsonb_build_object('repair_kind','specialist','repair_job_id',r.id,'cycle',r.cycle,'max_cycles',r.max_cycles,
   'source_role',r.source_role,'finding',r.finding,'write_scopes',r.write_scopes,'candidate_commit',r.candidate_commit)
  into v_repair from public.factory_repair_jobs r where r.work_unit_id=v_unit.id order by r.created_at desc limit 1;
 end if;
 return jsonb_build_object(
  'project_key',v_project.project_key,'repository',v_project.repository,'change_set_id',v_set.id,
  'work_unit_id',v_unit.id,'plan_task_key',v_unit.plan_task_key,'agent_key',v_unit.agent_key,'wave',v_unit.wave,
  'task',jsonb_build_object('title',v_task.title,'description',v_task.description,'acceptance_criteria',v_task.acceptance_criteria),
  'assignment',coalesce(v_assignment,jsonb_build_object('task_key',v_unit.plan_task_key,'agent_key',v_unit.agent_key,
   'scope_keys',coalesce(v_repair->'write_scopes','[]'::jsonb),'required_capabilities',jsonb_build_array('implementation'),'depends_on','[]'::jsonb)),
  'repair',coalesce(v_repair,'{}'::jsonb),
  'constraints',jsonb_build_array('Never include secrets, credentials or tokens in model context.',
   'Write only inside the explicit work-unit scopes.','Do not bypass, disable or weaken tests, CI, permissions or release gates.',
   'Do not merge or publish production.')
 );
end;
$f$;
revoke all on function public.factory_work_unit_context_source(uuid) from public,anon,authenticated;
grant execute on function public.factory_work_unit_context_source(uuid) to service_role;

create or replace function public.factory_enqueue_ci_repair(
 p_source_run_id uuid, p_project_id uuid, p_change_set_id uuid,
 p_repository text, p_pr_number integer, p_branch text, p_candidate_commit text,
 p_execution_generation bigint, p_failure_class text, p_failures jsonb,
 p_max_attempts integer default 2
) returns jsonb language plpgsql security invoker set search_path='' as $f$
declare
 v_run public.factory_runs%rowtype; v_set public.factory_change_sets%rowtype;
 v_project_id uuid; v_generation bigint; v_state text; v_existing public.factory_ci_repair_requests%rowtype;
 v_attempt integer; v_task_id uuid; v_unit_id uuid; v_request_id uuid; v_wave integer; v_scopes jsonb; v_receipt jsonb;
begin
 if p_source_run_id is null or p_project_id is null or p_change_set_id is null
    or p_pr_number is null or p_pr_number < 1 or p_execution_generation is null or p_execution_generation < 1
    or nullif(btrim(p_repository),'') is null or nullif(btrim(p_branch),'') is null
    or p_candidate_commit !~ '^[0-9a-f]{40}$'
    or p_failure_class not in ('code','infrastructure','runner','permission','quota','unknown')
    or p_max_attempts not between 1 and 3
    or jsonb_typeof(p_failures) <> 'array' or jsonb_array_length(p_failures) not between 1 and 20
    or exists(select 1 from jsonb_array_elements(p_failures) f
              where jsonb_typeof(f.value) <> 'object'
                 or nullif(btrim(f.value->>'name'),'') is null
                 or nullif(btrim(f.value->>'conclusion'),'') is null
                 or f.value->>'failure_class' not in ('code','infrastructure','runner','permission','quota','unknown')) then
  raise exception 'invalid exact CI repair request' using errcode='PT400';
 end if;
 select r.* into v_run
 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
 where r.id=p_source_run_id for update of r;
 select t.project_id into v_project_id from public.factory_tasks t where t.id=v_run.task_id;
 if not found or v_project_id is distinct from p_project_id
    or v_run.status is distinct from 'ci_pending'
    or v_run.candidate_commit is distinct from p_candidate_commit
    or v_run.branch_name is distinct from p_branch
    or v_run.metadata->>'change_set_id' is distinct from p_change_set_id::text
    or v_run.metadata->>'execution_generation' is distinct from p_execution_generation::text then
  raise exception 'CI repair source identity or epoch revoked' using errcode='PT409';
 end if;
 select state,generation into v_state,v_generation
 from public.factory_project_execution_controls where project_id=p_project_id for share;
 if not found or v_state is distinct from 'running' or v_generation is distinct from p_execution_generation then
  raise exception 'CI repair project execution epoch revoked' using errcode='PT409';
 end if;
 select * into v_set from public.factory_change_sets where id=p_change_set_id for update;
 if not found or v_set.project_id is distinct from p_project_id
    or v_set.status is distinct from 'ci_pending' or v_set.release_run_id is distinct from p_source_run_id
    or v_set.candidate_commit is distinct from p_candidate_commit
    or v_set.integration_branch is distinct from p_branch then
  raise exception 'CI repair Change Set candidate revoked' using errcode='PT409';
 end if;
 select metadata into v_receipt from public.factory_tool_usage
 where run_id=p_source_run_id and operation='create_pr'
 order by created_at desc limit 1;
 if v_receipt is null or (v_receipt->>'pr')::integer is distinct from p_pr_number
    or v_receipt->>'head_sha' is distinct from p_candidate_commit
    or v_receipt->>'change_set_id' is distinct from p_change_set_id::text then
  raise exception 'CI repair durable PR receipt revoked' using errcode='PT409';
 end if;
 -- This run may itself be the revalidated candidate from an earlier repair.
 -- Persist its failed CI result before creating the next bounded attempt.
 update public.factory_ci_repair_requests set status='ci_failed',updated_at=now()
 where release_run_id=p_source_run_id and repaired_commit=p_candidate_commit and status='awaiting_ci';
 select * into v_existing from public.factory_ci_repair_requests
 where source_run_id=p_source_run_id and original_candidate_commit=p_candidate_commit for update;
 if found then
  return jsonb_build_object('created',false,'reason','already_requested','repair_request_id',v_existing.id,
   'status',v_existing.status,'attempt',v_existing.attempt,'max_attempts',v_existing.max_attempts);
 end if;
 -- A non-code failure is durable evidence, not authority to invent a patch.
 if p_failure_class <> 'code' then
  insert into public.factory_ci_repair_requests(project_id,change_set_id,source_run_id,repository,pr_number,branch,
   original_candidate_commit,execution_generation,attempt,max_attempts,failure_class,failures,status,blocker_reason)
  values(p_project_id,p_change_set_id,p_source_run_id,p_repository,p_pr_number,p_branch,p_candidate_commit,
   p_execution_generation,1,p_max_attempts,p_failure_class,p_failures,'blocked','non_code_ci_failure') returning id into v_request_id;
  update public.factory_runs set status='failed_gate',metadata=metadata||jsonb_build_object('ci_repair_request_id',v_request_id)
   where id=p_source_run_id;
  insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  values(p_project_id,v_run.task_id,p_source_run_id,'system','ci-repair-controller','ci.repair.blocked',
   jsonb_build_object('repair_request_id',v_request_id,'failure_class',p_failure_class,'candidate_commit',p_candidate_commit));
  return jsonb_build_object('created',true,'repair_request_id',v_request_id,'status','blocked','reason','non_code_ci_failure');
 end if;
 select count(*)+1 into v_attempt from public.factory_ci_repair_requests
  where change_set_id=p_change_set_id and failure_class='code';
 if v_attempt>p_max_attempts then
  insert into public.factory_ci_repair_requests(project_id,change_set_id,source_run_id,repository,pr_number,branch,
   original_candidate_commit,execution_generation,attempt,max_attempts,failure_class,failures,status,blocker_reason)
  values(p_project_id,p_change_set_id,p_source_run_id,p_repository,p_pr_number,p_branch,p_candidate_commit,
   p_execution_generation,v_attempt,p_max_attempts,p_failure_class,p_failures,'exhausted','ci_repair_attempts_exhausted') returning id into v_request_id;
  update public.factory_runs set status='failed_gate',metadata=metadata||jsonb_build_object('ci_repair_request_id',v_request_id)
   where id=p_source_run_id;
  update public.factory_change_sets set status='blocked',metadata=metadata||jsonb_build_object('blocker','ci_repair_attempts_exhausted'),updated_at=now()
   where id=p_change_set_id;
  return jsonb_build_object('created',true,'repair_request_id',v_request_id,'status','exhausted','attempt',v_attempt);
 end if;
 v_scopes:=coalesce(v_set.metadata->'integrated_files','[]'::jsonb);
 if jsonb_typeof(v_scopes)<>'array' or jsonb_array_length(v_scopes)=0 then
  insert into public.factory_ci_repair_requests(project_id,change_set_id,source_run_id,repository,pr_number,branch,
   original_candidate_commit,execution_generation,attempt,max_attempts,failure_class,failures,write_scopes,status,blocker_reason)
  values(p_project_id,p_change_set_id,p_source_run_id,p_repository,p_pr_number,p_branch,p_candidate_commit,
   p_execution_generation,v_attempt,p_max_attempts,p_failure_class,p_failures,'[]'::jsonb,'blocked','repair_scope_unknown') returning id into v_request_id;
  update public.factory_runs set status='failed_gate',metadata=metadata||jsonb_build_object('ci_repair_request_id',v_request_id)
   where id=p_source_run_id;
  return jsonb_build_object('created',true,'repair_request_id',v_request_id,'status','blocked','reason','repair_scope_unknown');
 end if;
 v_wave:=v_set.current_wave+1;
 insert into public.factory_tasks(project_id,parent_task_id,external_key,title,description,status,complexity,risk,acceptance_criteria,depends_on,scope_keys)
 values(p_project_id,v_set.root_task_id,'ci-repair-'||replace(p_source_run_id::text,'-','')||'-'||v_attempt,
  'Repair native CI failure - attempt '||v_attempt,
  'Bounded repair from exact native CI evidence. Change only the recorded scopes; do not bypass, disable or weaken tests, CI, permissions or release gates.',
  'queued','medium','{}'::jsonb,jsonb_build_array(jsonb_build_object('ci_failures',p_failures,'candidate_commit',p_candidate_commit)),
  '[]'::jsonb,v_scopes) returning id into v_task_id;
 insert into public.factory_change_set_work_units(change_set_id,task_id,plan_task_key,agent_key,wave,status)
 values(p_change_set_id,v_task_id,'ci-repair-'||v_attempt,'development',v_wave,'pending') returning id into v_unit_id;
 insert into public.factory_ci_repair_requests(project_id,change_set_id,source_run_id,task_id,work_unit_id,repository,pr_number,branch,
  original_candidate_commit,execution_generation,attempt,max_attempts,failure_class,failures,write_scopes,status)
 values(p_project_id,p_change_set_id,p_source_run_id,v_task_id,v_unit_id,p_repository,p_pr_number,p_branch,p_candidate_commit,
  p_execution_generation,v_attempt,p_max_attempts,p_failure_class,p_failures,v_scopes,'queued') returning id into v_request_id;
 update public.factory_change_sets set status='building',current_wave=v_wave,release_run_id=null,attempt_count=0,
  lease_owner=null,lease_expires_at=null,metadata=metadata||jsonb_build_object('ci_repair_request_id',v_request_id,'ci_repair_attempt',v_attempt),updated_at=now()
 where id=p_change_set_id;
 update public.factory_runs set status='repair_pending',metadata=metadata||jsonb_build_object('ci_repair_request_id',v_request_id,'ci_repair_attempt',v_attempt)
 where id=p_source_run_id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(p_project_id,v_task_id,p_source_run_id,'system','ci-repair-controller','ci.repair.queued',
  jsonb_build_object('repair_request_id',v_request_id,'work_unit_id',v_unit_id,'attempt',v_attempt,
   'candidate_commit',p_candidate_commit,'execution_generation',p_execution_generation,'failure_class',p_failure_class));
 return jsonb_build_object('created',true,'repair_request_id',v_request_id,'task_id',v_task_id,'work_unit_id',v_unit_id,
  'attempt',v_attempt,'max_attempts',p_max_attempts,'status','repair_pending');
end;
$f$;
revoke all on function public.factory_enqueue_ci_repair(uuid,uuid,uuid,text,integer,text,text,bigint,text,jsonb,integer)
 from public,anon,authenticated;
grant execute on function public.factory_enqueue_ci_repair(uuid,uuid,uuid,text,integer,text,text,bigint,text,jsonb,integer) to service_role;

create or replace function public.factory_sync_ci_repair_request() returns trigger
language plpgsql security invoker set search_path='' as $f$
begin
 if new.status in ('building','review_ready') and new.candidate_commit is distinct from old.candidate_commit then
  update public.factory_ci_repair_requests r set status='integrated',repaired_commit=new.candidate_commit,
   lease_owner=null,lease_expires_at=null,updated_at=now()
  where r.change_set_id=new.id and r.status in ('queued','running')
    and exists(select 1 from public.factory_change_set_work_units u where u.id=r.work_unit_id and u.status='integrated');
 elsif new.status='ci_pending' and new.release_run_id is not null and new.release_run_id is distinct from old.release_run_id then
  update public.factory_ci_repair_requests r set status='awaiting_ci',release_run_id=new.release_run_id,
   repaired_commit=new.candidate_commit,lease_owner=null,lease_expires_at=null,updated_at=now()
  where r.change_set_id=new.id and r.status='integrated';
 elsif new.status='blocked' then
  update public.factory_ci_repair_requests r set status='failed_gate',blocker_reason=coalesce(new.metadata->>'blocker','change_set_blocked'),
   lease_owner=null,lease_expires_at=null,updated_at=now()
  where r.change_set_id=new.id and r.status in ('queued','running','integrated','awaiting_ci');
 end if;
 return new;
end;
$f$;
drop trigger if exists factory_sync_ci_repair_request on public.factory_change_sets;
create trigger factory_sync_ci_repair_request after update of status,candidate_commit,release_run_id on public.factory_change_sets
 for each row execute function public.factory_sync_ci_repair_request();

create or replace function public.factory_sync_ci_repair_lease() returns trigger
language plpgsql security invoker set search_path='' as $f$
begin
 if new.status='implementing' and new.lease_owner is not null and new.lease_expires_at is not null then
  update public.factory_ci_repair_requests r set status='running',lease_owner=new.lease_owner,
   lease_expires_at=new.lease_expires_at,updated_at=now()
  from public.factory_change_set_work_units u
  where u.run_id=new.id and r.work_unit_id=u.id and r.status='queued';
 elsif new.status='preview_ready' and new.candidate_commit is not null then
  update public.factory_ci_repair_requests r set status='passed',updated_at=now()
  where r.release_run_id=new.id and r.repaired_commit=new.candidate_commit and r.status='awaiting_ci';
 end if;
 return new;
end;
$f$;
drop trigger if exists factory_sync_ci_repair_lease on public.factory_runs;
create trigger factory_sync_ci_repair_lease after update of status,lease_owner,lease_expires_at on public.factory_runs
 for each row execute function public.factory_sync_ci_repair_lease();

create or replace function public.factory_record_ci_repair_result(
 p_release_run_id uuid,p_candidate_commit text,p_status text
) returns jsonb language plpgsql security invoker set search_path='' as $f$
declare v_request public.factory_ci_repair_requests%rowtype; v_generation bigint; v_state text; v_run public.factory_runs%rowtype;
begin
 if p_release_run_id is null or p_candidate_commit !~ '^[0-9a-f]{40}$' or p_status not in ('passed','failed') then
  raise exception 'invalid CI repair result' using errcode='PT400';
 end if;
 select * into v_request from public.factory_ci_repair_requests
 where release_run_id=p_release_run_id and repaired_commit=p_candidate_commit and status='awaiting_ci' for update;
 if not found then return jsonb_build_object('updated',false,'reason','no_awaiting_ci_repair'); end if;
 select r.* into v_run from public.factory_runs r
 join public.factory_tasks t on t.id=r.task_id join public.factory_project_execution_controls c on c.project_id=t.project_id
 where r.id=p_release_run_id for share of r,c;
 select c.state,c.generation into v_state,v_generation
 from public.factory_project_execution_controls c
 join public.factory_tasks t on t.project_id=c.project_id
 where t.id=v_run.task_id for share of c;
 if not found or v_run.candidate_commit is distinct from p_candidate_commit or v_state is distinct from 'running'
    or v_generation is distinct from v_request.execution_generation
    or v_run.metadata->>'execution_generation' is distinct from v_request.execution_generation::text then
  raise exception 'CI repair result execution epoch revoked' using errcode='PT409';
 end if;
 update public.factory_ci_repair_requests set status=case when p_status='passed' then 'passed' else 'ci_failed' end,
  updated_at=now() where id=v_request.id;
 return jsonb_build_object('updated',true,'repair_request_id',v_request.id,'status',p_status);
end;
$f$;
revoke all on function public.factory_record_ci_repair_result(uuid,text,text) from public,anon,authenticated;
grant execute on function public.factory_record_ci_repair_result(uuid,text,text) to service_role;

commit;
