-- Candidate only. Do not apply in production without a separate human migration gate.
-- New atomic RPCs supersede the legacy unfenced metadata mutation endpoints.
begin;

-- The same checkpoint now guards all three legitimate integration phases:
-- integrating (live lease), review_ready (durable completion receipt), and
-- ci_pending (exact release request and CI run). Pauses revoke every phase.
create or replace function public.factory_assert_change_set_integration_epoch(
 p_change_set_id uuid,p_project_id uuid,p_generation bigint,p_worker_id text,p_wave integer
) returns void language plpgsql security invoker set search_path='' as $f$
declare
 v_state text;v_generation bigint;v_set record;v_receipt jsonb;v_request jsonb;v_run record;
begin
 if p_change_set_id is null or p_project_id is null or p_generation is null or p_generation<1
    or nullif(btrim(p_worker_id),'') is null or p_wave is null or p_wave<1 then
  raise exception 'invalid integration checkpoint' using errcode='PT400';
 end if;
 select state,generation into v_state,v_generation
 from public.factory_project_execution_controls where project_id=p_project_id for share;
 if not found or v_state is distinct from 'running' or v_generation is distinct from p_generation then
  raise exception 'integration epoch revoked' using errcode='PT409';
 end if;
 select s.project_id,s.status,s.current_wave,s.lease_owner,s.lease_expires_at,
        s.candidate_commit,s.integration_branch,s.release_run_id,s.metadata
 into v_set from public.factory_change_sets s where s.id=p_change_set_id for share;
 if not found or v_set.project_id is distinct from p_project_id
    or v_set.current_wave is distinct from p_wave then
  raise exception 'integration checkpoint identity revoked' using errcode='PT409';
 end if;
 if v_set.status='integrating' then
  if v_set.lease_owner is distinct from p_worker_id
      or v_set.lease_expires_at is null or v_set.lease_expires_at<=clock_timestamp() then
   raise exception 'integration worker lease revoked' using errcode='PT409';
  end if;
  return;
 end if;
 v_receipt:=jsonb_build_object(
  'project_id',p_project_id,'generation',p_generation,'worker_id',p_worker_id,
  'wave',p_wave,'candidate_commit',v_set.candidate_commit);
 if v_set.metadata->'integration_epoch_receipt' is distinct from v_receipt
    or nullif(btrim(v_set.candidate_commit),'') is null then
  raise exception 'integration completion receipt revoked' using errcode='PT409';
 end if;
 if v_set.status='review_ready' then return; end if;
 if v_set.status='ci_pending' and v_set.release_run_id is not null then
  v_request:=v_set.metadata->'integration_release_request';
  if jsonb_typeof(v_request) is distinct from 'object'
     or v_request->>'candidate_commit' is distinct from v_set.candidate_commit
     or v_request->>'branch' is distinct from v_set.integration_branch then
   raise exception 'integration release checkpoint revoked' using errcode='PT409';
  end if;
  select status,candidate_commit,branch_name into v_run
  from public.factory_runs where id=v_set.release_run_id;
  if found and v_run.status='ci_pending'
     and v_run.candidate_commit=v_set.candidate_commit
     and v_run.branch_name=v_set.integration_branch then
   return;
  end if;
 end if;
 raise exception 'integration checkpoint status revoked' using errcode='PT409';
end;
$f$;

