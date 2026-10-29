-- Opt-in replacement of an obsolete existing-project Preview candidate.
-- This is a NEW CAS, not a relaxation of factory_repin_nonproduction_target_v1.
-- Requires separate human approval BEFORE installation in the production Control Plane.
-- Caller verifies live GitHub PR/ref/main ancestry/issue/exact native Actions CI.
begin;

create function public.factory_replace_nonproduction_candidate_v1(
 p_project_key text,
 p_expected_old_branch text,
 p_expected_old_sha text,
 p_expected_old_pr integer,
 p_new_branch text,
 p_new_sha text,
 p_new_pr integer,
 p_issue_number integer,
 p_expected_generation bigint,
 p_expected_version bigint,
 p_evidence jsonb,
 p_actor_ref text
) returns jsonb
language plpgsql security invoker set search_path=''
as $switch$
declare
 v_project public.factory_projects%rowtype;
 v_control public.factory_project_execution_controls%rowtype;
 v_old jsonb;
 v_new jsonb;
 v_ci jsonb;
 v_request jsonb;
 v_receipt jsonb;
begin
 if p_project_key is null or p_project_key !~ '^[a-z0-9][a-z0-9-]{0,63}$'
  or p_expected_old_branch is null or p_expected_old_branch !~ '^preview/[a-z0-9][a-z0-9/_-]{1,95}$'
  or p_new_branch is null or p_new_branch !~ '^preview/[a-z0-9][a-z0-9/_-]{1,95}$'
  or p_new_branch = p_expected_old_branch
  or p_expected_old_sha is null or p_expected_old_sha !~ '^[a-f0-9]{40}$'
  or p_new_sha is null or p_new_sha !~ '^[a-f0-9]{40}$'
  or p_expected_old_sha = p_new_sha
  or p_expected_old_pr is null or p_expected_old_pr < 1
  or p_new_pr is null or p_new_pr < 1 or p_new_pr = p_expected_old_pr
  or p_issue_number is null or p_issue_number < 1
  or p_expected_generation is null or p_expected_generation < 1
  or p_expected_version is null or p_expected_version < 0
  or p_actor_ref is null or length(p_actor_ref) not between 3 and 128
  or p_actor_ref ~ '[^A-Za-z0-9_.:-]'
  or p_evidence is null or jsonb_typeof(p_evidence) <> 'object'
  or length(p_evidence::text) > 8192
 then raise exception 'invalid candidate switch request' using errcode='PT400'; end if;

 select * into v_project
 from public.factory_projects
 where project_key=p_project_key for update;
 if not found or v_project.is_active is distinct from true
  or v_project.project_kind <> 'existing' or v_project.repository is null
 then raise exception 'existing project not active' using errcode='PT409'; end if;

 select * into v_control from public.factory_project_execution_controls
 where project_id=v_project.id for update;
 if not found or v_control.state <> 'running'
  or v_control.generation is distinct from p_expected_generation
  or v_control.version is distinct from p_expected_version
 then raise exception 'project epoch changed' using errcode='PT409'; end if;

 v_old := v_project.manifest->'delivery_target';
 v_ci := v_old->'repin_policy'->'native_ci';
 v_request := v_project.manifest->'continuation_request';
 if v_old is null or v_old->>'mode' is distinct from 'open_pr_candidate'
  or v_old->>'schema_version' is distinct from '1'
  or v_old->>'repository' is distinct from v_project.repository
  or v_old->>'branch' is distinct from p_expected_old_branch
  or v_old->>'sha' is distinct from p_expected_old_sha
  or v_old->>'candidate_pr_number' is distinct from p_expected_old_pr::text
  or v_old->'repin_policy'->>'enabled' is distinct from 'true'
  or v_old->'repin_policy'->>'schema_version' is distinct from '1'
  or v_ci->>'schema_version' is distinct from '1'
  or v_ci->>'event' is distinct from 'pull_request'
  or v_request->>'source' is distinct from 'github-owner'
  or nullif(v_request->>'id','') is null
  or (v_request->>'summary') is null
  or (v_request->>'summary') !~* ('(^|[^0-9])issue[[:space:]]+#'
         ||p_issue_number::text||'([^0-9]|$)')
 then raise exception 'candidate or authorized issue changed' using errcode='PT409'; end if;

 -- The service-role worker must attest the *old* pinned identity as well as
 -- the proposed new PR. The function does not accept user/browser evidence.
 if p_evidence->>'source' is distinct from 'github_actions_exact_sha'
  or p_evidence->>'repository' is distinct from v_project.repository
  or p_evidence->>'request_id' is distinct from v_request->>'id'
  or p_evidence->>'issue_number' is distinct from p_issue_number::text
  or p_evidence->>'old_branch' is distinct from p_expected_old_branch
  or p_evidence->>'old_sha' is distinct from p_expected_old_sha
  or p_evidence->>'old_pr_number' is distinct from p_expected_old_pr::text
  or p_evidence->>'new_branch' is distinct from p_new_branch
  or p_evidence->>'new_sha' is distinct from p_new_sha
  or p_evidence->>'new_pr_number' is distinct from p_new_pr::text
  or p_evidence->>'pr_head_sha' is distinct from p_new_sha
  or p_evidence->>'branch_head_sha' is distinct from p_new_sha
  or p_evidence->>'pr_base' is distinct from 'main'
  or p_evidence->>'pr_base_sha' is null
  or p_evidence->>'pr_base_sha' !~ '^[a-f0-9]{40}$'
  or p_evidence->>'pr_state' is distinct from 'open'
  or p_evidence->>'compare_status' is distinct from 'ahead'
  or p_evidence->>'ci_conclusion' is distinct from 'success'
  or p_evidence->>'ci_sha' is distinct from p_new_sha
  or p_evidence->>'ci_workflow_path' is distinct from v_ci->>'workflow_path'
  or p_evidence->>'ci_workflow_name' is distinct from v_ci->>'workflow_name'
  or p_evidence->>'ci_workflow_id' is distinct from v_ci->>'workflow_id'
  or jsonb_typeof(p_evidence->'ahead_by') is distinct from 'number'
  or jsonb_typeof(p_evidence->'behind_by') is distinct from 'number'
  or jsonb_typeof(p_evidence->'ci_run_id') is distinct from 'number'
  or jsonb_typeof(p_evidence->'ci_run_number') is distinct from 'number'
  or jsonb_typeof(p_evidence->'ci_run_attempt') is distinct from 'number'
  or (p_evidence->>'ahead_by')::integer not between 1 and 32
  or (p_evidence->>'behind_by')::integer <> 0
  or (p_evidence->>'ci_run_id')::bigint <= 0
  or (p_evidence->>'ci_run_number')::bigint <= 0
  or (p_evidence->>'ci_run_attempt')::integer <= 0
 then raise exception 'unverified new candidate evidence' using errcode='PT400'; end if;

 -- No live work can be retargeted. Only immutable unleased repair receipts
 -- from a completed task AND its exact completed Change Set are exempt.
 if not public.factory_control_quiescent(v_project.id)
  or exists (
   select 1 from public.factory_runs r
   join public.factory_tasks t on t.id=r.task_id
   where t.project_id=v_project.id and r.status in (
    'queued','claimed','running','dispatch_pending','ci_pending',
    'integration_pending','review_pending','specialist_review_pending',
    'preview_pending','repair_pending','release_pending'
   )
   and not (
    r.status='repair_pending'
    and r.lease_owner is null and r.lease_expires_at is null
    and t.status='completed'
    and exists (
      select 1 from public.factory_change_sets cs
      where cs.id::text=r.metadata->>'change_set_id'
       and cs.project_id=v_project.id and cs.root_task_id=t.id
       and cs.status='completed'
       and cs.lease_owner is null and cs.lease_expires_at is null
    )
   )
  )
  or exists (
    select 1 from public.factory_change_sets cs
    where cs.project_id=v_project.id and cs.status in (
     'queued','running','claimed','integration_pending','ci_pending',
     'dispatch_pending','review_pending','specialist_review_pending',
     'preview_pending','release_pending'
    )
  )
 then raise exception 'live project work prevents candidate switch' using errcode='PT409'; end if;

 -- Retain native CI and repin policy; change ONLY the target identity.
 v_new := jsonb_set(
    jsonb_set(
      jsonb_set(v_old,'{sha}',to_jsonb(p_new_sha)),
      '{branch}',to_jsonb(p_new_branch)
    ),
    '{candidate_pr_number}',to_jsonb(p_new_pr)
 );
 update public.factory_projects
 set manifest=jsonb_set(v_project.manifest,'{delivery_target}',v_new),
     updated_at=now()
 where id=v_project.id;
 update public.factory_project_execution_controls
 set generation=generation+1,version=version+1,updated_at=now()
 where project_id=v_project.id;

 v_receipt := jsonb_build_object(
   'status','replaced','project_key',p_project_key,
   'repository',v_project.repository,'issue_number',p_issue_number,
   'request_id',v_request->>'id',
   'old_branch',p_expected_old_branch,'old_sha',p_expected_old_sha,
   'old_pr_number',p_expected_old_pr,
   'new_branch',p_new_branch,'new_sha',p_new_sha,'new_pr_number',p_new_pr,
   'ci_sha',p_new_sha,'ci_run_id',p_evidence->'ci_run_id',
   'generation',p_expected_generation+1,'version',p_expected_version+1
 );
 insert into public.factory_audit_events(
   project_id,actor_type,actor_ref,event_type,payload
 ) values (
   v_project.id,'system',p_actor_ref,
   'project.delivery_target.replaced',v_receipt
 );
 return v_receipt;
end;
$switch$;

revoke all on function public.factory_replace_nonproduction_candidate_v1(
 text,text,text,integer,text,text,integer,integer,bigint,bigint,jsonb,text
) from public,anon,authenticated;
grant execute on function public.factory_replace_nonproduction_candidate_v1(
 text,text,text,integer,text,text,integer,integer,bigint,bigint,jsonb,text
) to service_role;
commit;
