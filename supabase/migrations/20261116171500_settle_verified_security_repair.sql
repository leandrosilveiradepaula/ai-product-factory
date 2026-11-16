-- Generic nonproduction security-repair settlement for an exact owner-reviewed
-- GitHub commit. A recovered blocked repair may have been fixed directly in
-- its ALREADY-APPROVED write scope, without reintroducing a model or backend.
-- Not a release. Requires separately authorized Control Plane migration.
begin;
create or replace function public.factory_settle_verified_blocked_security_repair_v1(
 p_change_set_id uuid, p_root_run_id uuid, p_repair_job_id uuid,
 p_old_sha text, p_new_sha text, p_pr_number integer, p_evidence jsonb
) returns jsonb
language plpgsql security invoker set search_path='' as $settle$
declare
 c public.factory_change_sets%rowtype;
 p public.factory_projects%rowtype;
 ctl record;
 root_run public.factory_runs%rowtype;
 repair public.factory_repair_jobs%rowtype;
 unit public.factory_change_set_work_units%rowtype;
 blocked_run public.factory_runs%rowtype;
 task_row public.factory_tasks%rowtype;
 v_link record;
 v_cursor text;
 v_link_count integer:=0;
 source_receipt record;
 expected_path text;
 v_rows integer;
begin
 if p_change_set_id is null or p_root_run_id is null or p_repair_job_id is null
   or p_old_sha !~ '^[0-9a-f]{40}$' or p_new_sha !~ '^[0-9a-f]{40}$'
   or p_old_sha=p_new_sha or p_pr_number is null or p_pr_number<1
   or jsonb_typeof(p_evidence) is distinct from 'object'
   or p_evidence->>'old_sha' is distinct from p_old_sha
   or p_evidence->>'new_sha' is distinct from p_new_sha
   or p_evidence->>'pr_number' is distinct from p_pr_number::text
   or p_evidence->>'compare_status' is distinct from 'ahead'
   or p_evidence->>'behind_by' is distinct from '0'
   or p_evidence->>'ahead_by' is distinct from '1'
   or p_evidence->>'ci_conclusion' is distinct from 'success'
   or p_evidence->>'security_secret_scan' is distinct from 'clean'
   or p_evidence->>'changed_files_count' is distinct from '1'
   or jsonb_typeof(p_evidence->'changed_files') is distinct from 'array'
   or jsonb_array_length(p_evidence->'changed_files')<>1
   or p_evidence->>'release_authorized' is distinct from 'false'
 then raise exception 'invalid independently verified security repair' using errcode='PT400'; end if;

 select * into c from public.factory_change_sets where id=p_change_set_id for update;
 if not found or c.status is distinct from 'blocked'
   or c.candidate_commit is distinct from p_old_sha
   or c.current_wave<2 or c.release_run_id is not null
   or c.lease_owner is not null or c.lease_expires_at is not null
   or c.integration_branch is distinct from p_evidence->>'branch'
   or c.integration_branch in ('main','master')
   or c.metadata#>>'{blocker,type}' is distinct from 'implementation_preflight_error'
   or c.metadata#>>'{blocker,reason}' not like
     'PermissionError: editable repository context contains redacted secret: %'
 then raise exception 'change set is not a blocked security-context repair' using errcode='PT409'; end if;
 select * into p from public.factory_projects where id=c.project_id for share;
 select state,generation into ctl from public.factory_project_execution_controls
 where project_id=c.project_id for share;
 if not found or p.is_active is distinct from true
    or p.project_kind is distinct from 'greenfield'
    or p.repository is distinct from p_evidence->>'repository'
    or ctl.state is distinct from 'running' or ctl.generation<1
 then raise exception 'greenfield project epoch or repository not valid' using errcode='PT409'; end if;

 select * into root_run from public.factory_runs where id=p_root_run_id for update;
 if not found or root_run.task_id is distinct from c.root_task_id
    or root_run.status is distinct from 'specialist_review_failed'
    or root_run.candidate_commit is distinct from p_old_sha
    or root_run.branch_name is distinct from c.integration_branch
    or root_run.metadata->>'source' is distinct from 'change-set'
    or root_run.metadata->>'change_set_id' is distinct from c.id::text
    or root_run.metadata->>'execution_generation' is distinct from ctl.generation::text
    or root_run.lease_owner is not null or root_run.lease_expires_at is not null
 then raise exception 'root run is not the same blocked review' using errcode='PT409'; end if;
 if c.metadata#>>'{integration_release_request,pr_number}' is distinct from p_pr_number::text
    or c.metadata#>>'{integration_release_request,candidate_commit}' is distinct from p_old_sha
    or c.metadata#>>'{integration_release_request,branch}' is distinct from c.integration_branch
    or c.metadata#>>'{integration_epoch_receipt,candidate_commit}' is distinct from p_old_sha
    or c.metadata#>>'{integration_epoch_receipt,generation}' is distinct from ctl.generation::text
 then raise exception 'original integration receipt does not match blocked review' using errcode='PT409'; end if;

 select * into repair from public.factory_repair_jobs where id=p_repair_job_id for update;
 if not found or repair.change_set_id is distinct from c.id
    or repair.project_id is distinct from c.project_id
    or repair.source_run_id is distinct from root_run.id
    or repair.source_role is distinct from 'security'
    or repair.status is distinct from 'queued'
    or repair.candidate_commit is distinct from p_old_sha
    or repair.cycle not between 1 and 3
    or repair.work_unit_id is null or repair.task_id is null
    or jsonb_typeof(repair.write_scopes) is distinct from 'array'
    or jsonb_array_length(repair.write_scopes)<>1
 then raise exception 'single approved repair scope is required' using errcode='PT409'; end if;
 expected_path:=repair.write_scopes->>0;
 if expected_path !~ '^(src|app|apps|packages|tests)/[A-Za-z0-9_./()-]+\.(py|ts|tsx|js|jsx)$'
    or expected_path like '%..%' or expected_path like '%//%'
    or p_evidence->'changed_files'->>0 is distinct from expected_path
    or repair.finding->>'path' is distinct from expected_path
    or repair.finding->>'kind' is distinct from 'secret_scan'
    or repair.finding->>'code' is distinct from 'supabase_secret'
    or c.metadata#>>'{blocker,reason}' is distinct from
       'PermissionError: editable repository context contains redacted secret: '||expected_path
 then raise exception 'repair target differs from approved security finding' using errcode='PT409'; end if;
 select count(*) into v_rows from public.factory_repair_jobs
 where change_set_id=c.id and status in ('queued','running','blocked');
 if v_rows<>1 then raise exception 'multiple unfinished repairs cannot be settled' using errcode='PT409'; end if;
 select * into unit from public.factory_change_set_work_units where id=repair.work_unit_id for update;
 if not found or unit.change_set_id is distinct from c.id
    or unit.task_id is distinct from repair.task_id
    or unit.status is distinct from 'blocked'
    or unit.wave is distinct from c.current_wave
    or unit.base_commit is distinct from p_old_sha
    or unit.output_commit is not null
    or unit.agent_key is distinct from repair.owner_agent_key
    or unit.plan_task_key is distinct from 'repair-security-'||repair.cycle::text
    or c.metadata#>>'{blocker,work_unit_id}' is distinct from unit.id::text
    or c.metadata#>>'{blocker,run_id}' is distinct from unit.run_id::text
 then raise exception 'source blocked work unit changed' using errcode='PT409'; end if;
 select * into blocked_run from public.factory_runs where id=unit.run_id for update;
 select * into task_row from public.factory_tasks where id=unit.task_id for update;
 if blocked_run.status is distinct from 'blocked'
    or blocked_run.task_id is distinct from task_row.id
    or blocked_run.candidate_commit is not null
    or blocked_run.attempt_count not between 1 and 2
    or blocked_run.lease_owner is not null or blocked_run.lease_expires_at is not null
    or blocked_run.last_error is distinct from c.metadata#>>'{blocker,reason}'
    or blocked_run.metadata->>'execution_generation' is distinct from ctl.generation::text
    or task_row.status is distinct from 'blocked'
    or task_row.project_id is distinct from c.project_id
 then raise exception 'blocked run/task historical identities mismatch' using errcode='PT409'; end if;
 if exists(select 1 from public.factory_change_set_work_units w where w.change_set_id=c.id
   and w.id<>unit.id and w.status is distinct from 'integrated')
 then raise exception 'unintegrated nonrepair work units remain' using errcode='PT409'; end if;

 select count(*) as n,max(metadata->>'head_sha') as sha into source_receipt
 from public.factory_tool_usage
 where run_id=root_run.id and operation='create_pr'
   and metadata->>'pr'=p_pr_number::text and metadata->>'change_set_id'=c.id::text;
 if source_receipt.n<>1 or source_receipt.sha !~ '^[0-9a-f]{40}$'
 then raise exception 'original issued PR receipt is ambiguous' using errcode='PT409'; end if;
 -- Full immutable ancestry: original issued PR -> one or more exact-SHA
 -- independently verified CI reconciliations -> currently blocked candidate.
 -- Do not confuse latest recovery's original SHA with its actual predecessor.
 v_cursor:=source_receipt.sha;
 for v_link in
   select u.id,u.metadata from public.factory_tool_usage u
   where u.run_id=root_run.id and u.operation='reconcile_pr_candidate'
   order by u.created_at,u.id
 loop
   v_link_count:=v_link_count+1;
   if v_link_count>12
      or jsonb_typeof(v_link.metadata) is distinct from 'object'
      or v_link.metadata->>'change_set_id' is distinct from c.id::text
      or v_link.metadata->>'repository' is distinct from p.repository
      or v_link.metadata->>'branch' is distinct from c.integration_branch
      or v_link.metadata->>'pr_number' is distinct from p_pr_number::text
      or v_link.metadata->>'compare_status' is distinct from 'ahead'
      or v_link.metadata->>'behind_by' is distinct from '0'
      or coalesce((v_link.metadata->>'ahead_by') ~ '^[1-9][0-9]*$',false) is false
      or (v_link.metadata->>'new_sha') !~ '^[a-f0-9]{40}$'
      or v_link.metadata->>'candidate_commit' is distinct from v_link.metadata->>'new_sha'
      or v_link.metadata->>'new_sha' is not distinct from v_cursor
   then raise exception 'invalid candidate reconciliation history'
        using errcode='PT409'; end if;

   if v_link.metadata->>'source' = 'independent_github_api' then
     if v_link.metadata->>'old_sha' is distinct from v_cursor
        or v_link.metadata->>'ci_conclusion' is distinct from 'success'
        or v_link.metadata->>'ci_sha' is distinct from v_link.metadata->>'new_sha'
        or v_link.metadata->>'pr_head_sha' is distinct from v_link.metadata->>'new_sha'
        or v_link.metadata->>'branch_head_sha' is distinct from v_link.metadata->>'new_sha'
        or v_link.metadata->>'pr_state' is distinct from 'open'
        or v_link.metadata->>'pr_base' is distinct from 'main'
     then raise exception 'original native CI reconciliation invalid'
          using errcode='PT409'; end if;
   elsif v_link.metadata->>'recovery_source' = 'blocked_release_policy' then
     if v_link.metadata->>'old_sha' is distinct from source_receipt.sha
        or v_link.metadata->>'previous_commit' is distinct from source_receipt.sha
        or v_link.metadata->>'prior_candidate_commit' is distinct from v_cursor
        or v_link.metadata->>'original_head_sha' is distinct from source_receipt.sha
        or v_link.metadata->>'ci_state' is distinct from 'success'
        or v_link.metadata->>'ci_source' is distinct from 'github_actions_checks'
        or coalesce((v_link.metadata->>'native_checks') ~ '^[1-9][0-9]*$',false) is false
        or coalesce((v_link.metadata->>'native_workflows') ~ '^[1-9][0-9]*$',false) is false
        or v_link.metadata->>'release_authorized' is distinct from 'false'
        or v_link.metadata->>'target_pr_ci_still_required' is distinct from 'true'
     then raise exception 'policy blocked CI recovery chain invalid'
          using errcode='PT409'; end if;
   else
     raise exception 'unverified candidate reconciliation origin'
          using errcode='PT409';
   end if;
   v_cursor:=v_link.metadata->>'new_sha';
 end loop;
 if v_cursor is distinct from p_old_sha then
   raise exception 'candidate SHA not reachable from issued PR receipt'
        using errcode='PT409'; end if;

 -- This integrates ONLY the externally committed fix verified on GitHub.
 -- Blocked implementation run remains immutable; fresh CI, QA, Security,
 -- Operations, Preview, DoD and human production gate are mandatory.
 update public.factory_change_set_work_units
 set status='integrated',output_commit=p_new_sha,changed_files=p_evidence->'changed_files',
     updated_at=now()
 where id=unit.id and status='blocked';
 if not found then raise exception 'unit settlement raced' using errcode='PT409'; end if;
 update public.factory_tasks set status='completed',updated_at=now()
 where id=task_row.id and status='blocked';
 if not found then raise exception 'task settlement raced' using errcode='PT409'; end if;
 update public.factory_repair_jobs set status='integrated',
     candidate_commit=p_new_sha,updated_at=now() where id=repair.id and status='queued';
 if not found then raise exception 'repair settlement raced' using errcode='PT409'; end if;
 update public.factory_change_sets
 set status='ci_pending',candidate_commit=p_new_sha,release_run_id=root_run.id,
     metadata=jsonb_set(jsonb_set((c.metadata-'blocker'),
       '{integration_release_request,candidate_commit}',to_jsonb(p_new_sha),false),
       '{integration_epoch_receipt,candidate_commit}',to_jsonb(p_new_sha),false)
       ||jsonb_build_object('verified_external_security_repair',
          jsonb_build_object('repair_id',repair.id,'blocked_run_id',blocked_run.id,
            'original_sha',p_old_sha,'new_sha',p_new_sha,'ci_verified',true,
            'security_recheck_required',true,'release_authorized',false,'at',now())),
     updated_at=now()
 where id=c.id and status='blocked';
 if not found then raise exception 'change set settlement raced' using errcode='PT409'; end if;
 update public.factory_runs set status='ci_pending',candidate_commit=p_new_sha,
     last_error=null,metadata=metadata||jsonb_build_object(
        'security_repair_exact_sha',jsonb_build_object(
          'original_sha',p_old_sha,'new_sha',p_new_sha,
          'repair_id',repair.id,'release_authorized',false,'at',now()))
 where id=root_run.id and status='specialist_review_failed';
 if not found then raise exception 'root run settlement raced' using errcode='PT409'; end if;
 insert into public.factory_tool_usage(run_id,tool_family,operation,usage_units,estimated_cost,metadata)
 values(root_run.id,'github','reconcile_pr_candidate',1,0,
    p_evidence || jsonb_build_object('change_set_id',c.id,
       'previous_commit',source_receipt.sha,'old_sha',source_receipt.sha,
       'prior_candidate_commit',p_old_sha,'candidate_commit',p_new_sha,
       'recovery_source','verified_scoped_external_security_repair',
       'release_authorized',false));
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(c.project_id,repair.task_id,blocked_run.id,'system',
   'verified-security-repair-settlement','change_set.security_repair.exact_sha_integrated',
   jsonb_build_object('change_set_id',c.id,'root_run_id',root_run.id,
     'repair_id',repair.id,'previous_commit',p_old_sha,
     'candidate_commit',p_new_sha,'changed_files',p_evidence->'changed_files',
     'original_blocked_run_preserved',true,'new_specialist_review_required',true,
     'release_authorized',false,'automatic_merge',false,'paid_model_calls',0));
 return jsonb_build_object('status','ci_pending','run_id',root_run.id,
    'candidate_commit',p_new_sha,'repair_id',repair.id,
    'old_evidence_preserved',true,'new_specialist_review_required',true,
    'release_authorized',false);
end;
$settle$;
revoke all on function public.factory_settle_verified_blocked_security_repair_v1(uuid,uuid,uuid,text,text,integer,jsonb)
 from public,anon,authenticated;
grant execute on function public.factory_settle_verified_blocked_security_repair_v1(uuid,uuid,uuid,text,text,integer,jsonb)
 to service_role;
commit;