create or replace function public.factory_complete_change_set_integration_epoch(
 p_change_set_id uuid,p_project_id uuid,p_generation bigint,p_worker_id text,
 p_wave integer,p_candidate_commit text,p_changed_files jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $f$
declare
 v_state text;v_generation bigint;
 v_set public.factory_change_sets%rowtype;
 v_count integer;v_updated integer;v_repairs integer;v_next_wave integer;
 v_expected text[];v_provided text[];v_status text;
 v_attempts jsonb;v_metadata jsonb;v_receipt jsonb;
begin
 if p_change_set_id is null or p_project_id is null or p_generation is null or p_generation<1
    or nullif(btrim(p_worker_id),'') is null or p_wave is null or p_wave<1
    or nullif(btrim(p_candidate_commit),'') is null
    or length(p_candidate_commit)>128 or p_candidate_commit ~ '[[:space:][:cntrl:]]'
    or p_changed_files is null or jsonb_typeof(p_changed_files)<>'array'
    or jsonb_array_length(p_changed_files) not between 1 and 500 then
  raise exception 'invalid integration completion request' using errcode='PT400';
 end if;
 if exists(select 1 from jsonb_array_elements(p_changed_files) f
            where jsonb_typeof(f.value)<>'string') then
  raise exception 'integration changed files must be strings' using errcode='PT400';
 end if;
 -- Always acquire the project control lock before the Change Set row lock.
 -- An operator pause/stop cannot race between this check and the writes.
 select state,generation into v_state,v_generation
 from public.factory_project_execution_controls where project_id=p_project_id for share;
 if not found or v_state is distinct from 'running' or v_generation is distinct from p_generation then
  raise exception 'integration epoch revoked' using errcode='PT409';
 end if;
 select * into v_set from public.factory_change_sets
 where id=p_change_set_id for update;
 if not found or v_set.project_id is distinct from p_project_id
    or v_set.status is distinct from 'integrating'
    or v_set.current_wave is distinct from p_wave
    or v_set.lease_owner is distinct from p_worker_id
    or v_set.lease_expires_at is null or v_set.lease_expires_at<=clock_timestamp()
    or v_set.attempt_count<1 then
  raise exception 'integration completion lease revoked' using errcode='PT409';
 end if;
 if p_candidate_commit=v_set.candidate_commit then
  raise exception 'integration candidate must advance' using errcode='PT409';
 end if;
 select count(*) into v_count
 from public.factory_change_set_work_units u
 where u.change_set_id=v_set.id and u.wave=v_set.current_wave;
 if v_count<1 or v_count>100 or exists(
  select 1 from public.factory_change_set_work_units u
  where u.change_set_id=v_set.id and u.wave=v_set.current_wave
    and (u.status is distinct from 'completed'
         or u.base_commit is distinct from v_set.candidate_commit
         or nullif(btrim(u.output_commit),'') is null
         or u.changed_files is null or jsonb_typeof(u.changed_files)<>'array')
 ) then
  raise exception 'integration work unit contract revoked' using errcode='PT409';
 end if;
 select array_agg(f.path order by f.path) into v_expected
 from public.factory_change_set_work_units u
 cross join lateral jsonb_array_elements_text(u.changed_files) f(path)
 where u.change_set_id=v_set.id and u.wave=v_set.current_wave;
 select array_agg(f.path order by f.path) into v_provided
 from jsonb_array_elements_text(p_changed_files) f(path);
 if v_expected is null or v_expected is distinct from v_provided
    or cardinality(v_expected)>(select count(distinct f.path) from unnest(v_expected) f(path))
    or exists(select 1 from unnest(v_expected) f(path)
       where length(f.path)>1024 or f.path='' or f.path like '/%'
         or position(chr(92) in f.path)>0 or f.path ~ '[[:cntrl:]]'
         or f.path like '../%' or f.path like '%/../%'
         or f.path like './%' or f.path like '%/./%'
         or f.path like '%//' or f.path like '%/..' or f.path like '%/.')
 then
  raise exception 'integration changed file evidence mismatch' using errcode='PT409';
 end if;
 select min(u.wave) into v_next_wave
 from public.factory_change_set_work_units u
 where u.change_set_id=v_set.id and u.status='pending';
 if v_next_wave is not null and v_next_wave<=v_set.current_wave then
  raise exception 'integration cannot move backwards' using errcode='PT409';
 end if;
 v_attempts:=coalesce(v_set.metadata->'integration_attempts_by_wave','{}'::jsonb);
 if jsonb_typeof(v_attempts)<>'object' then
  raise exception 'invalid integration attempt history' using errcode='PT409';
 end if;
 v_attempts:=v_attempts||jsonb_build_object(v_set.current_wave::text,v_set.attempt_count);
 v_metadata:=jsonb_set(coalesce(v_set.metadata,'{}'::jsonb)-'integration_epoch_receipt',
     '{integration_attempts_by_wave}',v_attempts,true);

 update public.factory_change_set_work_units set status='integrated',updated_at=now()
 where change_set_id=v_set.id and wave=v_set.current_wave and status='completed';
 get diagnostics v_updated=row_count;
 if v_updated<>v_count then
  raise exception 'integration work unit update mismatch' using errcode='PT409';
 end if;
 update public.factory_tasks t set status='integrated',updated_at=now()
 where exists(select 1 from public.factory_change_set_work_units u
   where u.change_set_id=v_set.id and u.wave=v_set.current_wave
     and u.task_id=t.id and u.status='integrated');
 -- Repair-job completion belongs to this same transaction and epoch.
 update public.factory_repair_jobs r
 set status='integrated',candidate_commit=p_candidate_commit,updated_at=now()
 from public.factory_change_set_work_units u
 where r.work_unit_id=u.id and r.change_set_id=v_set.id
   and u.wave=v_set.current_wave and r.status in ('queued','running');
 get diagnostics v_repairs=row_count;

 if v_next_wave is null then
  v_status:='review_ready';
  v_receipt:=jsonb_build_object(
   'project_id',p_project_id,'generation',p_generation,'worker_id',p_worker_id,
   'wave',p_wave,'candidate_commit',p_candidate_commit);
  update public.factory_change_sets
  set status=v_status,candidate_commit=p_candidate_commit,
      lease_owner=null,lease_expires_at=null,
      metadata=v_metadata||jsonb_build_object(
       'integrated_files',p_changed_files,'integration_epoch_receipt',v_receipt),
      updated_at=now()
  where id=v_set.id;
 else
  v_status:='building';
  update public.factory_change_sets
  set status=v_status,candidate_commit=p_candidate_commit,
      current_wave=v_next_wave,attempt_count=0,lease_owner=null,lease_expires_at=null,
      metadata=v_metadata,updated_at=now()
  where id=v_set.id;
 end if;
 return jsonb_build_object(
  'change_set_id',v_set.id,'status',v_status,'candidate_commit',p_candidate_commit,
  'current_wave',coalesce(v_next_wave,v_set.current_wave),'repair_jobs_integrated',v_repairs);
end;
$f$;

create or replace function public.factory_prepare_change_set_release_epoch(
 p_change_set_id uuid,p_project_id uuid,p_generation bigint,p_worker_id text,
 p_wave integer,p_issue_number integer,p_issue_url text,p_pr_number integer,
 p_candidate_commit text,p_branch text
) returns jsonb language plpgsql security invoker set search_path='' as $f$
declare
 v_state text;v_generation bigint;v_repository text;
 v_set public.factory_change_sets%rowtype;
 v_run_id uuid;v_run_status text;v_run_candidate text;v_run_branch text;
 v_receipt jsonb;v_request jsonb;
begin
 if p_change_set_id is null or p_project_id is null or p_generation is null or p_generation<1
    or nullif(btrim(p_worker_id),'') is null or p_wave is null or p_wave<1
    or p_issue_number is null or p_issue_number<1
    or p_pr_number is null or p_pr_number<1
    or nullif(btrim(p_candidate_commit),'') is null or nullif(btrim(p_branch),'') is null
    or length(p_candidate_commit)>128 or length(p_branch)>200 then
  raise exception 'invalid integration release request' using errcode='PT400';
 end if;
 select c.state,c.generation,p.repository into v_state,v_generation,v_repository
 from public.factory_project_execution_controls c
 join public.factory_projects p on p.id=c.project_id
 where c.project_id=p_project_id for share of c;
 if not found or v_state is distinct from 'running' or v_generation is distinct from p_generation then
  raise exception 'integration release epoch revoked' using errcode='PT409';
 end if;
 select * into v_set from public.factory_change_sets
 where id=p_change_set_id for update;
 if not found or v_set.project_id is distinct from p_project_id
    or v_set.current_wave is distinct from p_wave
    or v_set.candidate_commit is distinct from p_candidate_commit
    or v_set.integration_branch is distinct from p_branch then
  raise exception 'integration release candidate revoked' using errcode='PT409';
 end if;
 v_receipt:=jsonb_build_object(
  'project_id',p_project_id,'generation',p_generation,'worker_id',p_worker_id,
  'wave',p_wave,'candidate_commit',p_candidate_commit);
 if v_set.metadata->'integration_epoch_receipt' is distinct from v_receipt then
  raise exception 'integration release receipt revoked' using errcode='PT409';
 end if;
 if p_issue_url is distinct from
    ('https://github.com/'||v_repository||'/issues/'||p_issue_number::text) then
  raise exception 'integration issue does not belong to project repository' using errcode='PT409';
 end if;
 v_request:=jsonb_build_object(
  'issue_number',p_issue_number,'issue_url',p_issue_url,'pr_number',p_pr_number,
  'candidate_commit',p_candidate_commit,'branch',p_branch);
 -- Exact retries are idempotent: never allocate a second release run or cost record.
 if v_set.status='ci_pending' and v_set.release_run_id is not null
    and v_set.metadata->'integration_release_request' = v_request then
  select status,candidate_commit,branch_name into v_run_status,v_run_candidate,v_run_branch
  from public.factory_runs where id=v_set.release_run_id;
  if found and v_run_status='ci_pending' and v_run_candidate=p_candidate_commit
       and v_run_branch=p_branch then
   return jsonb_build_object('change_set_id',v_set.id,
    'release_run_id',v_set.release_run_id,'status','ci_pending','idempotent',true);
  end if;
 end if;
 if v_set.status is distinct from 'review_ready' or v_set.release_run_id is not null then
  raise exception 'integration release is not review ready' using errcode='PT409';
 end if;
 insert into public.factory_runs(task_id,status,candidate_commit,branch_name,metadata)
 values(v_set.root_task_id,'ci_pending',p_candidate_commit,p_branch,
  jsonb_build_object('source','change-set','change_set_id',v_set.id,
   'github_issue',jsonb_build_object('number',p_issue_number,'url',p_issue_url),
   'human_gate_required',false))
 returning id into v_run_id;
 insert into public.factory_tool_usage(run_id,tool_family,operation,usage_units,estimated_cost,metadata)
 values(v_run_id,'github','create_pr',1,0,
  jsonb_build_object('pr',p_pr_number,'head_sha',p_candidate_commit,'change_set_id',v_set.id));
 update public.factory_change_sets
 set status='ci_pending',release_run_id=v_run_id,
     metadata=coalesce(v_set.metadata,'{}'::jsonb)
       ||jsonb_build_object('integration_release_request',v_request),
     updated_at=now()
 where id=v_set.id;
 insert into public.factory_audit_events(
  project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_set.project_id,v_set.root_task_id,v_run_id,
  'system','change-set-integrator','change_set.release_candidate.created',
  jsonb_build_object('change_set_id',v_set.id,'pr',p_pr_number,
   'candidate_commit',p_candidate_commit,'branch',p_branch,
   'execution_generation',p_generation));
 return jsonb_build_object('change_set_id',v_set.id,'release_run_id',v_run_id,
  'status','ci_pending','idempotent',false);
end;
$f$;

-- Eliminate the runtime's old ungated mutations. Old callers fail closed;
-- only the new epoch-capability RPCs are callable by service_role.
revoke all on function public.factory_complete_change_set_integration(uuid,text,jsonb)
 from public,anon,authenticated,service_role;
revoke all on function public.factory_mark_repair_wave_integrated(uuid,integer,text)
 from public,anon,authenticated,service_role;
revoke all on function public.factory_prepare_change_set_release(uuid,integer,text,integer,text,text)
 from public,anon,authenticated,service_role;
revoke all on function public.factory_complete_change_set_integration_epoch(uuid,uuid,bigint,text,integer,text,jsonb)
 from public,anon,authenticated;
grant execute on function public.factory_complete_change_set_integration_epoch(uuid,uuid,bigint,text,integer,text,jsonb)
 to service_role;
revoke all on function public.factory_prepare_change_set_release_epoch(uuid,uuid,bigint,text,integer,integer,text,integer,text,text)
 from public,anon,authenticated;
grant execute on function public.factory_prepare_change_set_release_epoch(uuid,uuid,bigint,text,integer,integer,text,integer,text,text)
 to service_role;
commit;
