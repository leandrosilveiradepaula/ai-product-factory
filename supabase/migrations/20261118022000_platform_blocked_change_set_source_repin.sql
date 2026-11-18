-- Platform-only source repin for unimplemented, blocked Change Sets.
-- Read-only external GitHub compare/main/branch proof is supplied by a trusted
-- server-side operator. Does not infer authority from the model's text.
-- Migration is INERT until separate production approval and human merge.
create or replace function public.factory_repin_blocked_platform_source_v1(
  p_change_set_id uuid,
  p_old_sha text,
  p_new_sha text,
  p_evidence jsonb,
  p_reason text
) returns jsonb language plpgsql security invoker set search_path='' as $function$
declare
  v_set public.factory_change_sets%rowtype;
  v_unit public.factory_change_set_work_units%rowtype;
  v_run public.factory_runs%rowtype;
  v_task public.factory_tasks%rowtype;
  v_parent public.factory_tasks%rowtype;
  v_project public.factory_projects%rowtype;
  v_state text;
  v_generation bigint;
  v_paths jsonb;
  v_path text;
  v_scope text;
  v_ahead int;
  v_count int;
begin
  if p_old_sha !~ '^[0-9a-f]{40}$'
     or p_new_sha !~ '^[0-9a-f]{40}$'
     or p_old_sha=p_new_sha
     or nullif(btrim(p_reason),'') is null
     or length(p_reason)>1000
     or jsonb_typeof(p_evidence) is distinct from 'object'
     or p_evidence->>'old_sha' is distinct from p_old_sha
     or p_evidence->>'new_sha' is distinct from p_new_sha
     or p_evidence->>'compare_status' is distinct from 'ahead'
     or p_evidence->>'branch' is distinct from 'main'
     or p_evidence->>'behind_by' is distinct from '0'
     or coalesce(p_evidence->>'ahead_by','') !~ '^[1-9][0-9]*$'
  then
    raise exception 'platform repin requires exact verified ancestry evidence'
      using errcode='PT409';
  end if;
  v_ahead:=(p_evidence->>'ahead_by')::int;
  v_paths:=p_evidence->'changed_paths';
  if v_ahead>30
     or jsonb_typeof(v_paths) is distinct from 'array'
     or jsonb_array_length(v_paths) not between 1 and 100
     or coalesce(p_evidence->>'file_count','') !~ '^[1-9][0-9]*$'
     or (p_evidence->>'file_count')::int <> jsonb_array_length(v_paths)
  then
    raise exception 'platform repin source diff is not bounded'
      using errcode='PT409';
  end if;
  for v_path in select jsonb_array_elements_text(v_paths) loop
    if v_path !~ '^[A-Za-z0-9_.\-/]+$'
       or length(v_path)>300
       or v_path like '%..%'
       or v_path like '.env%'
       or v_path like 'apps/console/%'
       or v_path in ('AGENTS.md','PROJECT_PLAN.md','MEMORY.md',
                     'docs/STATUS.md','docs/OPERATIONS.md',
                     'docs/AUTH_ACTIVATION_READINESS.md')
    then
      raise exception 'platform repin diff includes protected or invalid path'
        using errcode='PT409';
    end if;
  end loop;
  select c.* into v_set from public.factory_change_sets c
    where c.id=p_change_set_id for update;
  if not found
     or v_set.status is distinct from 'blocked'
     or v_set.source_commit is distinct from p_old_sha
     or v_set.candidate_commit is distinct from p_old_sha
     or v_set.lease_owner is not null
     or v_set.lease_expires_at is not null
     or v_set.release_run_id is not null
     or v_set.metadata#>>'{blocker,type}' is distinct from 'implementation_preflight_error'
     or v_set.metadata#>>'{blocker,reason}' is distinct from
        'PermissionError: frozen Change Set source differs from verified candidate'
     or v_set.metadata ? 'platform_source_repin'
  then
    raise exception 'platform Change Set is not eligible for source repin'
      using errcode='PT409';
  end if;
  select p.* into v_project from public.factory_projects p
    where p.id=v_set.project_id and p.is_active=true for share;
  if not found
     or v_project.project_kind is distinct from 'platform'
     or v_project.repository is distinct from p_evidence->>'repository'
     or v_project.manifest#>>'{continuation_request,source}' is distinct from 'factory-console'
  then
    raise exception 'platform project identity mismatch'
      using errcode='PT409';
  end if;
  select c.state,c.generation into v_state,v_generation
    from public.factory_project_execution_controls c
    where c.project_id=v_project.id for update;
  if v_state is distinct from 'running' or v_generation is null then
    raise exception 'platform execution control is not active'
      using errcode='PT409';
  end if;
  select count(*) into v_count from public.factory_change_set_work_units u
    where u.change_set_id=p_change_set_id;
  if v_count<>1 then
    raise exception 'platform source repin requires one unimplemented work unit'
      using errcode='PT409';
  end if;
  select u.* into v_unit from public.factory_change_set_work_units u
    where u.change_set_id=p_change_set_id and u.status='blocked' for update;
  if not found or v_unit.base_commit is distinct from p_old_sha
     or v_unit.output_commit is not null
     or v_unit.branch_name is distinct from p_evidence->>'work_branch'
     or p_evidence->>'work_branch_sha' is distinct from p_new_sha
     or v_set.metadata#>>'{blocker,work_unit_id}' is distinct from v_unit.id::text
     or v_set.metadata#>>'{blocker,run_id}' is distinct from v_unit.run_id::text
  then
    raise exception 'platform work unit not eligible for source repin'
      using errcode='PT409';
  end if;
  select r.* into v_run from public.factory_runs r
    where r.id=v_unit.run_id for update;
  select t.* into v_task from public.factory_tasks t
    where t.id=v_unit.task_id for update;
  if v_run.status is distinct from 'blocked'
     or v_task.status is distinct from 'blocked'
     or v_run.task_id is distinct from v_task.id
     or v_run.attempt_count>2
     or v_run.lease_owner is not null
     or v_run.lease_expires_at is not null
     or v_run.candidate_commit is not null
     or v_run.last_error is distinct from v_set.metadata#>>'{blocker,reason}'
     or v_run.metadata->>'execution_generation' is distinct from v_generation::text
     or v_task.project_id is distinct from v_project.id
     or v_task.parent_task_id is null
     or jsonb_typeof(v_task.scope_keys) is distinct from 'array'
  then
    raise exception 'platform run/task source repin is unsafe'
      using errcode='PT409';
  end if;
  select t.* into v_parent from public.factory_tasks t
    where t.id=v_task.parent_task_id and t.project_id=v_project.id;
  if not found or v_parent.status is distinct from 'completed'
     or not exists (
       select 1 from public.factory_runs planning
       where planning.task_id=v_parent.id and planning.status='completed'
         and planning.metadata->>'source'='factory-console'
         and planning.metadata#>>'{stage_evidence,planning,status}'='completed'
     )
  then
    raise exception 'platform repin has no completed Console planning provenance'
      using errcode='PT409';
  end if;
  -- A source file changed between the approved plan and latest main must
  -- never become an implicit authority to rewrite it.
  for v_path in select jsonb_array_elements_text(v_paths) loop
    for v_scope in select jsonb_array_elements_text(v_task.scope_keys) loop
      if v_scope=v_path
         or (right(v_scope,3)='/**'
             and v_path like left(v_scope,length(v_scope)-3)||'/%')
      then
        raise exception 'platform repin diff intersects authorized work scope'
          using errcode='PT409';
      end if;
    end loop;
  end loop;
  if exists(
    select 1 from public.factory_audit_events ae
     where ae.run_id=v_run.id and ae.event_type='change_set.platform_source_repinned'
  ) then
    raise exception 'platform source repin is already recorded'
      using errcode='PT409';
  end if;
  update public.factory_change_sets set
    source_commit=p_new_sha,candidate_commit=p_new_sha,
    status='building',lease_owner=null,lease_expires_at=null,updated_at=now(),
    metadata=(metadata-'blocker')||
      jsonb_build_object('platform_source_repin',
        p_evidence||jsonb_build_object('reason',p_reason,'at',now()))
    where id=v_set.id and status='blocked';
  if not found then raise exception 'Change Set CAS failed' using errcode='PT409'; end if;
  update public.factory_change_set_work_units set
    base_commit=p_new_sha,status='queued',updated_at=now()
    where id=v_unit.id and status='blocked';
  if not found then raise exception 'work unit CAS failed' using errcode='PT409'; end if;
  update public.factory_runs set status='queued',last_error=null,
    source_commit=p_new_sha,candidate_commit=null,
    metadata=metadata||jsonb_build_object('platform_source_repin',
      jsonb_build_object('old_sha',p_old_sha,'new_sha',p_new_sha,'at',now()))
    where id=v_run.id and status='blocked';
  if not found then raise exception 'run CAS failed' using errcode='PT409'; end if;
  update public.factory_tasks set status='queued_execution',updated_at=now()
    where id=v_task.id and status='blocked';
  if not found then raise exception 'task CAS failed' using errcode='PT409'; end if;
  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  ) values (
    v_project.id,v_task.id,v_run.id,'system','platform-source-repin',
    'change_set.platform_source_repinned',
    p_evidence||jsonb_build_object(
      'change_set_id',v_set.id,'work_unit_id',v_unit.id,
      'old_sha',p_old_sha,'new_sha',p_new_sha,'reason',p_reason)
  );
  return jsonb_build_object(
    'status','requeued','run_id',v_run.id,'change_set_id',v_set.id,
    'source_commit',p_new_sha,'work_branch',v_unit.branch_name
  );
end;
$function$;
revoke all on function public.factory_repin_blocked_platform_source_v1(uuid,text,text,jsonb,text)
  from public,anon,authenticated;
grant execute on function public.factory_repin_blocked_platform_source_v1(uuid,text,text,jsonb,text)
  to service_role;
