-- Only attested native test failure can add one scoped test in a new Work Unit.
-- A separate human production gate is required before installing this RPC.
begin;
CREATE OR REPLACE FUNCTION public.factory_enqueue_ci_repair_verified_test_scope_v1(p_source_run_id uuid, p_project_id uuid, p_change_set_id uuid, p_repository text, p_pr_number integer, p_branch text, p_candidate_commit text, p_execution_generation bigint, p_failure_class text, p_failures jsonb, p_max_attempts integer DEFAULT 2)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
 v_run public.factory_runs%rowtype; v_set public.factory_change_sets%rowtype;
 v_project_id uuid; v_generation bigint; v_state text; v_existing public.factory_ci_repair_requests%rowtype;
 v_attempt integer; v_task_id uuid; v_unit_id uuid; v_request_id uuid; v_wave integer; v_scopes jsonb; v_receipt jsonb; v_scope_reason text; v_scope_count integer;
 v_test_path text; v_source_path text; v_receipt_tail text; v_previous_receipt text;
 v_parts text[]; v_e integer; v_a integer; v_failure jsonb; v_count integer:=0;
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
 -- Serialize retries on the source run.  An accepted first request already
 -- transitioned its run to repair_pending/failed_gate and its Change Set
 -- away from ci_pending; inspect its durable receipt before requiring the
 -- NEW-request state. Never materialize a second work unit for the same SHA.
 select * into v_existing from public.factory_ci_repair_requests
 where source_run_id=p_source_run_id and original_candidate_commit=p_candidate_commit for update;
 if found then
  if v_existing.project_id is distinct from p_project_id
     or v_existing.change_set_id is distinct from p_change_set_id
     or v_existing.repository is distinct from p_repository
     or v_existing.pr_number is distinct from p_pr_number
     or v_existing.branch is distinct from p_branch
     or v_existing.execution_generation is distinct from p_execution_generation
     or v_existing.failure_class is distinct from p_failure_class
     or v_existing.failures is distinct from p_failures
     or v_existing.max_attempts is distinct from p_max_attempts then
   raise exception 'CI repair replay identity drift' using errcode='PT409';
  end if;
  return jsonb_build_object('created',false,'reason','already_requested',
   'repair_request_id',v_existing.id,'status',v_existing.status,
   'attempt',v_existing.attempt,'max_attempts',v_existing.max_attempts);
 end if;
 if v_run.status is distinct from 'ci_pending' then
  raise exception 'CI repair source identity or epoch revoked' using errcode='PT409';
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
 -- Every integrated Work Unit is evidence of files actually committed
 -- into the candidate. metadata.integrated_files only lists the FINAL wave.
 -- Use an exact, bounded, sorted union; never trust metadata/model scopes.
 v_scope_reason:=null;
 v_scopes:='[]'::jsonb;
 if not exists(
  select 1 from public.factory_change_set_work_units u where u.change_set_id=p_change_set_id
 ) then
  v_scope_reason:='repair_scope_unknown';
 elsif exists(
  select 1 from public.factory_change_set_work_units u where u.change_set_id=p_change_set_id
   and (u.status is distinct from 'integrated' or u.wave<1 or u.wave>v_set.current_wave
    or (case when jsonb_typeof(u.changed_files)='array'
         then jsonb_array_length(u.changed_files) between 1 and 500 else false end) is not true)
 ) then
  v_scope_reason:='repair_scope_inconsistent';
 elsif exists(
  select 1 from public.factory_change_set_work_units u
  cross join lateral jsonb_array_elements(u.changed_files) f(value)
  where u.change_set_id=p_change_set_id
   and (jsonb_typeof(f.value) is distinct from 'string'
    or length(f.value#>>'{}') not between 1 and 1024
    or f.value#>>'{}' in ('.','..')
    or f.value#>>'{}' like '/%'
    or position(chr(92) in (f.value#>>'{}'))>0
    or (f.value#>>'{}') ~ '[[:cntrl:]]'
    or (f.value#>>'{}') like '../%' or (f.value#>>'{}') like '%/../%'
    or (f.value#>>'{}') like './%' or (f.value#>>'{}') like '%/./%'
    or (f.value#>>'{}') like '%//%' or (f.value#>>'{}') like '%/..'
    or (f.value#>>'{}') like '%/.')
 ) then
  v_scope_reason:='repair_scope_unsafe_path';
 else
  select count(*) into v_scope_count
  from (
   select distinct f.path from public.factory_change_set_work_units u
   cross join lateral jsonb_array_elements_text(u.changed_files) f(path)
   where u.change_set_id=p_change_set_id
  ) paths;
  if v_scope_count<1 then
   v_scope_reason:='repair_scope_unknown';
  elsif v_scope_count>500 then
   v_scope_reason:='repair_scope_exceeds_limit';
  else
   select jsonb_agg(paths.path order by paths.path) into v_scopes
   from (
    select distinct f.path from public.factory_change_set_work_units u
    cross join lateral jsonb_array_elements_text(u.changed_files) f(path)
    where u.change_set_id=p_change_set_id
   ) paths;
  end if;
 end if;
 -- Service-role-only, new assignment for precisely one CI-attested test.
 -- Original integrated write scopes remain auditable and unchanged.
 if v_scope_reason is null then
  if not exists (select 1 from public.factory_projects pr
      where pr.id=p_project_id and pr.project_kind='existing'
        and pr.is_active=true and pr.repository=p_repository) then
    raise exception 'test scope requires current existing project' using errcode='PT409';
  end if;
  if jsonb_array_length(p_failures)>4 then
    raise exception 'unbounded native test jobs' using errcode='PT400';
  end if;
  for v_failure in select value from jsonb_array_elements(p_failures) loop
    if v_failure->>'name' is distinct from 'native-ci/tests'
       or v_failure->>'conclusion' is distinct from 'failure'
       or v_failure->>'failure_class' is distinct from 'code'
       or v_failure->>'summary' not like
         'Verified failed GitHub Actions step (run and attempt bound); Verified native Vitest count: %'
       or v_failure->>'details_url' !~
         ('^https://github[.]com/'||replace(p_repository,'/','\/')
          ||'/actions/runs/[1-9][0-9]*/job/[1-9][0-9]*$') then
      raise exception 'native test assertion evidence is not certified' using errcode='PT400';
    end if;
    v_receipt_tail:=split_part(v_failure->>'summary','Verified native Vitest count: ',2);
    v_parts:=regexp_match(v_receipt_tail,
       '^test=([A-Za-z0-9_./()-]+) source=([A-Za-z0-9_./()-]+) expected=([0-9]{1,3}) actual=([0-9]{1,3})$');
    if v_parts is null or array_length(v_parts,1)<>4
       or (v_previous_receipt is not null and v_previous_receipt<>v_receipt_tail) then
      raise exception 'conflicting or malformed native test proof' using errcode='PT400';
    end if;
    v_previous_receipt:=v_receipt_tail;
    v_test_path:=v_parts[1];
    v_source_path:=v_parts[2];
    v_e:=v_parts[3]::integer;
    v_a:=v_parts[4]::integer;
    v_count:=v_count+1;
  end loop;
  if v_count<1
     or v_test_path !~ '^(src|test|tests|app|apps|packages)/[A-Za-z0-9_./()-]+\.(test|spec)\.tsx?$'
     or v_source_path !~ '^(src|app|apps|packages)/[A-Za-z0-9_./()-]+\.tsx?$'
     or v_test_path=v_source_path
     or position('..' in v_test_path)>0
     or position('..' in v_source_path)>0
     or position('//' in v_test_path)>0
     or position('//' in v_source_path)>0
     or v_e>100 or v_a<>v_e+1
     or not v_scopes ? v_source_path
     or jsonb_array_length(v_scopes)>=500 then
    raise exception 'test scope not justified by integrated source' using errcode='PT400';
  end if;
  if not v_scopes ? v_test_path then
    select jsonb_agg(q.path order by q.path) into v_scopes
    from (
       select distinct f.value as path from jsonb_array_elements_text(v_scopes) f
       union select v_test_path
    ) q;
  end if;
 end if;
 if v_scope_reason is not null then
  insert into public.factory_ci_repair_requests(project_id,change_set_id,source_run_id,repository,pr_number,branch,
   original_candidate_commit,execution_generation,attempt,max_attempts,failure_class,failures,write_scopes,status,blocker_reason)
  values(p_project_id,p_change_set_id,p_source_run_id,p_repository,p_pr_number,p_branch,p_candidate_commit,
   p_execution_generation,v_attempt,p_max_attempts,p_failure_class,p_failures,'[]'::jsonb,'blocked',v_scope_reason)
  returning id into v_request_id;
  update public.factory_runs set status='failed_gate',
   metadata=metadata||jsonb_build_object('ci_repair_request_id',v_request_id)
   where id=p_source_run_id;
  update public.factory_change_sets set status='blocked',
   metadata=metadata||jsonb_build_object('blocker',v_scope_reason),updated_at=now()
   where id=p_change_set_id;
  insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  values(p_project_id,v_run.task_id,p_source_run_id,'system','ci-repair-controller','ci.repair.blocked',
   jsonb_build_object('repair_request_id',v_request_id,'reason',v_scope_reason,'candidate_commit',p_candidate_commit));
  return jsonb_build_object('created',true,'repair_request_id',v_request_id,
   'status','blocked','reason',v_scope_reason);
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
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values (p_project_id,v_task_id,p_source_run_id,'system','ci-repair-test-scope',
 'ci.repair.verified_test_scope',jsonb_build_object(
  'repair_request_id',v_request_id,'change_set_id',p_change_set_id,
  'test_path',v_test_path,'source_path',v_source_path,
  'previous_expected',v_e,'actual',v_a,'candidate_sha',p_candidate_commit,
  'generation',p_execution_generation,'write_scopes',v_scopes,
  'release_authorized',false,'model_calls',0));
 return jsonb_build_object('created',true,'repair_request_id',v_request_id,'task_id',v_task_id,'work_unit_id',v_unit_id,
  'attempt',v_attempt,'max_attempts',p_max_attempts,'status','repair_pending');
end;
$function$;

revoke all on function public.factory_enqueue_ci_repair_verified_test_scope_v1(uuid,uuid,uuid,text,integer,text,text,bigint,text,jsonb,integer) from public,anon,authenticated;
grant execute on function public.factory_enqueue_ci_repair_verified_test_scope_v1(uuid,uuid,uuid,text,integer,text,text,bigint,text,jsonb,integer) to service_role;
commit;
