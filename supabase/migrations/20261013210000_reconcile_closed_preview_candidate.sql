-- Versioned, transactional reconciliation of a GitHub PR closed without merge.
-- The trusted worker verifies the GitHub PR identity and exact head SHA first.
create or replace function public.factory_reconcile_closed_preview_candidate(
 p_run_id uuid,p_candidate_commit text,p_pr_number integer,
 p_github_state text,p_github_merged boolean
) returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
 v_run public.factory_runs%rowtype;
 v_task public.factory_tasks%rowtype;
 v_set public.factory_change_sets%rowtype;
 v_evidence jsonb;
 v_record jsonb;
begin
 if p_github_state is distinct from 'closed'
   or p_github_merged is distinct from false then
   raise exception 'PR must be verified closed without merge';
 end if;
 if p_pr_number is null or p_pr_number<=0
   or p_candidate_commit is null or p_candidate_commit !~ '^[0-9a-f]{40}$' then
   raise exception 'valid PR number and full candidate SHA required';
 end if;
 select * into v_run from public.factory_runs where id=p_run_id for update;
 if v_run.id is null then raise exception 'preview run not found'; end if;
 if v_run.candidate_commit is distinct from p_candidate_commit
   or v_run.metadata->>'source' is distinct from 'change-set' then
   raise exception 'preview run source or candidate mismatch';
 end if;
 select * into v_task from public.factory_tasks
 where id=v_run.task_id for update;
 if v_task.id is null or v_task.status<>'completed' then
   raise exception 'root task must be completed before supersession';
 end if;
 if nullif(v_run.metadata->>'change_set_id','') is null then
   raise exception 'preview run is missing Change Set binding';
 end if;
 select * into v_set from public.factory_change_sets
 where id=(v_run.metadata->>'change_set_id')::uuid for update;
 if v_set.id is null or v_set.release_run_id is distinct from p_run_id
   or v_set.root_task_id is distinct from v_task.id
   or v_set.project_id is distinct from v_task.project_id
   or v_set.candidate_commit is distinct from p_candidate_commit then
   raise exception 'Change Set binding mismatch';
 end if;
 select u.metadata into v_evidence
 from public.factory_tool_usage u
 where u.run_id=p_run_id and u.operation='create_pr'
 order by u.created_at desc,u.id desc limit 1;
 if v_evidence is null
   or v_evidence->>'pr' is distinct from p_pr_number::text
   or v_evidence->>'head_sha' is distinct from p_candidate_commit then
   raise exception 'durable PR evidence mismatch';
 end if;
 if exists(select 1 from public.factory_human_gates g
   where g.run_id=p_run_id and g.status='pending')
   or exists(select 1 from public.factory_release_reports rr
     where rr.run_id=p_run_id and rr.status='released') then
   raise exception 'human gate or release prohibits supersession';
 end if;

 v_record:=v_run.metadata->'closed_pr_reconciliation';
 if v_run.status='cancelled' and v_set.status='superseded'
   and v_record->>'candidate_commit'=p_candidate_commit
   and v_record->>'pr_number'=p_pr_number::text then
   return jsonb_build_object(
     'run_id',p_run_id,'status','cancelled',
     'change_set_status','superseded','idempotent',true);
 end if;
 if v_run.status<>'preview_ready' or v_set.status<>'ci_pending' then
   raise exception 'run or Change Set is not in a reconciliable state';
 end if;
 update public.factory_runs
 set status='cancelled',finished_at=coalesce(finished_at,now()),
   lease_owner=null,lease_expires_at=null,
   metadata=metadata||jsonb_build_object('closed_pr_reconciliation',
     jsonb_build_object('pr_number',p_pr_number,'candidate_commit',p_candidate_commit,
       'github_state','closed','merged',false,'reason','closed_unmerged_pr',
       'observed_at',now()))
 where id=p_run_id;
 update public.factory_change_sets
 set status='superseded',lease_owner=null,lease_expires_at=null,
   updated_at=now(),
   metadata=metadata||jsonb_build_object('reconciliation',
     jsonb_build_object('reason','closed_unmerged_pr','pr_number',p_pr_number,
       'candidate_commit',p_candidate_commit,'previous_status',v_set.status,
       'reconciled_at',now()))
 where id=v_set.id;
 insert into public.factory_audit_events(
   project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_task.project_id,v_task.id,p_run_id,'system','preview-followup',
   'preview.closed_unmerged_pr_reconciled',
   jsonb_build_object('change_set_id',v_set.id,'pr_number',p_pr_number,
     'candidate_commit',p_candidate_commit,'run_from','preview_ready',
     'run_to','cancelled','change_set_from',v_set.status,
     'change_set_to','superseded'));
 return jsonb_build_object('run_id',p_run_id,'status','cancelled',
   'change_set_id',v_set.id,'change_set_status','superseded',
   'idempotent',false);
end;
$$;
revoke all on function public.factory_reconcile_closed_preview_candidate(uuid,text,integer,text,boolean)
 from public,anon,authenticated;
grant execute on function public.factory_reconcile_closed_preview_candidate(uuid,text,integer,text,boolean)
 to service_role;
