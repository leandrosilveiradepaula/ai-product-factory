-- Candidate only: privileged migration requires explicit human authorization.
begin;
create or replace function public.factory_reconcile_change_set_ci_candidate(
 p_change_set_id uuid,p_run_id uuid,p_pr_number integer,
 p_previous_commit text,p_new_commit text,p_verified_evidence jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare
 v_set public.factory_change_sets%rowtype;
 v_run public.factory_runs%rowtype;
 v_request jsonb;v_receipt jsonb;
 v_control record;
begin
 if p_change_set_id is null or p_run_id is null or p_pr_number<1
    or p_previous_commit !~ '^[0-9a-f]{40}$'
    or p_new_commit !~ '^[0-9a-f]{40}$'
    or p_previous_commit=p_new_commit
    or jsonb_typeof(p_verified_evidence) is distinct from 'object'
    or p_verified_evidence->>'old_sha' is distinct from p_previous_commit
    or p_verified_evidence->>'new_sha' is distinct from p_new_commit
    or p_verified_evidence->>'pr_number' is distinct from p_pr_number::text
    or p_verified_evidence->>'compare_status' is distinct from 'ahead'
    or coalesce((p_verified_evidence->>'ahead_by') ~ '^[1-9][0-9]*$',false) is false
 then raise exception 'invalid candidate reconciliation evidence' using errcode='PT400';
 end if;
 select s.* into v_set from public.factory_change_sets s
 where s.id=p_change_set_id for update;
 if not found or v_set.status<>'ci_pending'
    or v_set.release_run_id is distinct from p_run_id
    or v_set.candidate_commit is distinct from p_previous_commit then
  raise exception 'change set candidate revoked' using errcode='PT409';
 end if;
 select state,generation into v_control
 from public.factory_project_execution_controls
 where project_id=v_set.project_id for share;
 if not found or v_control.state is distinct from 'running' then
  raise exception 'project execution revoked' using errcode='PT409';
 end if;
 select * into v_run from public.factory_runs where id=p_run_id for update;
 if not found or v_run.status<>'ci_pending'
    or v_run.candidate_commit is distinct from p_previous_commit
    or v_run.branch_name is distinct from v_set.integration_branch then
  raise exception 'CI run candidate revoked' using errcode='PT409';
 end if;
 v_request:=v_set.metadata->'integration_release_request';
 v_receipt:=v_set.metadata->'integration_epoch_receipt';
 if jsonb_typeof(v_request) is distinct from 'object'
    or v_request->>'candidate_commit' is distinct from p_previous_commit
    or v_request->>'branch' is distinct from v_set.integration_branch
    or v_request->>'pr_number' is distinct from p_pr_number::text
    or jsonb_typeof(v_receipt) is distinct from 'object'
    or v_receipt->>'candidate_commit' is distinct from p_previous_commit
    or v_receipt->>'generation' is distinct from v_control.generation::text
    or v_receipt->>'project_id' is distinct from v_set.project_id::text then
  raise exception 'release epoch evidence revoked' using errcode='PT409';
 end if;
 -- The original create_pr receipt is immutable; append a separate reconciliation receipt.
 if not exists (
   select 1 from public.factory_tool_usage u
   where u.run_id=p_run_id and u.operation='create_pr'
     and u.metadata->>'pr'=p_pr_number::text
     and u.metadata->>'head_sha'=p_previous_commit
     and u.metadata->>'change_set_id'=p_change_set_id::text
 ) then raise exception 'original PR receipt missing' using errcode='PT409';
 end if;
 update public.factory_runs set candidate_commit=p_new_commit where id=p_run_id;
 update public.factory_change_sets
 set candidate_commit=p_new_commit,
     metadata=jsonb_set(jsonb_set(v_set.metadata,'{integration_release_request,candidate_commit}',
        to_jsonb(p_new_commit),false),'{integration_epoch_receipt,candidate_commit}',
        to_jsonb(p_new_commit),false),
     updated_at=now()
 where id=p_change_set_id;
 insert into public.factory_tool_usage(run_id,tool_family,operation,usage_units,estimated_cost,metadata)
 values(p_run_id,'github','reconcile_pr_candidate',1,0,
   p_verified_evidence||jsonb_build_object('change_set_id',p_change_set_id,
     'previous_commit',p_previous_commit,'candidate_commit',p_new_commit));
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_set.project_id,v_set.root_task_id,p_run_id,'system','ci-candidate-reconciler',
 'change_set.ci_candidate.reconciled',
 p_verified_evidence||jsonb_build_object('change_set_id',p_change_set_id));
 return jsonb_build_object('status','ci_pending','run_id',p_run_id,
   'candidate_commit',p_new_commit,'previous_commit',p_previous_commit);
end;
$fn$;
revoke all on function public.factory_reconcile_change_set_ci_candidate(uuid,uuid,integer,text,text,jsonb)
 from public,anon,authenticated;
grant execute on function public.factory_reconcile_change_set_ci_candidate(uuid,uuid,integer,text,text,jsonb)
 to service_role;
commit;
